# ============================================================
# OccuSense AI — Application Entrypoint
# ============================================================

import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager

from config import settings
from utils.logger import logger
from api.middleware.request_logger import RequestMetricsMiddleware
from api.middleware.error_handler import custom_exception_handler
from api.routes import (
    system_router, simulate_router, streaming_router,
    fusion_router, sensors_router, ai_router, automation_router,
)
from simulation.orchestrator import SimulationOrchestrator
from streaming.pipeline import PipelineManager
from sensor_fusion.fusion_pipeline import fusion_pipeline
from automation.alert_engine import alert_engine
from automation.workflow_engine import workflow_engine
from automation.scheduler import automation_scheduler

sim_orchestrator = SimulationOrchestrator()
pipeline_manager = PipelineManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.app_name} in {settings.environment} mode")

    # Phase 3 — streaming infrastructure
    await pipeline_manager.initialize()

    # Phase 4 — sensor fusion
    await fusion_pipeline.start()

    # Phase 5 — automation brain
    await alert_engine.start()
    await workflow_engine.start()
    await automation_scheduler.start()

    # Phase 2 — simulation (start last so automation is ready to consume)
    await sim_orchestrator.start()

    logger.info("All subsystems online")
    yield

    # Graceful shutdown
    logger.info("Shutting down OccuSense AI")
    await sim_orchestrator.stop()
    await workflow_engine.stop()
    await automation_scheduler.stop()


app = FastAPI(
    title="OccuSense AI",
    description="AI-powered HVAC optimisation & comfort intelligence platform",
    version="0.5.0",
    lifespan=lifespan,
)

app.add_middleware(RequestMetricsMiddleware)
app.add_exception_handler(Exception, custom_exception_handler)

app.include_router(system_router)
app.include_router(simulate_router)
app.include_router(streaming_router)
app.include_router(fusion_router)
app.include_router(sensors_router)
app.include_router(ai_router)
app.include_router(automation_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
