# Pydantic Models

from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import time

class TimezoneResponse(BaseModel):
    timezone: str

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    latitude: float = 52.52      # Optional, Default Berlin
    longitude: float = 13.40

class User(BaseModel):
    id: int
    email: EmailStr
    latitude: float 
    longitude: float

    class Config:
        orm_mode = True

class UserUpdate(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class PasswordChange(BaseModel):
    old_password: str
    new_password: str

class RoomCreate(BaseModel):
    name: str

class Room(BaseModel):
    id: int
    name: str
    user_id: int

class RoomSettings(BaseModel):
    timezone: str
    wanted_temp_day: float
    wanted_temp_night: float
    night_start: time
    night_end: time

class TemperatureEntry(BaseModel):
    room_id: int
    temperature: float

class TemperatureResponse(BaseModel):
    time: str
    value: float
    room_id: int

class HeatingStatusResponse(BaseModel):
    heating_on: bool

class TemperatureEntryBatch(BaseModel):
    room_id: int
    temperatures: list[float] 
    timestamps: Optional[list[str]] = None

class CitySearchResult(BaseModel):
    display_name: str
    latitude: float
    longitude: float
    
class CitySearchResults(BaseModel):
    results: List[CitySearchResult]

class WeatherResponse(BaseModel):
    temperature: float
    weather_condition: str
    location: str
    timestamp: str