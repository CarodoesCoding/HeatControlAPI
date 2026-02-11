import os
import requests
from fastapi import FastAPI, Depends, HTTPException, status, Query, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from timezonefinder import TimezoneFinder
from typing import Optional, List
from models import (
    UserCreate, User, UserUpdate, PasswordChange, RoomCreate, Room, RoomSettings,
    TemperatureEntry, TemperatureEntryBatch, TemperatureResponse, WeatherResponse, 
    CitySearchResult, CitySearchResults, HeatingStatusResponse, TimezoneResponse
)
from database import MySQLClient
from test_import import import_csv_if_needed
from influxdb_client import InfluxDBClient, Point, WriteOptions
from functools import lru_cache
import asyncio


# Environment variables
INFLUX_URL = str(os.getenv("INFLUX_URL"))
INFLUX_TOKEN = str(os.getenv("INFLUX_TOKEN"))
INFLUX_ORG = str(os.getenv("INFLUX_ORG"))
INFLUX_BUCKET = str(os.getenv("INFLUX_BUCKET"))
SECRET_KEY = str(os.getenv("SECRET_KEY"))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

WEATHER_API = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODES = {
    0: "Clear Sky",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Foggy",
    51: "Light Drizzle",
    53: "Moderate Drizzle",
    55: "Dense Drizzle",
    61: "Slight Rain",
    63: "Moderate Rain",
    65: "Heavy Rain",
    71: "Slight Snow",
    73: "Moderate Snow",
    75: "Heavy Snow",
    77: "Snow Grains",
    80: "Slight Showers",
    81: "Moderate Showers",
    82: "Violent Showers",
    85: "Slight Snow Showers",
    86: "Heavy Snow Showers",
    95: "Thunderstorm",
    96: "Thunderstorm with Hail",
    99: "Thunderstorm with Hail"
}

# Setup
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = influx_client.write_api(write_options=WriteOptions(batch_size=1))
db = MySQLClient()
app = FastAPI(title="Heating Regulation API")

#Limiting Requests
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ============ WEATHER BACKGROUND TASK ============
async def fetch_and_store_weather_data():
    """Background task to fetch and store weather data every 30 minutes"""
    while True:
        try:
            users = db.execute_query("SELECT id, latitude, longitude FROM users")
            if users:
                for user in users:
                    try:
                        response = requests.get(
                            WEATHER_API,
                            params={
                                "latitude": user["latitude"],
                                "longitude": user["longitude"],
                                "current": "temperature_2m,weather_code",
                                "timezone": "auto"
                            },
                            timeout=5
                        )
                        response.raise_for_status()
                        data = response.json()
                        current = data.get("current", {})
                        weather_temp = current.get("temperature_2m", None)

                        if weather_temp is not None:
                            timestamp = datetime.now()
                            point = (
                                Point("weather_temperature")
                                .tag("user_id", str(user["id"]))
                                .field("value", float(weather_temp))
                                .time(timestamp)
                            )
                            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
                            print(f"Weather data stored for user {user['id']}: {weather_temp}°C")
                    
                    except Exception as e:
                        print(f"Error fetching weather for user {user['id']}: {str(e)}")
            
        except Exception as e:
            print(f"Error in weather background task: {str(e)}")
        
        await asyncio.sleep(600)

# Starting the saving of the weather data when the app starts
@app.on_event("startup")
async def startup_event():
    """Start background task on app startup"""
    asyncio.create_task(fetch_and_store_weather_data())


# ============ AUTH HELPERS ============
def get_password_hash(password):
    return pwd_context.hash(password)


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_user(email: str):
    query = "SELECT id, email, hashed_password FROM users WHERE email = %s"
    rows = db.execute_query(query, (email,))
    if rows:
        row = rows[0]
        return {"id": row["id"], "email": row["email"], "hashed_password": row["hashed_password"]}
    return None


def authenticate_user(email: str, password: str):
    user = get_user(email)
    if not user:
        return False
    if not verify_password(password, user["hashed_password"]):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user(email)
    if user is None:
        raise credentials_exception
    return user



# ============ TESTDATA ============
@app.post("/import_testdata", tags=["Testdata"], summary="Import the testdata")
@limiter.limit("5/minute")  
def import_testdata(request: Request, current_user = Depends(get_current_user)):
    """Importing the Tesdtata from temperatures.csv into the database for the current user"""
    try:
        import_csv_if_needed(current_user["id"])
        return {"status": "success", "message": "Testdaten erfolgreich importiert"}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import fehlgeschlagen: {str(e)}")
    


