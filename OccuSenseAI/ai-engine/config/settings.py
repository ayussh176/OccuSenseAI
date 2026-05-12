from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Literal

class Settings(BaseSettings):
    app_name: str = "OccuSense AI API"
    environment: Literal["dev", "prod", "test", "development"] = "dev"
    log_level: str = "INFO"
    
    redis_url: str = "redis://localhost:6379/0"
    influxdb_url: str = "http://localhost:8086"
    influxdb_token: str = "token"
    influxdb_org: str = "occusense"
    influxdb_bucket: str = "sensors"
    
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    
    # Fusion Alerts
    ALERT_CO2_CRITICAL: float = 1200.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
