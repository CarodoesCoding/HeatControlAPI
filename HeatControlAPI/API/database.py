## Connects with SQL Database and creates a function to query to prevent SQL injection

import os
import mysql.connector
from mysql.connector import Error
import logging
from typing import Optional, List, Dict, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MySQLClient:
    def __init__(self):
        self.config = {
            "host": str(os.getenv("MYSQL_HOST", "sql_db")),
            "port": int(os.getenv("MYSQL_PORT", 3306)),
            "user": str(os.getenv("MYSQL_USER", "user")),
            "password": str(os.getenv("MYSQL_PASSWORD", "password")),
            "database": str(os.getenv("MYSQL_DB", "heating_db")),
        }

    def _connect(self):
        """Function to do SQL query using parameterized queries to preven SQL Injection."""
        try:
            return mysql.connector.connect(**self.config)
        except Error as e:
            logger.error(f"MySQL connection failed: {e}")
            raise
    # Function to prevent SQL Injection
    def execute_query(
        self,
        query: str,
        params: Optional[Tuple] = None,
        fetch: bool = True
    ) -> Optional[List[Dict]]:
        conn = None
        try:
            conn = self._connect()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(query, params)

            if fetch:
                results = cursor.fetchall()
                cursor.close()
                return results
            else:
                conn.commit()
                cursor.close()
                return None

        except Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Query failed: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def execute_many(self, query: str, params_list: List[Tuple]):
        """
        Function to do SQL query batch using parameterized queries to preven SQL Injection.
        """
        conn = None
        try:
            conn = self._connect()
            cursor = conn.cursor()

            cursor.executemany(query, params_list)
            conn.commit()
            cursor.close()

        except Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Batch execution failed: {e}")
            raise
        finally:
            if conn:
                conn.close()