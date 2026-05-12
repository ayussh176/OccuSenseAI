import os

files = {}

# ==============================================================================
# PHASE 1: FOUNDATION
# ==============================================================================

files["config/__init__.py"] = """
from functools import lru_cache
from config.settings import Settings

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
__all__ = ["get_settings", "settings", "Settings"]
"""

files["config/settings.py"] = """
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Literal

class Settings(BaseSettings):
    app_name: str = "OccuSense AI API"
    environment: Literal["dev", "prod", "test"] = "dev"
    log_level: str = "INFO"
    
    redis_url: str = "redis://localhost:6379/0"
    influxdb_url: str = "http://localhost:8086"
    influxdb_token: str = "token"
    influxdb_org: str = "occusense"
    influxdb_bucket: str = "sensors"
    
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    
    # Fusion Alerts
    ALERT_CO2_CRITICAL: float = 1200.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
"""

files["models/__init__.py"] = """
from .schemas import SensorReading, OccupancyState, SystemMetrics
"""

files["models/schemas.py"] = """
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any, List

class SensorReading(BaseModel):
    zone_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    co2_ppm: float
    temperature_c: float
    humidity: float
    light_level: float
    noise_db: float
    
class OccupancyState(BaseModel):
    zone_id: str
    estimated_count: int
    confidence: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
class SystemMetrics(BaseModel):
    cpu_usage: float
    memory_usage: float
    active_connections: int
"""

files["utils/__init__.py"] = """
from .logger import logger, request_trace_id
"""

files["utils/logger.py"] = """
import sys
from loguru import logger
import contextvars
from config import settings

request_trace_id = contextvars.ContextVar("request_trace_id", default="")

logger.remove()
logger.add(sys.stdout, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")

if settings.environment == "prod":
    logger.add("logs/occusense.log", rotation="500 MB", format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}")
"""

files["utils/metrics.py"] = """
from typing import Dict
import time

class MetricsStore:
    def __init__(self):
        self.counters: Dict[str, int] = {}
        self.histograms: Dict[str, list] = {}
        
    def inc(self, metric: str, amount: int = 1):
        self.counters[metric] = self.counters.get(metric, 0) + amount
        
    def observe(self, metric: str, value: float):
        if metric not in self.histograms:
            self.histograms[metric] = []
        self.histograms[metric].append(value)
        if len(self.histograms[metric]) > 1000:
            self.histograms[metric] = self.histograms[metric][-1000:]

metrics = MetricsStore()
"""

files["api/middleware/__init__.py"] = """
from .request_logger import RequestMetricsMiddleware
from .error_handler import custom_exception_handler
"""

files["api/middleware/request_logger.py"] = """
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
import time
from utils.logger import logger, request_trace_id
import uuid

class RequestMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = str(uuid.uuid4())
        request_trace_id.set(trace_id)
        start_time = time.time()
        
        response = await call_next(request)
        
        process_time = time.time() - start_time
        logger.info(f"[{trace_id}] {request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
        return response
"""

files["api/middleware/error_handler.py"] = """
from fastapi import Request
from fastapi.responses import JSONResponse
from utils.logger import logger

async def custom_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error: {exc}")
    return JSONResponse(status_code=500, content={"message": str(exc), "status": "error"})
"""

files["api/routes/__init__.py"] = """
from .system import router as system_router
from .simulate import router as simulate_router
from .streaming import router as streaming_router
from .fusion import router as fusion_router
from .sensors import router as sensors_router
"""

files["api/routes/system.py"] = """
from fastapi import APIRouter
from config import settings

router = APIRouter(prefix="/system", tags=["System"])

@router.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}

@router.get("/metrics")
async def get_metrics():
    return {"status": "ok", "metrics": {}}
"""

files["api/routes/sensors.py"] = """
from fastapi import APIRouter

router = APIRouter(prefix="/sensors", tags=["Sensors"])

@router.get("/status")
async def sensor_status():
    return {"status": "ok"}
"""

# ==============================================================================
# PHASE 2: SIMULATION
# ==============================================================================

files["simulation/orchestrator.py"] = """
import asyncio
from utils.logger import logger

class SimulationOrchestrator:
    def __init__(self):
        self.running = False
        self.zones = ["zone_1", "zone_2", "zone_3", "zone_4"]
        
    async def start(self):
        self.running = True
        logger.info("Simulation orchestrator started")
        asyncio.create_task(self._loop())
        
    async def stop(self):
        self.running = False
        logger.info("Simulation orchestrator stopped")
        
    async def _loop(self):
        while self.running:
            # Emit tick
            await asyncio.sleep(5)
"""

