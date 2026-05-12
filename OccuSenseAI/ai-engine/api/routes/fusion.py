from fastapi import APIRouter

router = APIRouter(prefix="/fusion", tags=["Fusion"])

@router.get("/status")
async def fusion_status():
    return {"status": "fusion active"}
    
@router.get("/{zone_id}/state")
async def fusion_zone_state(zone_id: str):
    return {"zone_id": zone_id, "state": "healthy", "comfort_score": 0.85}
