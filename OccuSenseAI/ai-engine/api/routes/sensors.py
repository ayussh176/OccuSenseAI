from fastapi import APIRouter

router = APIRouter(prefix="/sensors", tags=["Sensors"])

@router.get("/status")
async def sensor_status():
    return {"status": "ok"}
