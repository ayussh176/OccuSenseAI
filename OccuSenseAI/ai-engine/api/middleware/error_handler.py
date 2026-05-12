from fastapi import Request
from fastapi.responses import JSONResponse
from utils.logger import logger

async def custom_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error: {exc}")
    return JSONResponse(status_code=500, content={"message": str(exc), "status": "error"})
