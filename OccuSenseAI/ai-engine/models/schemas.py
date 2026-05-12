# ============================================================
# OccuSense AI — Domain Schemas (Pydantic v2)
# ============================================================
# Every data contract in the system is defined here.
# These models power API validation, event serialization,
# database persistence, and WebSocket payloads.
# ============================================================

from __future__ import annotations

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum


# ── Enums ────────────────────────────────────────────────────

class FanSpeed(str, Enum):
    OFF = "off"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"


class HVACMode(str, Enum):
    OFF = "off"
    COOLING = "cooling"
    HEATING = "heating"
    VENTILATION = "ventilation"
    AUTO = "auto"
    ENERGY_SAVER = "energy_saver"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertType(str, Enum):
    HIGH_CO2 = "high_co2"
    CRITICAL_CO2 = "critical_co2"
    OVERHEATING = "overheating"
    OVERCOOLING = "overcooling"
    HIGH_HUMIDITY = "high_humidity"
    OCCUPANCY_SURGE = "occupancy_surge"
    SENSOR_ANOMALY = "sensor_anomaly"
    HVAC_INEFFICIENCY = "hvac_inefficiency"
    EXCESSIVE_ENERGY = "excessive_energy"
    COMFORT_DEGRADATION = "comfort_degradation"


class OverridePriority(str, Enum):
    USER = "user"
    FACILITY_MANAGER = "facility_manager"
    EMERGENCY = "emergency"


# ── Sensor Data ──────────────────────────────────────────────

class SensorReading(BaseModel):
    zone_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    co2_ppm: float = Field(ge=0, le=10000)
    temperature_c: float = Field(ge=-40, le=80)
    humidity: float = Field(ge=0, le=100)
    light_level: float = Field(ge=0, default=300.0)
    noise_db: float = Field(ge=0, default=40.0)


class OccupancyState(BaseModel):
    zone_id: str
    estimated_count: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    trend: str = "stable"  # "increasing" | "decreasing" | "stable"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── HVAC Actions ─────────────────────────────────────────────

class HVACAction(BaseModel):
    """Represents a single HVAC control decision for a zone."""
    zone_id: str
    setpoint: float = Field(ge=18.0, le=28.0, description="Target temperature °C")
    fan_speed: FanSpeed = FanSpeed.MEDIUM
    mode: HVACMode = HVACMode.AUTO
    airflow_pct: float = Field(ge=0, le=100, default=50.0)
    ventilation_pct: float = Field(ge=0, le=100, default=50.0)
    reason: str = "automation"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    energy_estimate_kwh: float = Field(ge=0, default=0.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)


# ── Alert ────────────────────────────────────────────────────

class Alert(BaseModel):
    """Structured alert emitted by the alert engine."""
    alert_id: str
    zone_id: str
    severity: AlertSeverity
    alert_type: AlertType
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ── Override ─────────────────────────────────────────────────

class Override(BaseModel):
    """Manual HVAC override placed by an operator."""
    zone_id: str
    override_active: bool = True
    locked_setpoint: float = Field(ge=18.0, le=28.0)
    locked_fan_speed: Optional[FanSpeed] = None
    locked_mode: Optional[HVACMode] = None
    priority: OverridePriority = OverridePriority.USER
    reason: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


# ── Workflow ─────────────────────────────────────────────────

class WorkflowEvent(BaseModel):
    """Tracks one execution of the automation workflow pipeline."""
    workflow_id: str
    zone_id: str
    trigger: str
    steps_completed: List[str] = Field(default_factory=list)
    hvac_action: Optional[HVACAction] = None
    alerts_generated: int = 0
    duration_ms: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Energy ───────────────────────────────────────────────────

class EnergySnapshot(BaseModel):
    """Per-zone energy optimization metrics."""
    zone_id: str
    current_kwh: float = 0.0
    baseline_kwh: float = 0.0
    savings_pct: float = 0.0
    cooling_efficiency: float = 0.0
    runtime_hours: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── System ───────────────────────────────────────────────────

class SystemMetrics(BaseModel):
    cpu_usage: float
    memory_usage: float
    active_connections: int
