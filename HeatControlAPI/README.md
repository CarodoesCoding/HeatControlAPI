# Heat Control API
A FastAPI-based backend that automatically controls room heating by monitoring indoor temperatures against target values, integrating real-time weather data and external geocoding services.

## System Architecture

┌─────────────────────────────────────────────────────────────────┐
│                        Heat Control API                         │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────┐      ┌──────────────────┐       ┌─────────────┐
│   Dashboard      │      │    FastAPI       │─────▶│ InfluxDB    │
│   Port: 8501     │      │    Backend       │       │ Temps       │
│   (Streamlit)    │      │    Port: 8000    │       │ Port: 8086  │
└──────────────────┘      └──────────────────┘       └─────────────┘
                                │                       ▲
                ┌───────────────┼──────────────┐        │
                │               │              │        │
                ▼               ▼              ▼        │
      ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
      │ Noatim API  │ │ OpenMeteo   │ │   MySQL     │   │
      │ (Geocoding) │ │ (Weather)   │ │ Rooms/Users │◄──┘
      │             │ │             │ │ Port: 3306  │
      └─────────────┘ └─────────────┘ └─────────────┘
## Key Features
Heating Control Decision: Get automatic on/off recommendations based on room temperature vs target and weather conditions

Temperature Monitoring: Retrieve latest indoor temperatures from InfluxDB time-series storage

Weather Integration: Fetch current weather data via OpenMeteo API

Data Management: Add new temperature readings, rooms, and update target temperatures

User Management: User registration, login, and room assignment per user

Interactive Dashboard: Visualize temperatures and control decisions at http://localhost:8501

## Quick Start
Prerequisites
Docker and Docker Compose installed

Running the System
Navigate to the project directory:

bash
cd heat-control-api
Copy environment template:

bash
cp .env.example .env
**Edit .env if needed (defaults work for basic setup)**
Start all services:

docker compose up --build
Access the applications:

Dashboard: http://localhost:8501

API Documentation: http://localhost:8000/docs#/

InfluxDB UI: http://localhost:8086

Stopping the System
docker compose down


To remove all data volumes:
docker compose down -v


## Project Structure

.
├── api/                  # FastAPI backend application
│   ├── database.py       # Database connection management
│   ├── main.py           # API entry point
│   ├── models.py         # Pydantic data models
│   ├── sql.py            # MySQL operations (rooms/users)
│   ├── Dockerfile
│   ├── requirements.txt
│   └── test_import.py
├── dashboard/             # Streamlit visualization
│   ├── dashboard.py
│   ├── Dockerfile
│   └── requirements.txt
├── data/                  # Initial data
│   └── temperatures.csv
├── database/              # Database services
│   ├── influx.py          # InfluxDB setup
│   ├── Dockerfile
│   └── requirements.txt
├── .dockerignore
├── .gitignore
├── .env.example           # Environment template
└── docker-compose.yaml    # Orchestration file

## Most impportant API Endpoints
Access full interactive documentation at http://localhost:8000/docs:

POST /temperatures - Add new temperature reading

GET /temperatures/latest - Get latest temperature

GET /heating-control - Get heating on/off decision

GET /weather - Get current weather data

POST /rooms - Add new room

PATCH /rooms/{room_id}/target - Update target temperature

POST /register - Register new user

POST /login - User login

GET /users/rooms - List user's rooms

## Environment Variables
Copy .env.example to .env and configure:

Database credentials (MySQL, InfluxDB)

API keys for Noatim and OpenMeteo services

Application secrets

All services are pre-configured in docker-compose.yaml with health checks and automatic initialization.