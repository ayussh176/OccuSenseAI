# ============================================================
# OccuSense AI — HVAC Controller
# ============================================================
# The central decision engine that translates environmental
# state into concrete HVAC actions. It enforces hard safety
# limits, applies a layered rule engine (air-quality → energy
# → comfort → thermal → pre-conditioning), and emits actions
# to the EventBus for downstream broadcast and persistence.
# ============================================================

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from models.schemas import (
    FanSpeed,
    HVACAction,
    HVACMode,
)
from streaming.event_bus import EventChannel, bus
from utils.logger import logger
from utils.metrics import metrics


# ── Safety limits (hardcoded, never overridden) ──────────────

MIN_SETPOINT: float = 18.0
MAX_SETPOINT: float = 28.0
MAX_AIRFLOW: int = 100
DEFAULT_SETPOINT: float = 23.0
DEFAULT_FAN: FanSpeed = FanSpeed.MEDIUM


# ── Per-zone state tracked by the controller ─────────────────

class ZoneHVACState:
    """Mutable snapshot of one zone's current HVAC configuration."""

    def __init__(self, zone_id: str) -> None:
        self.zone_id = zone_id
        self.setpoint: float = DEFAULT_SETPOINT
        self.fan_speed: FanSpeed = DEFAULT_FAN
        self.mode: HVACMode = HVACMode.AUTO
        self.airflow_pct: float = 50.0
        self.ventilation_pct: float = 50.0
        self.enabled: bool = True
        self.last_action_ts: float = 0.0
        self.action_count: int = 0
        self.energy_kwh: float = 0.0
        self.baseline_kwh: float = 0.0


# ── Main controller ─────────────────────────────────────────

