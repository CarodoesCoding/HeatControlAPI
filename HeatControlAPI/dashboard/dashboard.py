import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
import pytz
st.cache_data.clear()


API_URL = "http://api:8000"
WEATHER_EMOJI = {
    "Clear Sky": "☀️",
    "Mainly Clear": "🌤️",
    "Partly Cloudy": "⛅",
    "Overcast": "☁️",
    "Foggy": "🌫️",
    "Light Drizzle": "🌦️",
    "Moderate Drizzle": "🌧️",
    "Dense Drizzle": "🌧️",
    "Slight Rain": "🌧️",
    "Moderate Rain": "🌧️",
    "Heavy Rain": "⛈️",
    "Slight Snow": "🌨️",
    "Moderate Snow": "🌨️",
    "Heavy Snow": "❄️",
    "Snow Grains": "❄️",
    "Slight Showers": "🌦️",
    "Moderate Showers": "🌧️",
    "Violent Showers": "⛈️",
    "Slight Snow Showers": "🌨️",
    "Heavy Snow Showers": "❄️",
    "Thunderstorm": "⛈️",
    "Thunderstorm with Hail": "⛈️",
}

# Note: I know Emojis always seem like AI but here I was simply too lazy to select a bunch of little images. Using Emojis was the simplest solution.

st.set_page_config(
    page_title="Heat Control",
    layout="wide"
)

# ============ SESSION MANAGEMENT ============

class SessionManager:
    """Verwaltet persistente Session-Daten über Refreshes hinweg"""
    def __init__(self):
        self.token = None
        self.user = None
        self.current_room = None
        self.show_user_profile = False
        self.user_timezone = "UTC"

@st.cache_resource
def get_session_manager():
    return SessionManager()

session = get_session_manager()

if not hasattr(session, "confirm_delete_room_id"):
    session.confirm_delete_room_id = None
    session.confirm_delete_room_name = None


# ============ COOKIE & SESSION HELPERS ============
def get_token_from_url():
    """Test if token is in query-parameters"""
    if "token" in st.query_params:
        return st.query_params["token"]
    return None


def save_token_to_url(token: str):
    """Saving Token in URL Query-Parameters"""
    st.query_params = {"token": token}


def initialize_session():
    """Initialize session for first startup"""
    if session.token is None:
        url_token = get_token_from_url()
        if url_token:
            session.token = url_token
            try:
                user_response = requests.get(
                    f"{API_URL}/me",
                    headers={"Authorization": f"Bearer {session.token}"}
                )
                user_response.raise_for_status()
                session.user = user_response.json()
                session.user_timezone = get_user_timezone()
            except:
                session.token = None
                session.user = None

initialize_session()

# ============ API HELPERS ============
def register_user(email: str, password: str, latitude: float, longitude: float):
    """Register new user"""
    try:
        response = requests.post(
            f"{API_URL}/register",
            json={
                "email": email,
                "password": password,
                "latitude": latitude,
                "longitude": longitude
            }
        )
        response.raise_for_status()
        return True, "Registration successful, please log in now!"
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 422:
            return False, "Email not in acceptable format"
        elif e.response.status_code == 400:
            return False, "Email already registered"
        return False, f"Error: {str(e)}"
    except requests.exceptions.RequestException as e:
        return False, f"Error: {str(e)}"


def register_user_with_city(email: str, password: str, city_name: str, city_data: dict):
    """Register new user with city"""
    try:
        response = requests.post(
            f"{API_URL}/register",
            json={
                "email": email,
                "password": password,
                "latitude": city_data["latitude"],
                "longitude": city_data["longitude"]
            }
        )
        response.raise_for_status()
        return True, "Registration succesfull, please log in now!"
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 422:
            return False, "Email not in acceptable format"
        elif e.response.status_code == 400:
            return False, "Email already registered"
        return False, f"Error: {str(e)}"
    except requests.exceptions.RequestException as e:
        return False, f"Error: {str(e)}"



