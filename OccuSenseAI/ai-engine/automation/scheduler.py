# ============================================================
# OccuSense AI — Automation Scheduler
# ============================================================
# Uses APScheduler to run periodic automation jobs:
#   - Nightly HVAC relaxation
#   - Morning pre-cooling
#   - Hourly energy analysis
#   - Override expiry sweeps
#   - Anomaly scans
# ============================================================

from __future__ import annotations
import asyncio
from datetime import datetime
from typing import Any, Dict
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from automation.hvac_controller import hvac_controller
from automation.override_manager import override_manager
from streaming.event_bus import EventChannel, bus
from utils.logger import logger


class AutomationScheduler:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._started = False
        self._job_log: list = []

    async def start(self) -> None:
        """Register all recurring jobs and start the scheduler."""
        # Every 60s — sweep expired overrides
        self._scheduler.add_job(
            self._sweep_overrides, IntervalTrigger(seconds=60),
            id="sweep_overrides", replace_existing=True,
        )

        # Every 5 min — energy analysis broadcast
        self._scheduler.add_job(
            self._energy_analysis, IntervalTrigger(minutes=5),
            id="energy_analysis", replace_existing=True,
        )

        # Nightly 11pm — relax all zones to energy-saver
        self._scheduler.add_job(
            self._nightly_relaxation, CronTrigger(hour=23, minute=0),
            id="nightly_relaxation", replace_existing=True,
        )

        # Morning 6am — pre-cool all zones
        self._scheduler.add_job(
            self._morning_precool, CronTrigger(hour=6, minute=0),
            id="morning_precool", replace_existing=True,
        )

        # Hourly — automation status broadcast
        self._scheduler.add_job(
            self._status_broadcast, IntervalTrigger(minutes=60),
            id="status_broadcast", replace_existing=True,
        )

        self._scheduler.start()
        self._started = True
        logger.info("AutomationScheduler started with 5 recurring jobs")

    async def stop(self) -> None:
        if self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False
            logger.info("AutomationScheduler stopped")

    # ── Scheduled jobs ───────────────────────────────────────

    async def _sweep_overrides(self) -> None:
        cleared = await override_manager.sweep_expired()
        if cleared:
            logger.info(f"Scheduler: swept {cleared} expired overrides")
            self._log("sweep_overrides", {"cleared": cleared})

    async def _energy_analysis(self) -> None:
        summaries = []
        for zone_id in list(hvac_controller.get_all_states().keys()):
            summary = hvac_controller.get_energy_summary(zone_id)
            summaries.append(summary)
        await bus.publish(EventChannel.ENERGY_UPDATE, {
            "type": "periodic_analysis",
            "zones": summaries,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self._log("energy_analysis", {"zones_analysed": len(summaries)})

    async def _nightly_relaxation(self) -> None:
        """Relax all non-overridden zones to energy-saving mode."""
        count = 0
        for zone_id, state in hvac_controller.get_all_states().items():
            if not override_manager.is_overridden(zone_id):
                await hvac_controller.evaluate({
                    "zone_id": zone_id, "co2_ppm": 400, "temperature_c": 22,
                    "humidity": 45, "comfort_score": 80, "estimated_count": 0,
                    "occupancy_trend": "stable",
                })
                count += 1
        logger.info(f"Nightly relaxation applied to {count} zones")
        self._log("nightly_relaxation", {"zones": count})

    async def _morning_precool(self) -> None:
        """Pre-cool all zones before morning occupancy arrives."""
        count = 0
        for zone_id, state in hvac_controller.get_all_states().items():
            if not override_manager.is_overridden(zone_id):
                await hvac_controller.evaluate({
                    "zone_id": zone_id, "co2_ppm": 420, "temperature_c": 25,
                    "humidity": 50, "comfort_score": 70, "estimated_count": 5,
                    "occupancy_trend": "increasing",
                })
                count += 1
        logger.info(f"Morning pre-cool applied to {count} zones")
        self._log("morning_precool", {"zones": count})

    async def _status_broadcast(self) -> None:
        await bus.publish(EventChannel.AUTOMATION_STATUS, {
            "scheduler_running": self._started,
            "timestamp": datetime.utcnow().isoformat(),
        })

    # ── Helpers ──────────────────────────────────────────────

    def _log(self, job: str, data: Dict[str, Any]) -> None:
        self._job_log.append({"job": job, "data": data,
                              "timestamp": datetime.utcnow().isoformat()})
        if len(self._job_log) > 200:
            self._job_log = self._job_log[-200:]

    def status(self) -> Dict[str, Any]:
        jobs = []
        if self._started:
            for job in self._scheduler.get_jobs():
                jobs.append({"id": job.id, "next_run": str(job.next_run_time)})
        return {"started": self._started, "jobs": jobs,
                "recent_log": self._job_log[-10:]}


automation_scheduler = AutomationScheduler()
