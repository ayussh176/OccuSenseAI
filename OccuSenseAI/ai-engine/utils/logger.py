import sys
from loguru import logger
import contextvars
from config import settings

request_trace_id = contextvars.ContextVar("request_trace_id", default="")

logger.remove()
logger.add(sys.stdout, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")

if settings.environment == "prod":
    logger.add("logs/occusense.log", rotation="500 MB", format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}")
