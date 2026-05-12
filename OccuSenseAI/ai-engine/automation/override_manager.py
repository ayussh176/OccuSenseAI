# ============================================================
# OccuSense AI — Override Manager
# ============================================================
# Allows facility managers to place manual HVAC overrides on
# zones. Overrides have priority levels, expiration windows,
# and audit logging. The HVAC controller checks overrides
# before applying automated rules.
# ============================================================

from __future__ import annotations
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from models.schemas import Override, OverridePriority, FanSpeed, HVACMode
from streaming.event_bus import EventChannel, bus
from utils.logger import logger


class OverrideManager:
    def __init__(self) -> None:
        # zone_id → Override
        self._overrides: Dict[str, Override] = {}
        self._audit_log: List[Dict[str, Any]] = []

    # ── Set override ─────────────────────────────────────────

    async def set_override(
        self,
        zone_id: str,
        setpoint: float,
        duration_minutes: int = 120,
        priority: OverridePriority = OverridePriority.USER,
        reason: str = "",
        fan_speed: Optional[FanSpeed] = None,
        mode: Optional[HVACMode] = None,
    ) -> Override:
        """Place a manual HVAC override on a zone."""
        # Priority check — cannot override a higher-priority lock
        existing = self._overrides.get(zone_id)
        prio_order = {OverridePriority.USER: 0,
                      OverridePriority.FACILITY_MANAGER: 1,
                      OverridePriority.EMERGENCY: 2}
        if existing and existing.override_active:
            if prio_order.get(existing.priority, 0) > prio_order.get(priority, 0):
                logger.warning(f"Override denied for {zone_id}: existing {existing.priority} > {priority}")
                raise ValueError(
                    f"Cannot override: existing lock by {existing.priority.value} "
                    f"outranks {priority.value}"
                )

        # Clamp setpoint to safety limits
        setpoint = max(18.0, min(28.0, setpoint))

        override = Override(
            zone_id=zone_id,
            locked_setpoint=setpoint,
            locked_fan_speed=fan_speed,
            locked_mode=mode,
            priority=priority,
            reason=reason,
            expires_at=datetime.utcnow() + timedelta(minutes=duration_minutes),
        )
        self._overrides[zone_id] = override

        # Audit log
        entry = {
            "action": "set", "zone_id": zone_id,
            "setpoint": setpoint, "priority": priority.value,
            "reason": reason, "duration_min": duration_minutes,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._audit_log.append(entry)
        if len(self._audit_log) > 500:
            self._audit_log = self._audit_log[-500:]

        # Broadcast
        await bus.publish(EventChannel.OVERRIDE_EVENT, override.model_dump(mode="json"))
        logger.info(f"Override SET on {zone_id}: sp={setpoint} by {priority.value} for {duration_minutes}m")
        return override

    # ── Clear override ───────────────────────────────────────

    async def clear_override(self, zone_id: str, reason: str = "manual_clear") -> bool:
        override = self._overrides.get(zone_id)
        if not override or not override.override_active:
            return False
        override.override_active = False
        self._audit_log.append({
            "action": "clear", "zone_id": zone_id,
            "reason": reason, "timestamp": datetime.utcnow().isoformat(),
        })
        await bus.publish(EventChannel.OVERRIDE_EVENT, {
            "zone_id": zone_id, "override_active": False, "reason": reason,
        })
        logger.info(f"Override CLEARED on {zone_id}: {reason}")
        return True

    # ── Query ────────────────────────────────────────────────

    def is_overridden(self, zone_id: str) -> bool:
        """Check if a zone has an active, non-expired override."""
        override = self._overrides.get(zone_id)
        if not override or not override.override_active:
            return False
        if override.expires_at and datetime.utcnow() > override.expires_at:
            override.override_active = False
            return False
        return True

    def get_override(self, zone_id: str) -> Optional[Override]:
        if self.is_overridden(zone_id):
            return self._overrides[zone_id]
        return None

    def all_overrides(self) -> List[Override]:
        return [o for o in self._overrides.values() if self.is_overridden(o.zone_id)]

    @property
    def audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log[-30:])

    # ── Expiration sweep ─────────────────────────────────────

    async def sweep_expired(self) -> int:
        """Clear any overrides past their expiry. Called by scheduler."""
        now = datetime.utcnow()
        cleared = 0
        for zone_id, ov in list(self._overrides.items()):
            if ov.override_active and ov.expires_at and now > ov.expires_at:
                ov.override_active = False
                cleared += 1
                logger.info(f"Override EXPIRED on {zone_id}")
        return cleared


override_manager = OverrideManager()