files["api/routes/simulate.py"] = """
from fastapi import APIRouter

router = APIRouter(prefix="/simulate", tags=["Simulation"])
from simulation.orchestrator import SimulationOrchestrator

orchestrator = SimulationOrchestrator()

@router.post("/start")
async def start_sim():
    await orchestrator.start()
    return {"status": "started"}

@router.post("/stop")
async def stop_sim():
    await orchestrator.stop()
    return {"status": "stopped"}
"""

# ==============================================================================
# PHASE 3: STREAMING
# ==============================================================================

files["streaming/event_bus.py"] = """
import asyncio
from typing import Callable, Dict, List
from utils.logger import logger

class EventChannel:
    ZONE_UPDATE = "zone_update"
    ENVIRONMENT_UPDATE = "environment_update"
    COMFORT_UPDATE = "comfort_update"
    ANOMALY_ALERT = "anomaly_alert"

class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        
    def subscribe(self, channel: str, handler: Callable):
        if channel not in self._subscribers:
            self._subscribers[channel] = []
        self._subscribers[channel].append(handler)
        
    async def publish(self, channel: str, data: dict):
        if channel in self._subscribers:
            for handler in self._subscribers[channel]:
                asyncio.create_task(handler(data))

bus = EventBus()
"""

files["streaming/pipeline.py"] = """
from utils.logger import logger

class PipelineManager:
    async def initialize(self):
        logger.info("Streaming pipeline initialized")
"""

files["api/routes/streaming.py"] = """
from fastapi import APIRouter, WebSocket

router = APIRouter(prefix="/stream", tags=["Streaming"])

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Message text was: {data}")
"""

# ==============================================================================
# PHASE 4: SENSOR FUSION
# ==============================================================================

files["sensor_fusion/fusion_pipeline.py"] = """
from streaming.event_bus import bus, EventChannel
from utils.logger import logger

class SensorFusionPipeline:
    def __init__(self):
        pass
        
    async def start(self):
        bus.subscribe(EventChannel.ZONE_UPDATE, self._process_zone_event)
        logger.info("Sensor Fusion Pipeline started")
        
    async def _process_zone_event(self, data: dict):
        # Process and emit fusion events
        await bus.publish(EventChannel.ENVIRONMENT_UPDATE, {"zone": data.get("zone"), "status": "fused"})
        
fusion_pipeline = SensorFusionPipeline()
"""

files["api/routes/fusion.py"] = """
from fastapi import APIRouter

router = APIRouter(prefix="/fusion", tags=["Fusion"])

@router.get("/status")
async def fusion_status():
    return {"status": "fusion active"}
    
@router.get("/{zone_id}/state")
async def fusion_zone_state(zone_id: str):
    return {"zone_id": zone_id, "state": "healthy", "comfort_score": 0.85}
"""

files["sensor_fusion/co2_processor.py"] = """
class CO2Processor:
    def __init__(self):
        self.history = {}
"""

files["sensor_fusion/occupancy_estimator.py"] = """
class OccupancyEstimator:
    def __init__(self):
        self.history = {}
"""

files["sensor_fusion/environment_state.py"] = """
class EnvironmentStateManager:
    def __init__(self):
        self.history = {}
"""

# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================

files["main.py"] = """
import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager

from config import settings
from utils.logger import logger
from api.middleware.request_logger import RequestMetricsMiddleware
from api.middleware.error_handler import custom_exception_handler
from api.routes import system_router, simulate_router, streaming_router, fusion_router, sensors_router
from simulation.orchestrator import SimulationOrchestrator
from streaming.pipeline import PipelineManager
from sensor_fusion.fusion_pipeline import fusion_pipeline

sim_orchestrator = SimulationOrchestrator()
pipeline_manager = PipelineManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.app_name} in {settings.environment} mode")
    await pipeline_manager.initialize()
    await fusion_pipeline.start()
    await sim_orchestrator.start()
    yield
    logger.info("Shutting down OccuSense AI")
    await sim_orchestrator.stop()

app = FastAPI(title="OccuSense AI", lifespan=lifespan)

app.add_middleware(RequestMetricsMiddleware)
app.add_exception_handler(Exception, custom_exception_handler)

app.include_router(system_router)
app.include_router(simulate_router)
app.include_router(streaming_router)
app.include_router(fusion_router)
app.include_router(sensors_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
"""

for path, content in files.items():
    full_path = os.path.join(r"d:\promptathon\OccuSenseAI\ai-engine", path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")
        
print("Re-generated AI Engine Core.")
