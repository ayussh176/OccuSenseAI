# ============================================================
# OccuSense AI — Alert Engine
# ============================================================

from __future__ import annotations
import time, uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from models.schemas import Alert, AlertSeverity, AlertType
from streaming.event_bus import EventChannel, bus
from utils.logger import logger
from utils.metrics import metrics

CO2_HIGH = 1000.0
CO2_CRITICAL = 1500.0
TEMP_OVERHEAT = 30.0
TEMP_OVERCOOL = 16.0
HUMIDITY_HIGH = 70.0
COMFORT_LOW = 50.0
OCCUPANCY_SURGE = 20
DEFAULT_COOLDOWN = 120


class AlertEngine:
    def __init__(self) -> None:
        self._active: Dict[str, List[Alert]] = {}
        self._cooldowns: Dict[tuple, float] = {}
        self._history: List[Alert] = []
        self._started = False

    async def start(self) -> None:
        bus.subscribe(EventChannel.ANOMALY_ALERT, self._on_anomaly)
        bus.subscribe(EventChannel.ENVIRONMENT_UPDATE, self._on_environment)
        bus.subscribe(EventChannel.COMFORT_UPDATE, self._on_comfort)
        self._started = True
        logger.info("AlertEngine started")

    async def _on_anomaly(self, data: Dict[str, Any]) -> None:
        zone = data.get("zone_id", data.get("zone", "unknown"))
        try:
            at = AlertType(data.get("alert_type", "sensor_anomaly"))
        except ValueError:
            at = AlertType.SENSOR_ANOMALY
        try:
            sev = AlertSeverity(data.get("severity", "warning"))
        except ValueError:
            sev = AlertSeverity.WARNING
        await self._fire(zone, at, sev, data.get("message", f"Anomaly in {zone}"), data)

    async def _on_environment(self, data: Dict[str, Any]) -> None:
        zone = data.get("zone_id", data.get("zone", "unknown"))
        co2 = data.get("co2_ppm", 0)
        temp = data.get("temperature_c", 22)
        humidity = data.get("humidity", 45)
        occ = data.get("estimated_count", 0)

        if co2 >= CO2_CRITICAL:
            await self._fire(zone, AlertType.CRITICAL_CO2, AlertSeverity.CRITICAL,
                             f"CO2 {co2:.0f}ppm critical", data)
        elif co2 >= CO2_HIGH:
            await self._fire(zone, AlertType.HIGH_CO2, AlertSeverity.WARNING,
                             f"CO2 {co2:.0f}ppm elevated", data)
        if temp >= TEMP_OVERHEAT:
            await self._fire(zone, AlertType.OVERHEATING, AlertSeverity.CRITICAL,
                             f"Temp {temp:.1f}C overheating", data)
        elif temp <= TEMP_OVERCOOL:
            await self._fire(zone, AlertType.OVERCOOLING, AlertSeverity.WARNING,
                             f"Temp {temp:.1f}C overcooling", data)
        if humidity > HUMIDITY_HIGH:
            await self._fire(zone, AlertType.HIGH_HUMIDITY, AlertSeverity.WARNING,
                             f"Humidity {humidity:.0f}% high", data)
        if occ >= OCCUPANCY_SURGE:
            await self._fire(zone, AlertType.OCCUPANCY_SURGE, AlertSeverity.WARNING,
                             f"Occupancy surge: {occ}", data)

    async def _on_comfort(self, data: Dict[str, Any]) -> None:
        zone = data.get("zone_id", data.get("zone", "unknown"))
        comfort = data.get("comfort_score", 100)
        if comfort < COMFORT_LOW:
            await self._fire(zone, AlertType.COMFORT_DEGRADATION, AlertSeverity.WARNING,
                             f"Comfort {comfort:.0f} low", data)

    async def _fire(self, zone_id: str, alert_type: AlertType,
                    severity: AlertSeverity, message: str,
                    metadata: Dict[str, Any] | None = None) -> Optional[Alert]:
        key = (zone_id, alert_type.value)
        now = time.time()
        if now - self._cooldowns.get(key, 0) < DEFAULT_COOLDOWN:
            return None
        self._cooldowns[key] = now

        alert = Alert(alert_id=f"alert_{uuid.uuid4().hex[:12]}", zone_id=zone_id,
                      severity=severity, alert_type=alert_type, message=message,
                      metadata=metadata or {})
        self._active.setdefault(zone_id, []).append(alert)
        self._history.append(alert)
        if len(self._history) > 1000:
            self._history = self._history[-1000:]

        metrics.inc("alerts_total")
        await bus.publish(EventChannel.ALERT_EVENT, alert.model_dump(mode="json"))
        logger.warning(f"ALERT [{severity.value}] {zone_id}: {alert_type.value} — {message}")
        return alert

    def resolve(self, alert_id: str) -> bool:
        for zone_alerts in self._active.values():
            for a in zone_alerts:
                if a.alert_id == alert_id and not a.resolved:
                    a.resolved = True
                    a.resolved_at = datetime.utcnow()
                    return True
        return False

    def resolve_zone(self, zone_id: str) -> int:
        count = 0
        for a in self._active.get(zone_id, []):
            if not a.resolved:
                a.resolved = True
                a.resolved_at = datetime.utcnow()
                count += 1
        return count

    @property
    def active_alerts(self) -> List[Alert]:
        return [a for alerts in self._active.values() for a in alerts if not a.resolved]

    def zone_alerts(self, zone_id: str) -> List[Alert]:
        return [a for a in self._active.get(zone_id, []) if not a.resolved]

    @property
    def history(self) -> List[Alert]:
        return list(self._history[-50:])

    def status(self) -> Dict[str, Any]:
        return {"started": self._started, "active_count": len(self.active_alerts),
                "history_size": len(self._history)}


alert_engine = AlertEngine()
