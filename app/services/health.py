import time
import logging
from app.core.schema import create_success_response, create_error_response, BaseResponse

logger = logging.getLogger(__name__)

def health() -> BaseResponse:
    try:
        """
        You can add more complex health checks here such as checking database connectivity.
        """
        return create_success_response(message="Service is healthy", data={"timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return create_error_response(message=str(e))
