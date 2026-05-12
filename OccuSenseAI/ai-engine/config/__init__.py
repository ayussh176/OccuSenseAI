from functools import lru_cache
from config.settings import Settings

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
__all__ = ["get_settings", "settings", "Settings"]
