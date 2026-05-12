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
