# ============================================================
# OccuSense AI — Workflow Engine
# ============================================================
# Orchestrates the full automation pipeline:
#   Sensor Event → Environment Analysis → Rule Evaluation
#   → HVAC Decision → Alert Evaluation → Action Execution
#   → Broadcast Update → Persist State
# ============================================================

from __future__ import annotations
import time, uuid
from typing import Any, Dict, List, Optional
from models.schemas import HVACAction, WorkflowEvent
from automation.hvac_controller import hvac_controller
from automation.alert_engine import alert_engine
from automation.override_manager import override_manager
from streaming.event_bus import EventChannel, bus
from utils.logger import logger
from utils.metrics import metrics


class WorkflowEngine:
    """
    Consumes ENVIRONMENT_UPDATE events from the fusion pipeline and
    runs the full automation workflow for each zone.
    """

    def __init__(self) -> None:
        self._running = False
        self._workflow_count = 0
        self._history: List[Dict[str, Any]] = []

    async def start(self) -> None:
        bus.subscribe(EventChannel.ENVIRONMENT_UPDATE, self._on_environment)
        self._running = True
        logger.info("WorkflowEngine started — listening on ENVIRONMENT_UPDATE")

    async def stop(self) -> None:
        self._running = False
        logger.info("WorkflowEngine stopped")

    async def _on_environment(self, data: Dict[str, Any]) -> None:
        """Run the full automation pipeline for one environmental event."""
        if not self._running:
            return

        t0 = time.perf_counter()
        zone_id = data.get("zone_id", data.get("zone", "unknown"))
        wf_id = f"wf_{uuid.uuid4().hex[:10]}"
        steps: List[str] = []
        alerts_generated = 0

        # ── Step 1: Environment Analysis ─────────────────────
        steps.append("environment_analysis")
        env_state = self._build_env_snapshot(data)

        # ── Step 2: Override Check ───────────────────────────
        steps.append("override_check")
        if override_manager.is_overridden(zone_id):
            ov = override_manager.get_override(zone_id)
            logger.debug(f"WF {wf_id}: {zone_id} is overridden — skipping automation")
            steps.append("override_active_skip")
            await self._record_workflow(wf_id, zone_id, "override_active", steps, None, 0, t0)
            return

        # ── Step 3: Rule Evaluation → HVAC Decision ──────────
        steps.append("rule_evaluation")
        action: Optional[HVACAction] = await hvac_controller.evaluate(env_state)
        steps.append("hvac_decision")

        # ── Step 4: Alert Evaluation ─────────────────────────
        # Alerts are already fired reactively by AlertEngine's own
        # subscriptions, but we track them for workflow completeness.
        steps.append("alert_evaluation")
        active = alert_engine.zone_alerts(zone_id)
        alerts_generated = len(active)

        # ── Step 5: Action Execution (already done in evaluate) ──
        steps.append("action_executed")

        # ── Step 6: Broadcast workflow event ─────────────────
        steps.append("broadcast")
        wf_event = WorkflowEvent(
            workflow_id=wf_id,
            zone_id=zone_id,
            trigger="environment_update",
            steps_completed=steps,
            hvac_action=action,
            alerts_generated=alerts_generated,
            duration_ms=round((time.perf_counter() - t0) * 1000, 2),
        )
        await bus.publish(EventChannel.WORKFLOW_EVENT, wf_event.model_dump(mode="json"))

        # ── Step 7: Persist state ────────────────────────────
        steps.append("persist")
        await self._record_workflow(wf_id, zone_id, "environment_update",
                                    steps, action, alerts_generated, t0)

        self._workflow_count += 1
        metrics.inc("workflows_total")

    def _build_env_snapshot(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise raw event data into the format HVACController expects."""
        return {
            "zone_id": data.get("zone_id", data.get("zone", "unknown")),
            "co2_ppm": data.get("co2_ppm", 420.0),
            "temperature_c": data.get("temperature_c", 22.0),
            "humidity": data.get("humidity", 45.0),
            "comfort_score": data.get("comfort_score", 80.0),
            "estimated_count": data.get("estimated_count", 0),
            "occupancy_trend": data.get("occupancy_trend", data.get("trend", "stable")),
            "noise_db": data.get("noise_db", 40.0),
            "light_level": data.get("light_level", 300.0),
        }

    async def _record_workflow(
        self, wf_id: str, zone_id: str, trigger: str,
        steps: List[str], action: Optional[HVACAction],
        alerts: int, t0: float,
    ) -> None:
        elapsed = round((time.perf_counter() - t0) * 1000, 2)
        entry = {
            "workflow_id": wf_id, "zone_id": zone_id,
            "trigger": trigger, "steps": steps,
            "action": action.model_dump(mode="json") if action else None,
            "alerts_generated": alerts, "duration_ms": elapsed,
        }
        self._history.append(entry)
        if len(self._history) > 300:
            self._history = self._history[-300:]
        metrics.observe("workflow_ms", elapsed)

    # ── Diagnostics ──────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "total_workflows": self._workflow_count,
            "recent_history_size": len(self._history),
        }

    @property
    def recent_history(self) -> List[Dict[str, Any]]:
        return list(self._history[-20:])


workflow_engine = WorkflowEngine()