def login_user(email: str, password: str):
    """Logging in user and saving the token"""
    try:
        response = requests.post(
            f"{API_URL}/token",
            data={"username": email, "password": password}
        )
        response.raise_for_status()
        data = response.json()
        session.token = data["access_token"]
        
        # Speichere Token in URL
        save_token_to_url(data["access_token"])
        
        # Hole User Info
        user_response = requests.get(
            f"{API_URL}/me",
            headers={"Authorization": f"Bearer {session.token}"}
        )
        user_response.raise_for_status()
        session.user = user_response.json()
        session.user_timezone = get_user_timezone()
        
        return True, "Login sucessful"
    except requests.exceptions.HTTPError as e:
        # Bessere Fehlermeldungen statt generischem HTTP-Error
        if e.response.status_code == 400:
            return False, "Incorrect Email or Password"
        return False, f"Login error: {str(e)}"
    except requests.exceptions.RequestException as e:
        return False, f"Login error: {str(e)}"


def logout():
    """Logout and delete token"""
    st.query_params.clear()
    session.token = None
    session.user = None
    session.current_room = None
    session.current_name = None
    session.show_user_profile = False
    get_session_manager.clear()


def get_rooms():
    """Get all rooms from users"""
    try:
        response = requests.get(
            f"{API_URL}/rooms",
            headers={"Authorization": f"Bearer {session.token}"}
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error when loading rooms: {str(e)}")
        return []


def create_room(room_name: str):
    """Creating new room"""
    try:
        response = requests.post(
            f"{API_URL}/rooms",
            json={"name": room_name},
            headers={"Authorization": f"Bearer {session.token}"}
        )
        response.raise_for_status()
        st.success("Created room successfully!")
        st.rerun()
    except requests.exceptions.RequestException as e:
        st.error(f"Error: {str(e)}")


def delete_room(room_id: int):
    """Deleting a room"""
    try:
        response = requests.delete(
            f"{API_URL}/rooms/{room_id}",
            headers={"Authorization": f"Bearer {session.token}"}
        )
        response.raise_for_status()
        st.success("Room deleted successfully!")
    except requests.exceptions.RequestException as e:
        st.error(f"Error: {str(e)}")


def get_room_settings(room_id: int):
    """Get settings of a room"""
    try:
        response = requests.get(
            f"{API_URL}/rooms/{room_id}/settings",
            headers={"Authorization": f"Bearer {session.token}"}
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error: {str(e)}")
        return None


def update_room_settings(room_id: int, settings: dict):
    """Update room settings"""
    try:
        response = requests.put(
            f"{API_URL}/rooms/{room_id}/settings",
            json=settings,
            headers={"Authorization": f"Bearer {session.token}"}
        )
        response.raise_for_status()
        st.success("Updatet settings succesfully!")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return None
        st.error(f"Error: {str(e)}")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Error: {str(e)}")
        return None


def get_latest_temperature(room_id: int):
    """Get latest temperature of a room"""
    try:
        response = requests.get(
            f"{API_URL}/temperature/{room_id}/latest/",
            headers={"Authorization": f"Bearer {session.token}"}
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return None
        st.error(f"Error: {str(e)}")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Error: {str(e)}")
        return None


def get_temperature_history(room_id: int, start: str = None, end: str = None):
    """Get temperature history mit Start+End"""
    try:
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        
        response = requests.get(
            f"{API_URL}/temperature/{room_id}",
            params=params,
            headers={"Authorization": f"Bearer {session.token}"}
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error: {str(e)}")
        return []


def get_heating_status(room_id: int):
    """Get current heating status"""
    try:
        response = requests.get(
            f"{API_URL}/heating_on/{room_id}",
            headers={"Authorization": f"Bearer {session.token}"}
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return None
        st.error(f"Error: {str(e)}")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Error: {str(e)}")
        return None
    

@st.cache_data(ttl=3600)
def search_cities(query: str, user_email: str):
    """Get Koordinates of a city by searching with Noatim API"""
    if not query or len(query) < 2:
        return []
    try:
        response = requests.get(
            f"{API_URL}/geocode/search",
            params={"q": query}
        )
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    except:
        return []


def get_weather():
    """Get current weather data"""
    try:
        response = requests.get(
            f"{API_URL}/weather",
            headers={"Authorization": f"Bearer {session.token}"}
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error: {str(e)}")
        return None
    
    
def get_weather_temperatures(start: str = None, end: str = None):
    """Get weather temperature history"""
    try:
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
            
        response = requests.get(
            f"{API_URL}/weather_temperature",
            params=params,
            headers={"Authorization": f"Bearer {session.token}"}
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error: {str(e)}")
        return []


def get_user_timezone():
    """Get user timezone from backend"""
    try:
        response = requests.get(
            f"{API_URL}/timezone",
            headers={"Authorization": f"Bearer {session.token}"}
        )
        response.raise_for_status()
        return response.json().get("timezone", "UTC")
    except requests.exceptions.RequestException as e:
        st.error(f"Error: {str(e)}")
        return "UTC"


def get_current_target_temp(room_id: int, settings: dict):
    """Get current wanted temperature"""
    from datetime import time as dt_time
    now = datetime.now().time()
    night_start_str = settings["night_start"]
    night_end_str = settings["night_end"]
    
    night_start = datetime.strptime(night_start_str, "%H:%M:%S").time()
    night_end = datetime.strptime(night_end_str, "%H:%M:%S").time()
    
    # Determine if night or day
    is_night = False
    if night_start < night_end:
        is_night = night_start <= now < night_end
    else:
        is_night = now >= night_start or now < night_end
    
    if is_night:
        return settings["wanted_temp_night"]
    else:
        return settings["wanted_temp_day"]
    

def update_user_location(latitude: float, longitude: float):
    """Updates the location of the user"""
    try:
        response = requests.put(
            f"{API_URL}/me/location",
            json={"latitude": latitude, "longitude": longitude},
            headers={"Authorization": f"Bearer {session.token}"}
        )
        response.raise_for_status()
        
        # Reload User Data
        user_response = requests.get(
            f"{API_URL}/me",
            headers={"Authorization": f"Bearer {session.token}"}
        )
        user_response.raise_for_status()
        session.user = user_response.json()
        session.user_timezone = get_user_timezone()
        
        return True, "Location changed succesfully!"
    except requests.exceptions.RequestException as e:
        return False, f"Error: {str(e)}"


def change_password(old_password: str, new_password: str):
    """Change Password"""
    try:
        response = requests.put(
            f"{API_URL}/me/password",
            json={"old_password": old_password, "new_password": new_password},
            headers={"Authorization": f"Bearer {session.token}"}
        )
        response.raise_for_status()
        return True, "Password changed successfully!"
    except requests.exceptions.RequestException as e:
        if "400" in str(e):
            return False, "Incorrect Password"
        return False, f"Error: {str(e)}"

# ============ PAGES ============
def render_topbar(show_back: bool = False):
    """
    Header Bar for all pages
    """
    if show_back:
        cols = st.columns([1, 6, 2, 1])
    else:
        cols = st.columns([6, 2, 1])

    if show_back:
        with cols[0]:
            if st.button("⬅ back", use_container_width=True):
                session.current_room = None
                session.current_name = None
                st.rerun()
    with cols[-3]:
        st.empty()
    with cols[-2]:
        if st.button(session.user["email"], use_container_width=True):
            session.show_user_profile = True
            st.rerun()
    with cols[-1]:
        if st.button("Logout", use_container_width=True):
            logout()
            st.rerun()
    st.divider()


def page_login():
    """Login/Register page"""
    st.title("Heat Control API")
    
    tab1, tab2 = st.tabs(["Login", "Register"])
    # Login Page
    with tab1:
        st.subheader("Login")
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        
        if st.button("Login"):
            if email and password:
                success, message = login_user(email, password)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
            else:
                st.warning("Please fill in all fields")
    # Register Page
    with tab2:
        st.subheader("Register")
        reg_email = st.text_input("Email", key="reg_email")
        reg_password = st.text_input("Password", type="password", key="reg_password")
        
        st.divider()
        st.write("**Enter City:**")
        
        city_query = st.text_input("Input City (e.g. 'Munich')", key="city_search")
        
        selected_city = None
        selected_data = None
        
        if city_query and len(city_query) >= 2:
            suggestions = search_cities(city_query, reg_email)
            
            if suggestions:
                display_names = [s["display_name"] for s in suggestions]
                selected_idx = st.selectbox(
                    "Choose your city:",
                    range(len(display_names)),
                    format_func=lambda i: display_names[i],
                    key="city_select"
                )
                selected_city = display_names[selected_idx]
                selected_data = suggestions[selected_idx]
                
                col1, col2 = st.columns(2)
                col1.metric("Latitude", f"{selected_data['latitude']:.4f}")
                col2.metric("Longitude", f"{selected_data['longitude']:.4f}")
            else:
                st.warning("No cities found!")
        elif city_query:
            st.info("Please enter at least 2 characters")
        
        st.divider()
        st.write("**Choose coordinates:**")
        col1, col2 = st.columns(2)
        with col1:
            manual_lat = st.number_input("Latitude", value=52.52, key="reg_latitude")
        with col2:
            manual_lon = st.number_input("Longitude", value=13.40, key="reg_longitude")
        
        if st.button("Register"):
            if not reg_email or not reg_password:
                st.error("Email and password needed!")
            elif selected_data:
                # Registering user with city
                success, message = register_user_with_city(
                    reg_email, 
                    reg_password, 
                    selected_city,
                    selected_data
                )
                if success:
                    pass
                else:
                    st.error(message)
            elif manual_lat and manual_lon:
                # Registering user with coordinates
                success, message = register_user(
                    reg_email, 
                    reg_password, 
                    manual_lat, 
                    manual_lon
                )
                if success:
                    st.success(message)
                    pass
                else:
                    st.error(message)
            else:
                st.error("Please choose a city or enter coordinates.")




def page_user_profile():
    """User profile page"""
    col1, col2 = st.columns(2)

    with col1:
        if st.button("Back to the rooms", use_container_width=True):
            session.show_user_profile = False
            st.rerun()

    with col2:
        if st.button("Logout", use_container_width=True):
            logout()
            st.rerun()

    st.divider()
    user = session.user
    st.divider()

    # Changing location option
    with st.container(border=True):
        st.subheader("Change Location")
        st.write("**Enter city:**")
        update_city_query = st.text_input(
            "Enter city", 
            key="update_city_search", 
            label_visibility="collapsed"
        )

        selected_update_data = None
        selected_display_name = None

        if update_city_query and len(update_city_query) >= 2:
            suggestions = search_cities(update_city_query, user["email"])

            if suggestions:
                display_names = [s["display_name"] for s in suggestions]
                
                selected_idx = st.selectbox(
                    "Choose your city:",
                    range(len(display_names)),
                    format_func=lambda i: display_names[i],
                    key="update_city_select"
                )

                selected_update_data = suggestions[selected_idx]
                selected_display_name = display_names[selected_idx]

                # Zeige Koordinaten (Preview)
                col1, col2 = st.columns(2)
                col1.metric("Latitude", f"{selected_update_data['latitude']:.4f}")
                col2.metric("Longitude", f"{selected_update_data['longitude']:.4f}")

            else:
                st.warning("No cities found!")

        elif update_city_query:
            st.info("Please enter at least 2 characters.")

        st.divider()

        st.write("**Choose coordinates:**")

        col1, col2 = st.columns(2)

        with col1:
            latitude = st.number_input(
                "Latitude",
                value=float(selected_update_data["latitude"]) if selected_update_data else float(user["latitude"]),
                format="%.6f",
                step=0.000001,
                key="profile_lat"
            )

        with col2:
            longitude = st.number_input(
                "Longitude",
                value=float(selected_update_data["longitude"]) if selected_update_data else float(user["longitude"]),
                format="%.6f",
                step=0.000001,
                key="profile_lon"
            )

        if st.button("Save Location"):
            # Either city or coordinates can be used
            if selected_update_data:
                final_lat = selected_update_data["latitude"]
                final_lon = selected_update_data["longitude"]
                location_name = selected_display_name
            else:
                final_lat = latitude
                final_lon = longitude
                location_name = f"{final_lat:.4f}, {final_lon:.4f}"

            success, message = update_user_location(final_lat, final_lon)

            if success:
                st.rerun()
                st.success(f"Location changed to: {location_name}")
            else:
                st.error(message)

    st.divider()

    # Change password option
    st.subheader("Change password")

    with st.form("change_password_form"):
        old_password = st.text_input(
            "Old password",
            type="password",
            key="old_pw"
        )

        new_password = st.text_input(
            "New password",
            type="password",
            key="new_pw"
        )

        new_password_confirm = st.text_input(
            "Repeat new password",
            type="password",
            key="new_pw_confirm"
        )

        if st.form_submit_button("Save"):
            if not old_password:
                st.error("Missing old password")
            elif not new_password:
                st.error("Missing new password")
            elif new_password != new_password_confirm:
                st.error("Passwords do not match")
            else:
                success, message = change_password(old_password, new_password)
                if success:
                    st.success(message)
                else:
                    st.error(message)

    st.divider()

    if st.button("Back to rooms"):
        session.show_user_profile = False
        st.rerun()



def page_rooms():
    """Rooms overview"""
    render_topbar(show_back=False)

    st.title("My rooms")

    with st.expander("Add new room"):
        new_room_name = st.text_input("Name of room")
        if st.button("Save"):
            if new_room_name:
                create_room(new_room_name)
            else:
                st.warning("Please enter name")
    
    if session.confirm_delete_room_id:
        with st.container(border=True):
            st.warning(
                f"Do you really want to delete the room: "
                f"**{session.confirm_delete_room_name}**?"
            )
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Cancel", use_container_width=True):
                    session.confirm_delete_room_id = None
                    session.confirm_delete_room_name = None
                    st.rerun()

            with col2:
                if st.button("Delete", type="primary", use_container_width=True):
                    delete_room(session.confirm_delete_room_id)
                    session.confirm_delete_room_id = None
                    session.confirm_delete_room_name = None
                    st.rerun()
    rooms = get_rooms()
    
    if not rooms:
        st.info("No rooms found! Please create new rooms!")
        if st.button("Load Testdata"):
            try:
                response = requests.post(
                    f"{API_URL}/import_testdata",
                    headers={"Authorization": f"Bearer {session.token}"}
                )
                if response.status_code == 200:
                    st.success("Imported Testdata succesfully!")
                    st.rerun()
                else:
                    st.error(f"Error: {response.text}")
            except Exception as e:
                st.error(f"API Error: {str(e)}")
        return
    
    cols = st.columns(3)
    for idx, room in enumerate(rooms):
        with cols[idx % 3]:
            with st.container(border=True):
                st.subheader(room['name'])
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"View", key=f"view_{room['id']}"):
                        session.current_room = room['id']
                        session.current_name = room['name']
                        st.rerun()
                with col2:
                    if st.button(f"Delete", key=f"delete_{room['id']}"):
                        session.confirm_delete_room_id = room["id"]
                        session.confirm_delete_room_name = room["name"]
                        st.rerun()



def page_room_detail():
    """Room Details Page"""
    room_id = session.current_room
    render_topbar(show_back=True)
    st.title(session.current_name)
    settings = get_room_settings(room_id)
    
    # Current temperature/Heating Status
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        latest_temp = get_latest_temperature(room_id)
        if latest_temp:
            st.metric("Current temperature:", f"{latest_temp['value']:.1f}°C")
        else:
            st.metric("Current temperature:", "No entries")
    
    with col2:
        if settings:
            current_target = get_current_target_temp(room_id, settings)
            st.metric("Wanted temperature:", f"{current_target:.1f}°C")
        else:
            st.metric("Wanted temperature:", "Please add wanted temperature in the settings")
    
    with col3:
        heating = get_heating_status(room_id)
        if heating:
            status = "🔥ON" if heating["heating_on"] else "❄️OFF"
            st.metric("Heating is:", status)
        else:
            st.metric("Heating is:", "No entries")
    
    with col4:
        weather = get_weather()
        if weather:
            emoji = WEATHER_EMOJI.get(weather["weather_condition"], "🌤️")
            st.metric(
                f"Current weather:",
                f"{weather['temperature']:.1f}°C\n{weather['weather_condition']} {emoji}"
            )
    
    st.divider()
    
    # Temperature graph
    st.subheader("Temperature history")
    show_weather = st.checkbox("Show outdoor temperature", value=True, key="show_weather")
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Start:**")
        col_date1, col_time1 = st.columns(2)
        start_date = col_date1.date_input(
            "Start-Datum",
            value=datetime.now().date() - timedelta(days=1),
            key="start_date"
        )
        start_hour = col_time1.selectbox(
            "Start-Uhrzeit",
            options=[f"{h:02d}:00:00" for h in range(24)],
            index=0,
            key="start_hour"
        )

    with col2:
        st.write("**End:**")
        col_date2, col_time2 = st.columns(2)
        end_date = col_date2.date_input(
            "End-Datum",
            value=datetime.now().date(),
            key="end_date"
        )
        end_hour = col_time2.selectbox(
            "End-Uhrzeit",
            options=[f"{h:02d}:00:00" for h in range(24)],
            index=23,
            key="end_hour"
        )

    # Convert Time to ISO
    start_dt = datetime.combine(start_date, datetime.strptime(start_hour, "%H:%M:%S").time())
    end_dt = datetime.combine(end_date, datetime.strptime(end_hour, "%H:%M:%S").time())

    api_start = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    api_end = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    st.caption(f"Zeitraum: **{start_date} {start_hour} → {end_date} {end_hour}**")
    temps = get_temperature_history(room_id, api_start, api_end)

    # Make graph
    if temps:
        df = pd.DataFrame(temps)
        df["time"] = pd.to_datetime(df["time"], format='ISO8601')
        if df["time"].dt.tz is None:
            df["time"] = df["time"].dt.tz_localize('UTC')
        user_tz = ZoneInfo(session.user_timezone)
        df["time"] = df["time"].dt.tz_convert(user_tz)
        df = df.sort_values("time").reset_index(drop=True)
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["time"].tolist(),
            y=df["value"].tolist(),
            mode='lines+markers',
            name='Indoor Temperature',
            line=dict(color='#FF6B6B', width=2),
            marker=dict(size=4)
        ))
        fig.update_layout(
            title="Temperature history",
            yaxis_title="Temperature (°C)",
            hovermode="x unified",
            legend=dict(
                y=0.1, 
                x=1.06,
                xanchor="center", 
            )
        )

        # Also showing saved weather temperatures (if selected)
        if show_weather:
            weather_data = get_weather_temperatures(api_start, api_end)
            if weather_data:
                weather_df = pd.DataFrame(weather_data)
                weather_df["time"] = pd.to_datetime(weather_df["time"], format='ISO8601')
                if weather_df["time"].dt.tz is None:
                    weather_df["time"] = weather_df["time"].dt.tz_localize('UTC')
                
                user_tz = ZoneInfo(session.user_timezone)
                weather_df["time"] = weather_df["time"].dt.tz_convert(user_tz)
                weather_df = weather_df.sort_values("time").reset_index(drop=True)

                fig.add_trace(go.Scatter(
                    x=weather_df["time"].tolist(),
                    y=weather_df["value"].tolist(),  # ← value statt temperature
                    mode='lines',
                    name='Outdoor temperature',
                    line=dict(color='#87CEEB', width=2)  # Hellblau
                ))
        
        # Add lines for wanted temperatures
        if settings:
            fig.add_hline(
                y=settings["wanted_temp_day"],
                line_dash="dash",
                line_color="green",
                annotation_text="Day wanted",
                annotation_position="right"
            )
            fig.add_hline(
                y=settings["wanted_temp_night"],
                line_dash="dash",
                line_color="blue",
                annotation_text="Night wanted",
                annotation_position="right"
            )
        
        fig.update_layout(
            title="Temperature history",
            xaxis_title="Time",
            yaxis_title="Temperature (°C)",
            hovermode="x unified",
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No temperatures found")
    st.divider()
    
    # Settings for the rooms
    st.subheader("Settings")
    if settings:
        col1, col2 = st.columns(2)
        
        with col1:
            day_temp = st.number_input(
                "Wanted temperature daytime (°C)",
                value=settings["wanted_temp_day"],
                step=0.5
            )
        
        with col2:
            night_temp = st.number_input(
                "Wanted temperature nighttime (°C)",
                value=settings["wanted_temp_night"],
                step=0.5
            )
        
        col1, col2 = st.columns(2)
        
        with col1:
            night_start = st.time_input(
                "Night begins:",
                value=datetime.strptime(settings["night_start"], "%H:%M:%S").time()
            )
        
        with col2:
            night_end = st.time_input(
                "Night ends:",
                value=datetime.strptime(settings["night_end"], "%H:%M:%S").time()
            )
        
        if st.button("Save"):
            update_room_settings(room_id, {
                "timezone": settings["timezone"],
                "wanted_temp_day": day_temp,
                "wanted_temp_night": night_temp,
                "night_start": night_start.strftime("%H:%M:%S"),
                "night_end": night_end.strftime("%H:%M:%S")
            })




# ============ MAIN ============



def main():
    if session.show_user_profile:
        page_user_profile()
    elif session.token is None:
        page_login()
    elif session.current_room is None:
        page_rooms()
    else:
        page_room_detail()




if __name__ == "__main__":
    main()