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
