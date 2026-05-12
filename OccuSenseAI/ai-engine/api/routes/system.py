from fastapi import APIRouter
from config import settings

router = APIRouter(prefix="/system", tags=["System"])

@router.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}

@router.get("/metrics")
async def get_metrics():
    return {"status": "ok", "metrics": {}}
