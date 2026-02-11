import os
import pandas as pd
from datetime import datetime, timedelta
from database import MySQLClient
from influxdb_client import InfluxDBClient, Point, WriteOptions
import logging

# Environment variables
INFLUX_URL = str(os.getenv("INFLUX_URL", "http://influxdb:8086"))
INFLUX_TOKEN = str(os.getenv("INFLUX_TOKEN", "influx_token"))
INFLUX_ORG = str(os.getenv("INFLUX_ORG", "my-org"))
INFLUX_BUCKET = str(os.getenv("INFLUX_BUCKET", "heating"))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, "data", "temperatures.csv")

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fahrenheit_to_celsius(fahrenheit):
    """Convertings Fahrenheit to Celsius"""
    return (fahrenheit - 32) * 5 / 9


def import_csv_if_needed(user_id: int):
    """Importing Testdata from CSV, if the user does not have any rooms, changing the timeframes to end yesterday, converting temperatures to Celsius"""
    db = MySQLClient()
    
    # Check already has rooms
    existing_rooms = db.execute_query(
        "SELECT id FROM rooms WHERE user_id = %s",
        (user_id,)
    )
    
    if existing_rooms and len(existing_rooms) > 0:
        logger.info(f"User {user_id} hat bereits {len(existing_rooms)} Räume. Import übersprungen.")
        return
    
    # Check if CSV exists
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"CSV-Datei nicht gefunden: {CSV_PATH}")
    df = pd.read_csv(CSV_PATH, skipinitialspace=True)
    
    # Converting data in suitable format and celius
    df.columns = df.columns.str.strip().str.replace('"', '')
    df['time'] = pd.to_datetime(df['time'])
    df['temperature'] = df['temperature'].apply(fahrenheit_to_celsius)
        
    # Only using every tenth datapoint because otherwise the data would take very long to load
    df = df.iloc[::10].reset_index(drop=True)
    
    # Changing data to yesterday
    max_date = df['time'].max()
    yesterday = datetime.now().replace(hour=23, minute=59, second=59, microsecond=0) - timedelta(days=1)
    offset = yesterday - max_date
    df['time'] = df['time'] + offset
    
    # Room 4 is only used as the Data for the saved current weather
    room_4_data = df[df['room'] == 'Room 4'].copy()
    df = df[df['room'] != 'Room 4']
    
    # Create Rooms in SQL Database
    unique_rooms = df['room'].unique()
    room_mapping = {}
    
    for room_name in unique_rooms:
        db.execute_query(
            "INSERT INTO rooms (user_id, name) VALUES (%s, %s)",
            (user_id, room_name),
            fetch=False
        )
        
        room_result = db.execute_query(
            "SELECT id FROM rooms WHERE user_id = %s AND name = %s",
            (user_id, room_name)
        )
        
        room_id = room_result[0]['id']
        room_mapping[room_name] = room_id
        
        db.execute_query(
            """
            INSERT INTO room_settings
            (user_id, room_id, timezone, wanted_temp_day, wanted_temp_night, night_start, night_end)
            VALUES (%s, %s, 'Europe/Berlin', 21.0, 18.0, '22:00:00', '06:00:00')
            """,
            (user_id, room_id),
            fetch=False
        )
        
        logger.info(f"Created '{room_name}' with ID: {room_id}")
    
    # Add temperatures to Influx
    influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = influx_client.write_api(write_options=WriteOptions(batch_size=500))
    points = []
    for _, row in df.iterrows():
        room_id = room_mapping[row['room']]
        
        point = (
            Point("temperature")
            .tag("user_id", str(user_id))
            .tag("room_id", str(room_id))
            .field("value", float(row['temperature']))
            .time(row['time'])
        )
        points.append(point)
        
        if len(points) >= 500:
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points)
            points = []
    
    if points:
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points)
    
    # Add weather Data to Influx (temperatures from Room 4)
    weather_points = []
    for _, row in room_4_data.iterrows():
        weather_point = (
            Point("weather_temperature")
            .tag("user_id", str(user_id))
            .field("value", float(row['temperature']))
            .time(row['time'])
        )
        weather_points.append(weather_point)
        
        if len(weather_points) >= 500:
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=weather_points)
            weather_points = []
    
    if weather_points:
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=weather_points)
    
    write_api.close()
    influx_client.close()