# ============ TIMEZONE ENDPOINT ============

@app.get("/timezone", response_model=TimezoneResponse, tags=["User"], summary="Get user timezone from coordinates")
@limiter.limit("5/minute")  
async def get_user_timezone(request: Request, current_user=Depends(get_current_user)):
    """Gets timezone of user based on User-Coordinates"""
    try:
        user = db.execute_query(
            "SELECT latitude, longitude FROM users WHERE id = %s",
            (current_user["id"],)
        )[0]
        
        # Direkter Timezone-Lookup
        tf = TimezoneFinder()
        timezone = tf.timezone_at(lat=float(user["latitude"]), lng=float(user["longitude"]))
        
        return {"timezone": timezone if timezone else "UTC"}
        
    except Exception as e:
        print(f"Error getting timezone: {str(e)}")
        return {"timezone": "UTC"}




# ============ USER ENDPOINTS ============
@app.post("/register", response_model=User, tags=["User"], summary="Register a new user")
@limiter.limit("5/minute")  
def register(request: Request, user: UserCreate):
    """Registering a new user"""
    existing = db.execute_query("SELECT id FROM users WHERE email = %s", (user.email,))
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = get_password_hash(user.password)
    db.execute_query(
        "INSERT INTO users (email, hashed_password, latitude, longitude) VALUES (%s, %s, %s, %s)",
        (user.email, hashed_password, user.latitude, user.longitude), fetch=False)    
    new_user = db.execute_query(
        "SELECT id, email, latitude, longitude FROM users WHERE email = %s",
        (user.email,))[0]
    return User(id=new_user["id"],
            email=new_user["email"],
            latitude=new_user["latitude"],
            longitude=new_user["longitude"])


@app.post("/token", tags=["User"], summary="Create token for authentification")
@limiter.limit("5/minute")  
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """Creating the token for the OAuth2 authentification"""
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user["email"]})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/me", response_model=User, tags=["User"], summary="Get current user")
@limiter.limit("50/minute")  
async def get_current_user_info(request: Request, current_user=Depends(get_current_user)):
    """Get all information about the current user"""
    user = db.execute_query(
        "SELECT id, email, latitude, longitude FROM users WHERE id = %s",
        (current_user["id"],))[0]
    return User(
        id=user["id"],
        email=user["email"],
        latitude=user["latitude"],
        longitude=user["longitude"])


@app.put("/me/location", tags=["User"], summary="Update location of user")
@limiter.limit("50/minute") 
async def update_user_location(request: Request, update: UserUpdate, current_user=Depends(get_current_user)):
    """Update user location"""
    if update.latitude is not None and update.longitude is not None:
        db.execute_query(
            "UPDATE users SET latitude = %s, longitude = %s WHERE id = %s",
            (update.latitude, update.longitude, current_user["id"]),
            fetch=False
        )
        return {"message": "Location updated"}
    raise HTTPException(status_code=400, detail="latitude and longitude required")


