# Creating the needed SQL tables on startup (if they do not already existed)

import time
from database import MySQLClient
import mysql.connector
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = MySQLClient()

def wait_for_mysql(retries=10, delay=3):
    """ Making sure that SQL is up and running, retrying if it is not """
    for i in range(retries):
        try:
            conn = db._connect()
            conn.close()
            return True
        except mysql.connector.Error:
            logger.error(f"MySQL not ready yet, retry {i+1}/{retries}...")
            time.sleep(delay)
    raise Exception("MySQL did not become ready in time")

def create_tables():
    """ Creating all the needed tables once SQL database is available """
    wait_for_mysql()
    logger.info(f"Creating Tables")
    db.execute_query("CREATE DATABASE IF NOT EXISTS heating_db;", fetch=False)
    db.execute_query("USE heating_db;", fetch=False)
    CREATE_TABLES = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            hashed_password VARCHAR(255) NOT NULL,
            latitude FLOAT DEFAULT 52.52,
            longitude FLOAT DEFAULT 13.40,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS rooms (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            name VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE KEY unique_user_room (user_id, name)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS room_settings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            room_id INT NOT NULL,
            timezone VARCHAR(255) DEFAULT 'Europe/Berlin',
            wanted_temp_day FLOAT DEFAULT 21.0,
            wanted_temp_night FLOAT DEFAULT 18.0,
            night_start TIME DEFAULT '22:00:00',
            night_end TIME DEFAULT '06:00:00',
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
            UNIQUE KEY unique_user_room (user_id, room_id)
        );
        """
    ]

    for query in CREATE_TABLES:
        db.execute_query(query, fetch=False)
    logger.info("MySQL tables created successfully.")

if __name__ == "__main__":
    create_tables()