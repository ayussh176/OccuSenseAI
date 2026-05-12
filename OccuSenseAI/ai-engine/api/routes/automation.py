# ============================================================
# OccuSense AI — Automation API Routes
# ============================================================
# REST endpoints for controlling HVAC automation, overrides,
# alerts, energy optimisation, and scheduler status.
# ============================================================

from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from automation.hvac_controller import hvac_controller
from automation.alert_engine import alert_engine
from automation.override_manager import override_manager
from automation.workflow_engine import workflow_engine
from automation.scheduler import automation_scheduler
from models.schemas import OverridePriority, FanSpeed, HVACMode

router = APIRouter(tags=["Automation"])


# ── Request models ───────────────────────────────────────────

class OverrideRequest(BaseModel):
    zone_id: str
    setpoint: float = Field(ge=18.0, le=28.0, default=23.0)
    duration_minutes: int = Field(ge=1, le=1440, default=120)
    priority: str = "user"
    reason: str = ""
    fan_speed: Optional[str] = None
    mode: Optional[str] = None


class AutomationToggle(BaseModel):
    zone_id: str
    enabled: bool = True


# ── Override endpoints ───────────────────────────────────────

@router.post("/zones/override")
async def set_override(req: OverrideRequest):
    """Place a manual HVAC override on a zone."""
    try:
        prio = OverridePriority(req.priority)
    except ValueError:
        prio = OverridePriority.USER

    fan = None
    if req.fan_speed:
        try:
            fan = FanSpeed(req.fan_speed)
        except ValueError:
            pass

    mode = None
    if req.mode:
        try:
            mode = HVACMode(req.mode)
        except ValueError:
            pass

    try:
        override = await override_manager.set_override(
            zone_id=req.zone_id,
            setpoint=req.setpoint,
            duration_minutes=req.duration_minutes,
            priority=prio,
            reason=req.reason,
            fan_speed=fan,
            mode=mode,
        )
        return {"status": "override_set", "override": override.model_dump(mode="json")}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/zones/override/{zone_id}")
async def clear_override(zone_id: str):
    """Remove an active override from a zone."""
    cleared = await override_manager.clear_override(zone_id)
    if not cleared:
        raise HTTPException(status_code=404, detail="No active override for this zone")
    return {"status": "override_cleared", "zone_id": zone_id}


@router.get("/zones/overrides")
async def list_overrides():
    """List all active overrides."""
    return {
        "overrides": [o.model_dump(mode="json") for o in override_manager.all_overrides()],
        "audit_log": override_manager.audit_log,
    }


# ── Automation control ───────────────────────────────────────

@router.post("/zones/automation/enable")
async def enable_automation(req: AutomationToggle):
    hvac_controller.set_zone_enabled(req.zone_id, True)
    return {"status": "enabled", "zone_id": req.zone_id}


@router.post("/zones/automation/disable")
async def disable_automation(req: AutomationToggle):
    hvac_controller.set_zone_enabled(req.zone_id, False)
    return {"status": "disabled", "zone_id": req.zone_id}


@router.get("/zones/{zone_id}/automation")
async def zone_automation_state(zone_id: str):
    """Get the full automation state for a zone."""
    state = hvac_controller.get_zone_state(zone_id)
    if not state:
        raise HTTPException(status_code=404, detail="Zone not found")
    override = override_manager.get_override(zone_id)
    alerts = alert_engine.zone_alerts(zone_id)
    energy = hvac_controller.get_energy_summary(zone_id)
    return {
        "zone_id": zone_id,
        "enabled": state.enabled,
        "setpoint": state.setpoint,
        "fan_speed": state.fan_speed.value,
        "mode": state.mode.value,
        "airflow_pct": state.airflow_pct,
        "ventilation_pct": state.ventilation_pct,
        "action_count": state.action_count,
        "override": override.model_dump(mode="json") if override else None,
        "active_alerts": [a.model_dump(mode="json") for a in alerts],
        "energy": energy,
    }


# ── Alerts ───────────────────────────────────────────────────

@router.get("/alerts")
async def get_alerts():
    return {
        "active": [a.model_dump(mode="json") for a in alert_engine.active_alerts],
        "recent_history": [a.model_dump(mode="json") for a in alert_engine.history],
        "status": alert_engine.status(),
    }


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    resolved = alert_engine.resolve(alert_id)
    if not resolved:
        raise HTTPException(status_code=404, detail="Alert not found or already resolved")
    return {"status": "resolved", "alert_id": alert_id}


@router.post("/alerts/resolve-zone/{zone_id}")
async def resolve_zone_alerts(zone_id: str):
    count = alert_engine.resolve_zone(zone_id)
    return {"status": "resolved", "zone_id": zone_id, "count": count}


# ── Energy ───────────────────────────────────────────────────

@router.get("/energy/optimization")
async def energy_optimization():
    summaries = []
    for zone_id in list(hvac_controller.get_all_states().keys()):
        summaries.append(hvac_controller.get_energy_summary(zone_id))
    total_kwh = sum(s.get("total_kwh", 0) for s in summaries)
    total_baseline = sum(s.get("baseline_kwh", 0) for s in summaries)
    savings = ((total_baseline - total_kwh) / total_baseline * 100) if total_baseline > 0 else 0
    return {
        "zones": summaries,
        "total_kwh": round(total_kwh, 3),
        "total_baseline_kwh": round(total_baseline, 3),
        "overall_savings_pct": round(savings, 1),
    }


# ── Automation status ────────────────────────────────────────

@router.get("/automation/status")
async def automation_status():
    return {
        "hvac_controller": {
            "zones_managed": len(hvac_controller.get_all_states()),
            "recent_actions": hvac_controller.recent_actions[-5:],
        },
        "alert_engine": alert_engine.status(),
        "workflow_engine": workflow_engine.status(),
        "scheduler": automation_scheduler.status(),
        "overrides_active": len(override_manager.all_overrides()),
    }


# ── Workflow history ─────────────────────────────────────────

@router.get("/automation/workflows")
async def workflow_history():
    return {
        "recent": workflow_engine.recent_history,
        "status": workflow_engine.status(),
    }
