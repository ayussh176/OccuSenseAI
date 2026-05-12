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