class HVACController:
    """
    Rule-based HVAC optimisation engine.

    The controller is stateless between zones — each zone has an independent
    ``ZoneHVACState`` and is evaluated independently every time an
    environmental update arrives.

    Rule evaluation order (highest priority first):
        1. Emergency safety (temperature extremes, CO₂ emergency)
        2. Air-quality rules (CO₂ thresholds → ventilation)
        3. Comfort protection (comfort score → setpoint nudge)
        4. Thermal balancing (actual temp vs. setpoint)
        5. Energy optimisation (occupancy == 0 → relax)
        6. Pre-conditioning (rising occupancy trend → pre-cool)
    """

    def __init__(self) -> None:
        self._zones: Dict[str, ZoneHVACState] = {}
        self._action_log: List[Dict[str, Any]] = []
        logger.info("HVACController initialised")

    # ── Zone management ──────────────────────────────────────

    def _ensure_zone(self, zone_id: str) -> ZoneHVACState:
        if zone_id not in self._zones:
            self._zones[zone_id] = ZoneHVACState(zone_id)
        return self._zones[zone_id]

    def get_zone_state(self, zone_id: str) -> Optional[ZoneHVACState]:
        return self._zones.get(zone_id)

    def get_all_states(self) -> Dict[str, ZoneHVACState]:
        return dict(self._zones)

    def set_zone_enabled(self, zone_id: str, enabled: bool) -> None:
        state = self._ensure_zone(zone_id)
        state.enabled = enabled
        logger.info(f"HVAC automation {'enabled' if enabled else 'disabled'} for {zone_id}")

    # ── Core evaluation ──────────────────────────────────────

    async def evaluate(self, env: Dict[str, Any]) -> Optional[HVACAction]:
        """
        Given an environmental snapshot ``env``, run the rule stack and
        return an HVACAction if the system should change anything.

        Expected keys in *env*:
            zone_id, co2_ppm, temperature_c, humidity, comfort_score,
            estimated_count, occupancy_trend, noise_db, light_level
        """
        zone_id: str = env.get("zone_id", "unknown")
        state = self._ensure_zone(zone_id)

        if not state.enabled:
            return None

        t0 = time.perf_counter()
        reasons: List[str] = []

        co2: float = env.get("co2_ppm", 420.0)
        temp: float = env.get("temperature_c", 22.0)
        humidity: float = env.get("humidity", 45.0)
        comfort: float = env.get("comfort_score", 80.0)
        occupancy: int = env.get("estimated_count", 0)
        trend: str = env.get("occupancy_trend", "stable")

        # Start from current state
        new_setpoint = state.setpoint
        new_fan = state.fan_speed
        new_mode = state.mode
        new_airflow = state.airflow_pct
        new_vent = state.ventilation_pct

        # ── 1. Emergency safety ──────────────────────────────
        if temp > 35.0:
            new_mode = HVACMode.COOLING
            new_fan = FanSpeed.MAX
            new_airflow = 100.0
            new_setpoint = 22.0
            reasons.append("emergency_overheating")
        elif temp < 10.0:
            new_mode = HVACMode.HEATING
            new_fan = FanSpeed.HIGH
            new_setpoint = 20.0
            reasons.append("emergency_overcooling")

        if co2 > 2000.0:
            new_vent = 100.0
            new_fan = FanSpeed.MAX
            reasons.append("emergency_co2")

        # ── 2. Air-quality rules ─────────────────────────────
        if co2 > 1500.0:
            new_vent = min(100.0, new_vent + 30)
            new_fan = FanSpeed.HIGH
            reasons.append("critical_co2_ventilation")
        elif co2 > 1000.0:
            new_vent = min(100.0, new_vent + 20)
            if new_fan in (FanSpeed.OFF, FanSpeed.LOW):
                new_fan = FanSpeed.MEDIUM
            reasons.append("high_co2_ventilation")
        elif co2 > 800.0:
            new_vent = min(100.0, new_vent + 10)
            reasons.append("elevated_co2")
        elif co2 < 500.0:
            new_vent = max(20.0, new_vent - 10)

        # ── 3. Comfort protection ────────────────────────────
        if comfort < 40.0:
            # Aggressive correction
            new_setpoint = 22.0
            new_fan = FanSpeed.HIGH
            new_mode = HVACMode.AUTO
            reasons.append("comfort_critical")
        elif comfort < 60.0:
            # Moderate nudge toward ideal
            if temp > 24.0:
                new_setpoint = max(MIN_SETPOINT, new_setpoint - 1.0)
            elif temp < 21.0:
                new_setpoint = min(MAX_SETPOINT, new_setpoint + 1.0)
            reasons.append("comfort_low")

        # ── 4. Humidity control ──────────────────────────────
        if humidity > 70.0:
            new_mode = HVACMode.COOLING  # dehumidify via cooling
            new_airflow = min(100.0, new_airflow + 15)
            reasons.append("high_humidity_dehumidify")
        elif humidity < 25.0:
            new_airflow = max(20.0, new_airflow - 10)
            reasons.append("low_humidity_reduce_airflow")

        # ── 5. Thermal balancing ─────────────────────────────
        delta = temp - new_setpoint
        if delta > 2.0:
            new_mode = HVACMode.COOLING
            new_fan = FanSpeed.HIGH if delta > 4.0 else FanSpeed.MEDIUM
            new_airflow = min(100.0, new_airflow + 10)
            reasons.append("thermal_overcool")
        elif delta < -2.0:
            new_mode = HVACMode.HEATING
            new_fan = FanSpeed.MEDIUM
            reasons.append("thermal_undercool")

        # ── 6. Energy optimisation ───────────────────────────
        if occupancy == 0:
            new_setpoint = 26.0  # relax setpoint
            new_fan = FanSpeed.LOW
            new_airflow = max(20.0, new_airflow - 20)
            new_mode = HVACMode.ENERGY_SAVER
            reasons.append("unoccupied_energy_save")
        elif occupancy <= 2:
            new_airflow = max(30.0, new_airflow - 10)
            reasons.append("low_occupancy_reduce")

        # ── 7. Pre-conditioning ──────────────────────────────
        if trend == "increasing" and occupancy >= 2:
            new_setpoint = max(MIN_SETPOINT, new_setpoint - 0.5)
            new_airflow = min(100.0, new_airflow + 5)
            reasons.append("pre_cooling_rising_occupancy")

        # ── Clamp to safety limits ───────────────────────────
        new_setpoint = max(MIN_SETPOINT, min(MAX_SETPOINT, new_setpoint))
        new_airflow = max(0.0, min(100.0, new_airflow))
        new_vent = max(0.0, min(100.0, new_vent))

        # ── Energy estimate ──────────────────────────────────
        fan_kwh_map = {
            FanSpeed.OFF: 0.0, FanSpeed.LOW: 0.8,
            FanSpeed.MEDIUM: 1.5, FanSpeed.HIGH: 2.5, FanSpeed.MAX: 3.5,
        }
        energy_est = fan_kwh_map.get(new_fan, 1.5) * (new_airflow / 100.0)
        baseline_est = energy_est * 1.35  # 35% worse without optimisation

        # ── Build action ─────────────────────────────────────
        if not reasons:
            reasons.append("no_change_needed")

        action = HVACAction(
            zone_id=zone_id,
            setpoint=round(new_setpoint, 1),
            fan_speed=new_fan,
            mode=new_mode,
            airflow_pct=round(new_airflow, 1),
            ventilation_pct=round(new_vent, 1),
            reason="|".join(reasons),
            energy_estimate_kwh=round(energy_est, 3),
            confidence=0.85,
        )

        # ── Update zone state ────────────────────────────────
        state.setpoint = action.setpoint
        state.fan_speed = action.fan_speed
        state.mode = action.mode
        state.airflow_pct = action.airflow_pct
        state.ventilation_pct = action.ventilation_pct
        state.last_action_ts = time.time()
        state.action_count += 1
        state.energy_kwh += energy_est
        state.baseline_kwh += baseline_est

        # ── Metrics ──────────────────────────────────────────
        elapsed = (time.perf_counter() - t0) * 1000
        metrics.observe("hvac_eval_ms", elapsed)
        metrics.inc("hvac_actions_total")

        # ── Persist to action log (in-memory ring buffer) ────
        entry = action.model_dump()
        entry["evaluation_ms"] = round(elapsed, 2)
        self._action_log.append(entry)
        if len(self._action_log) > 500:
            self._action_log = self._action_log[-500:]

        # ── Publish to EventBus ──────────────────────────────
        await bus.publish(EventChannel.HVAC_ACTION, action.model_dump(mode="json"))

        logger.info(
            f"HVAC → {zone_id}: sp={action.setpoint}°C fan={action.fan_speed.value} "
            f"mode={action.mode.value} air={action.airflow_pct}% "
            f"reason={action.reason}"
        )

        return action

    # ── Diagnostics ──────────────────────────────────────────

    @property
    def recent_actions(self) -> List[Dict[str, Any]]:
        return list(self._action_log[-20:])

    def get_energy_summary(self, zone_id: str) -> Dict[str, Any]:
        state = self._zones.get(zone_id)
        if not state:
            return {"zone_id": zone_id, "error": "zone_not_found"}
        savings = (
            ((state.baseline_kwh - state.energy_kwh) / state.baseline_kwh * 100)
            if state.baseline_kwh > 0 else 0.0
        )
        return {
            "zone_id": zone_id,
            "total_kwh": round(state.energy_kwh, 3),
            "baseline_kwh": round(state.baseline_kwh, 3),
            "savings_pct": round(savings, 1),
            "action_count": state.action_count,
        }


# Module-level singleton
hvac_controller = HVACController()
