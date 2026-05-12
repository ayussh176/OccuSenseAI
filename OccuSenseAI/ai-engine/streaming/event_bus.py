# ============================================================
# OccuSense AI — Event Bus (Extended for Phase 5)
# ============================================================
# In-process async pub/sub system. Every subsystem communicates
# through named channels. Handlers are fire-and-forget tasks
# wrapped in error boundaries so one bad handler cannot crash
# the bus.
# ============================================================

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine, Dict, List
from utils.logger import logger


# ── Channel constants ────────────────────────────────────────

class EventChannel:
    """Well-known channel names used across the platform."""

    # Phase 2 — Simulation
    ZONE_UPDATE = "zone_update"

    # Phase 4 — Sensor Fusion
    ENVIRONMENT_UPDATE = "environment_update"
    COMFORT_UPDATE = "comfort_update"
    ANOMALY_ALERT = "anomaly_alert"

    # Phase 5 — HVAC Automation
    HVAC_ACTION = "hvac_action"
    OVERRIDE_EVENT = "override_event"
    ALERT_EVENT = "alert_event"
    WORKFLOW_EVENT = "workflow_event"
    ENERGY_UPDATE = "energy_update"
    AUTOMATION_STATUS = "automation_status"


# ── Bus implementation ───────────────────────────────────────

Handler = Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]


class EventBus:
    """Lightweight async pub/sub for intra-process event routing."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Handler]] = {}
        self._event_count: int = 0

    # ── Public API ───────────────────────────────────────────

    def subscribe(self, channel: str, handler: Handler) -> None:
        """Register *handler* to be called whenever *channel* fires."""
        if channel not in self._subscribers:
            self._subscribers[channel] = []
        self._subscribers[channel].append(handler)
        logger.debug(f"EventBus: subscribed {handler.__qualname__} -> {channel}")

    async def publish(self, channel: str, data: Dict[str, Any]) -> None:
        """Broadcast *data* to every handler registered on *channel*."""
        self._event_count += 1
        handlers = self._subscribers.get(channel, [])
        for handler in handlers:
            asyncio.create_task(self._safe_dispatch(channel, handler, data))

    # ── Internals ────────────────────────────────────────────

    async def _safe_dispatch(
        self, channel: str, handler: Handler, data: Dict[str, Any]
    ) -> None:
        """Run a single handler inside a try/except so failures are logged
        but never propagate to the publisher."""
        try:
            await handler(data)
        except Exception as exc:
            logger.error(
                f"EventBus handler error on '{channel}' "
                f"({handler.__qualname__}): {exc}"
            )

    # ── Diagnostics ──────────────────────────────────────────

    @property
    def total_events(self) -> int:
        return self._event_count

    @property
    def channel_stats(self) -> Dict[str, int]:
        return {ch: len(hs) for ch, hs in self._subscribers.items()}


# Module-level singleton
bus = EventBus()
