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
