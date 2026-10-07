"""
Pydantic Schemas for Building Management & Historical Telemetry APIs
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class BuildingBase(BaseModel):
    name: str = Field(..., description="Building display name", examples=["Hog Betsy Office Tower"])
    building_type: str = Field(default="Office", description="Building sector / category", examples=["Office"])
    total_area_sqm: Optional[float] = Field(default=None, description="Total gross floor area in m2", examples=[12500.0])
    location: Optional[str] = Field(default=None, description="City or facility campus", examples=["Hanoi, Vietnam"])
    timezone: str = Field(default="UTC", description="Local timezone identifier", examples=["Asia/Ho_Chi_Minh"])


class BuildingCreate(BuildingBase):
    id: str = Field(..., description="Unique alphanumeric building code", examples=["office_tower_01"])


class BuildingResponse(BuildingBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BuildingListResponse(BaseModel):
    total: int = Field(..., description="Total count of registered buildings")
    buildings: List[BuildingResponse]


class HistoricalReadingPoint(BaseModel):
    timestamp: datetime
    meter_reading_kwh: float
    outdoor_temperature_c: Optional[float] = None
    relative_humidity_pct: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class BuildingHistoryResponse(BaseModel):
    building_id: str
    count: int
    data: List[HistoricalReadingPoint]