@app.put("/me/password", tags=["User"], summary="Update password of user")
@limiter.limit("10/minute") 
async def change_password(request: Request, data: PasswordChange, current_user=Depends(get_current_user)):
    """Change password of the current user"""
    user = get_user(current_user["email"])
    
    if not verify_password(data.old_password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Old password incorrect")
    
    new_hash = get_password_hash(data.new_password)
    db.execute_query(
        "UPDATE users SET hashed_password = %s WHERE id = %s",
        (new_hash, current_user["id"]),
        fetch=False
    )
    return {"message": "Password updated successfully"}

# ============ ROOM ENDPOINTS ============
@app.post("/rooms", response_model=Room, tags=["Rooms"], summary="Add room")
@limiter.limit("10/minute")
async def create_room(request: Request, room: RoomCreate, current_user=Depends(get_current_user)):
    """Creating a new room"""
    query = "INSERT INTO rooms (user_id, name) VALUES (%s, %s)"
    try:
        db.execute_query(query, (current_user["id"], room.name), fetch=False)
        new_room = db.execute_query(
            "SELECT id, user_id, name FROM rooms WHERE user_id = %s AND name = %s",
            (current_user["id"], room.name))[0]
        
        # Füge default room_settings ein
        settings_query = """
        INSERT INTO room_settings (user_id, room_id, timezone, wanted_temp_day, wanted_temp_night, night_start, night_end)
        VALUES (%s, %s, 'Europe/Berlin', 21.0, 18.0, '22:00:00', '06:00:00')
        """
        db.execute_query(settings_query, (current_user["id"], new_room["id"]), fetch=False)
        return Room(id=new_room["id"], user_id=new_room["user_id"], name=new_room["name"])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not create room: {str(e)}")
    

@app.get("/rooms", response_model=List[Room], tags=["Rooms"], summary="Show users rooms")
@limiter.limit("50/minute") 
async def get_rooms(request: Request, current_user=Depends(get_current_user)):
    """Get all rooms of the user"""
    query = "SELECT id, user_id, name FROM rooms WHERE user_id = %s"
    rooms = db.execute_query(query, (current_user["id"],))
    return [Room(id=r["id"], user_id=r["user_id"], name=r["name"]) for r in (rooms or [])]


@app.delete("/rooms/{room_id}", tags=["Rooms"], summary="Delete a room")
@limiter.limit("50/minute") 
async def delete_room(request: Request, room_id: int, current_user=Depends(get_current_user)):
    """Delete a room and all of its temperature data"""
    # Check if room actually belongs to user
    room = db.execute_query(
        "SELECT id FROM rooms WHERE id = %s AND user_id = %s",
        (room_id, current_user["id"]))
    if not room:
        raise HTTPException(status_code=404, detail="Room not found or access denied")
    # Deleting the suiting temperature data from Influx
    try:
        delete_api = influx_client.delete_api()
        delete_api.delete(
            predicate=f'_measurement="temperature" AND room_id="{str(room_id)}" AND user_id="{int(current_user["id"])}"',
            start="1970-01-01T00:00:00Z",
            stop=datetime.now().isoformat() + "Z",
            bucket=INFLUX_BUCKET,
            org=INFLUX_ORG)
    except Exception as e:
        print(f"Warning: Could not delete from InfluxDB: {str(e)}")
    # Deleting room from SQL
    db.execute_query("DELETE FROM rooms WHERE id = %s", (room_id,), fetch=False)
    return {"message": "Room and all temperature data deleted successfully"}


# ============ ROOM SETTINGS ENDPOINTS ============
@app.put("/rooms/{room_id}/settings", tags=["Room settings"], summary="Update settings of a room")
@limiter.limit("10/minute") 
async def update_room_settings(request: Request, room_id: int, settings: RoomSettings, current_user=Depends(get_current_user)):
    """Update heating settings of a room"""
    # Check if room actually belongs to user
    room = db.execute_query(
        "SELECT id FROM rooms WHERE id = %s AND user_id = %s",
        (room_id, current_user["id"]))
    if not room:
        raise HTTPException(status_code=404, detail="Room not found or access denied")
    # Check if it has settings
    existing_settings = db.execute_query(
        "SELECT id FROM room_settings WHERE user_id = %s AND room_id = %s",
        (current_user["id"], room_id))
    if not existing_settings:
        raise HTTPException(status_code=404, detail="Room settings not found")
    query = """
    UPDATE room_settings
    SET timezone = %s, wanted_temp_day = %s, wanted_temp_night = %s, night_start = %s, night_end = %s
    WHERE user_id = %s AND room_id = %s
    """
    db.execute_query(query, (
        settings.timezone, settings.wanted_temp_day, settings.wanted_temp_night,
        settings.night_start, settings.night_end,
        current_user["id"], room_id
    ), fetch=False)
    return {"message": "Settings updated successfully"}


@app.get("/rooms/{room_id}/settings", response_model=RoomSettings, tags=["Room settings"], summary="Show settings of a room")
@limiter.limit("50/minute") 
async def get_room_settings(request: Request, room_id: int, current_user=Depends(get_current_user)):
    """Get current heating settings of a room (wanted temperature day and night, also night_start and night_end)"""
    # Checking if room belongs to user
    room = db.execute_query(
        "SELECT id FROM rooms WHERE id = %s AND user_id = %s",
        (room_id, current_user["id"]))
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    # Checking settings
    settings = db.execute_query(
        "SELECT timezone, wanted_temp_day, wanted_temp_night, night_start, night_end FROM room_settings WHERE user_id = %s AND room_id = %s",
        (current_user["id"], room_id))
    if not settings:
        raise HTTPException(status_code=404, detail="Room settings not found")    
    s = settings[0]
    return RoomSettings(
        timezone=s["timezone"],
        wanted_temp_day=s["wanted_temp_day"],
        wanted_temp_night=s["wanted_temp_night"],
        night_start=str(s["night_start"]),
        night_end=str(s["night_end"]))


# ============ TEMPERATURE ENDPOINTS ============
@app.post("/temperature", tags=["Temperatures"], summary="Add new temperature")
@limiter.limit("50/minute")
async def post_temperature(request: Request, data: TemperatureEntry, current_user=Depends(get_current_user)):
    """Save a new temperature (only done in backend by IOT device)"""
    # Check if room belongs to user
    room = db.execute_query(
        "SELECT id FROM rooms WHERE id = %s AND user_id = %s",
        (data.room_id, current_user["id"]))
    if not room:
        raise HTTPException(status_code=404, detail="Room not found or access denied")    
    # Adding temperature with timestamp
    timestamp = datetime.now()    
    point = (
        Point("temperature")
        .tag("user_id", str(current_user["id"]))
        .tag("room_id", str(data.room_id))
        .field("value", data.temperature)
        .time(timestamp))
    write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
    return {"message": "Temperature recorded"}


@app.post("/temperature/batch", tags=["Temperatures"], summary="Add multiple temperatures at once")
@limiter.limit("50/minute") 
async def post_temperature_batch(request: Request, batch: TemperatureEntryBatch, current_user=Depends(get_current_user)):
    """Add new temperatures in a batch (only useful for debugging)"""
    # Check if room belongs to user
    room = db.execute_query(
        "SELECT id FROM rooms WHERE id = %s AND user_id = %s",
        (batch.room_id, current_user["id"]))
    if not room:
        raise HTTPException(status_code=404, detail="Room not found or access denied") 
    if len(batch.temperatures) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 temperatures per request")
    # Save all temperatures
    for i, temp in enumerate(batch.temperatures):
        timestamp = datetime.now()
        if batch.timestamps and i < len(batch.timestamps):
            try:
                timestamp = datetime.fromisoformat(batch.timestamps[i].replace('Z', '+00:00'))
            except ValueError:
                timestamp = datetime.now()
        point = (
            Point("temperature")
            .tag("user_id", str(current_user["id"]))
            .tag("room_id", str(batch.room_id))
            .field("value", temp)
            .time(timestamp))
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
    return {"message": f"{len(batch.temperatures)} temperatures recorded"}


@app.get("/temperature/{room_id}", response_model=List[TemperatureResponse], tags=["Temperatures"], summary="Get temperatures of a certain timeframe")
@limiter.limit("100/minute")
async def get_room_temperatures(
    request: Request, 
    room_id: int,
    current_user=Depends(get_current_user),
    start: Optional[str] = Query(None, description="Start time for the query. ISO format (2026-01-01T00:00:00Z)"),
    end: Optional[str] = Query(None, description="Start time for the query. ISO format (2026-01-01T00:00:00Z)")
):
    """Get all temperatures of a room over a custom timeframe"""
    # Checking if room belongs to user
    room = db.execute_query("SELECT id FROM rooms WHERE id = %s AND user_id = %s",
                           (room_id, current_user["id"]))
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    # Default is last 24 hours till now
    if not start:
        start_flux = "-24h"
    else:
        start_flux = f'time(v: "{start}")'
    
    if not end:
        end_flux = "now()"
    else:
        end_flux = f'time(v: "{end}")'
    
    flux_query = f'''
    from(bucket:"{INFLUX_BUCKET}")
      |> range(start: {start_flux}, stop: {end_flux})
      |> filter(fn: (r) => r._measurement == "temperature")
      |> filter(fn: (r) => r.user_id == "{current_user['id']}")
      |> filter(fn: (r) => r.room_id == "{room_id}")
      |> sort(columns: ["_time"], desc: false)
    '''
    
    tables = influx_client.query_api().query(flux_query, org=INFLUX_ORG)
    results = []
    for table in tables:
        for record in table.records:
            results.append(TemperatureResponse(
                time=record.get_time().isoformat(),
                value=record.get_value(),
                room_id=room_id))
    return results



@app.get("/temperature/{room_id}/latest/", response_model=TemperatureResponse, tags=["Temperatures"], summary="Get latest temperature")
@limiter.limit("100/minute") 
async def get_latest_temperature(request: Request, room_id: int, current_user=Depends(get_current_user)):
    """ Get latest temperature of a room"""
    # Checking if room belongs to user
    room = db.execute_query(
        "SELECT id FROM rooms WHERE id = %s AND user_id = %s",
        (room_id, current_user["id"]))
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")    
    # Getting the last temperature added
    flux_query = f'''
    from(bucket:"{INFLUX_BUCKET}")
      |> range(start: -7d)
      |> filter(fn: (r) => r._measurement == "temperature")
      |> filter(fn: (r) => r.user_id == "{current_user['id']}")
      |> filter(fn: (r) => r.room_id == "{room_id}")
      |> last()
    '''    
    tables = influx_client.query_api().query(flux_query, org=INFLUX_ORG)    
    for table in tables:
        for record in table.records:
            return TemperatureResponse(
                time=record.get_time().isoformat(),
                value=record.get_value(),
                room_id=room_id)    
    raise HTTPException(status_code=404, detail="No temperature data found")


@app.get("/temperatures/all", response_model=List[TemperatureResponse], tags=["Temperatures"], summary="get temperatures of all rooms")
@limiter.limit("50/minute") 
async def get_all_temperatures(
    request: Request, 
    current_user=Depends(get_current_user),
    start: str = "-24h",
    end: Optional[str] = "now"    
):
    """
    Gets ALL temperature Data of a room
    - start: relative Duration (eg. -24h or -7d) or ISO-Time (2025-11-27T00:00:00Z)
    - end:   "now" (Default) oder ISO-Time
    """

    if end is None or end == "now":
        stop_expr = "now()"
    else:
        stop_expr = f"time(v: \"{end}\")"

    flux_query = f'''
    from(bucket:"{INFLUX_BUCKET}")
      |> range(start: {start}, stop: {stop_expr})
      |> filter(fn: (r) => r._measurement == "temperature")
      |> filter(fn: (r) => r.user_id == "{int(current_user['id'])}")
      |> sort(columns: ["_time"], desc: false)
    '''

    tables = influx_client.query_api().query(flux_query, org=INFLUX_ORG)
    results: List[TemperatureResponse] = []

    for table in tables:
        for record in table.records:
            results.append(TemperatureResponse(
                time=record.get_time().isoformat(),
                value=record.get_value(),
                room_id=int(record.values.get("room_id", 0))
            ))
    return results


# ============ WEATHER TEMPERATURE ENDPOINT ============
@app.get("/weather_temperature", response_model=List[TemperatureResponse], tags=["Weather"], summary="Get weather temperatures")
@limiter.limit("100/minute") 
async def get_weather_temperatures(
    request: Request, 
    current_user=Depends(get_current_user),
    start: Optional[str] = Query(None, description="Start time for the query. ISO format (2026-01-01T00:00:00Z)"),
    end: Optional[str] = Query(None, description="End time for the query. ISO format (2026-01-01T00:00:00Z)")
):
    """Get weather temperature history for current user"""
    # Default: last 24h
    if not start:
        start_flux = "-24h"
    else:
        start_flux = f'time(v: "{start}")'
    
    if not end:
        end_flux = "now()"
    else:
        end_flux = f'time(v: "{end}")'
    
    # Select Weather Temperatures     
    flux_query = f'''
    from(bucket:"{INFLUX_BUCKET}")
      |> range(start: {start_flux}, stop: {end_flux})
      |> filter(fn: (r) => r._measurement == "weather_temperature")
      |> filter(fn: (r) => r.user_id == "{current_user['id']}")
      |> sort(columns: ["_time"], desc: false)
    '''
    
    tables = influx_client.query_api().query(flux_query, org=INFLUX_ORG)
    results = []
    for table in tables:
        for record in table.records:
            results.append(TemperatureResponse(
                time=record.get_time().isoformat(),
                value=record.get_value(),
                room_id=0  # Weather data has no room_id
            ))
    return results


# ============ CURRENT WEATHER ============


@app.get("/geocode/search", response_model=CitySearchResults, tags=["Weather"], summary="Search for cities and convert into coordinates")
@limiter.limit("50/minute") 
async def search_cities(request: Request, q: str):  
    """Using noatim to look for cities and converting it to coordinates"""
    if not q or len(q) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    
    # The Api only works with an email, although luckily, the email does not need to actually exist
    user_email = "public@heatcontrol.app"
    
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": q,
        "format": "json",
        "language": "en",
        "limit": 10
    }
    headers = {
        "User-Agent": f"HeatControlApp/1.0 ({user_email})"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return CitySearchResults(results=[])
        
        results = [
            CitySearchResult(
                display_name=item["display_name"],
                latitude=float(item["lat"]),
                longitude=float(item["lon"])
            )
            for item in data[:10]
        ]
        
        return CitySearchResults(results=results)
    
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Nominatim API error: {str(e)}")
    

@app.get("/weather", response_model=WeatherResponse, tags=["Weather"], summary="Get current weather at user location")
@limiter.limit("50/minute") 
async def get_weather(request: Request, current_user=Depends(get_current_user)):
    """Get weather data for the user location"""
    # Get current Users location
    user = db.execute_query(
        "SELECT latitude, longitude FROM users WHERE id = %s",
        (current_user["id"],)
    )[0]
    
    latitude = user["latitude"]
    longitude = user["longitude"]
    
    # Look up weather at that location
    try:
        response = requests.get(
            WEATHER_API,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,weather_code",
                "timezone": "auto"
            },
            timeout=5
        )
        response.raise_for_status()
        data = response.json()
        
        current = data.get("current", {})
        weather_code = current.get("weather_code", 0)
        weather_condition = WEATHER_CODES.get(weather_code, "Unknown")
        
        return WeatherResponse(
            temperature=current.get("temperature_2m", 0),
            weather_condition=weather_condition,
            location=f"{latitude},{longitude}",
            timestamp=current.get("time", datetime.now().isoformat())
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Weather API error: {str(e)}")


# ============ HEATING STATUS ============
@app.get("/heating_on/{room_id}", response_model=HeatingStatusResponse, tags=["Heating"], summary="Check if heating should be on or off")
@limiter.limit("50/minute") 
async def get_heating_status(request: Request, room_id: int, current_user=Depends(get_current_user)):
    """Checks if heating should be on depending on the wanted temperature/temperature of the room, returns either True or False"""
    # Check if room belongs to user
    room = db.execute_query(
        "SELECT id FROM rooms WHERE id = %s AND user_id = %s",
        (room_id, current_user["id"]))
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    # Get wanted temperatures
    settings = db.execute_query(
        "SELECT wanted_temp_day, wanted_temp_night, night_start, night_end FROM room_settings WHERE user_id = %s AND room_id = %s",
        (current_user["id"], room_id))
    if not settings:
        raise HTTPException(status_code=404, detail="Room settings not found")
    settings = settings[0]
    # Check if nighttime wanted temperature or daytime wanted temperature is needed
    now = datetime.now().time()
    night_start = settings["night_start"]
    night_end = settings["night_end"]
    if isinstance(night_start, timedelta):
        seconds = int(night_start.total_seconds())
        night_start = time(seconds // 3600, (seconds % 3600) // 60, seconds % 60)
    elif isinstance(night_start, str):
        night_start = datetime.strptime(night_start, "%H:%M:%S").time()
    if isinstance(night_end, timedelta):
        seconds = int(night_end.total_seconds())
        night_end = time(seconds // 3600, (seconds % 3600) // 60, seconds % 60)
    elif isinstance(night_end, str):
        night_end = datetime.strptime(night_end, "%H:%M:%S").time()
    is_night = False
    if night_start < night_end:
        is_night = night_start <= now < night_end
    else:
        is_night = now >= night_start or now < night_end
    target_temp = settings["wanted_temp_night"] if is_night else settings["wanted_temp_day"]
    # Check if latest temperature is lower or higher than wanted temperature
    flux_query = f'''
    from(bucket:"{INFLUX_BUCKET}")
      |> range(start: -7d)
      |> filter(fn: (r) => r._measurement == "temperature")
      |> filter(fn: (r) => r.user_id == "{int(current_user['id'])}")
      |> filter(fn: (r) => r.room_id == "{str(room_id)}")
      |> last()
    '''
    tables = influx_client.query_api().query(flux_query, org=INFLUX_ORG)
    current_temp = None
    for table in tables:
        for record in table.records:
            current_temp = record.get_value()
    if current_temp is None:
        raise HTTPException(status_code=404, detail="No temperature data found for this room")
    # Returns True if current temperature is below the target temperature
    heating_on = current_temp < target_temp
    return {"heating_on": heating_on}