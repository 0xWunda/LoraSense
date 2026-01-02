import mysql.connector
import os
import time
from datetime import datetime

def get_db_connection():
    max_retries = 10
    retry_delay = 3
    
    # Credentials from environment variables
    db_host = os.getenv("MYSQL_HOST", "db")
    db_user = os.getenv("MYSQL_USER", "lora_user")
    db_pass = os.getenv("MYSQL_PASSWORD", "lora_pass")
    db_name = os.getenv("MYSQL_DATABASE", "lorasense_db")

    while max_retries > 0:
        try:
            conn = mysql.connector.connect(
                host=db_host,
                user=db_user,
                password=db_pass,
                database=db_name
            )
            return conn
        except mysql.connector.Error as err:
            print(f"Waiting for database... ({max_retries} retries left). Error: {err}")
            max_retries -= 1
            time.sleep(retry_delay)
    
    print("Could not connect to database.")
    return None

def init_db():
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {os.getenv('MYSQL_DATABASE', 'lorasense_db')}")
        cursor.execute("USE " + os.getenv('MYSQL_DATABASE', 'lorasense_db'))
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sensor_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                raw_payload TEXT,
                type INT,
                battery FLOAT,
                temperature FLOAT,
                t_min FLOAT,
                t_max FLOAT,
                humidity FLOAT,
                pressure FLOAT,
                irradiation FLOAT,
                irr_max FLOAT,
                rain FLOAT,
                rain_min_time FLOAT
            )
        """)
        conn.commit()
    except mysql.connector.Error as err:
        print(f"Error initializing DB: {err}")
    finally:
        cursor.close()
        conn.close()

def save_sensor_data(raw_payload, decoded):
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        sql = """
            INSERT INTO sensor_data 
            (raw_payload, type, battery, temperature, t_min, t_max, humidity, pressure, irradiation, irr_max, rain, rain_min_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        values = (
            raw_payload,
            decoded.get("Type"),
            decoded.get("Battery"),
            decoded.get("Temperature"),
            decoded.get("T_min"),
            decoded.get("T_max"),
            decoded.get("Humidity"),
            decoded.get("Pressure"),
            decoded.get("Irradiation"),
            decoded.get("Irr_max"),
            decoded.get("Rain"),
            decoded.get("Rain_min_time")
        )
        cursor.execute(sql, values)
        conn.commit()
        return True
    except mysql.connector.Error as err:
        print(f"Error saving data: {err}")
        return False
    finally:
        cursor.close()
        conn.close()

def get_latest_data(limit=20):
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM sensor_data ORDER BY timestamp DESC LIMIT %s", (limit,))
        rows = cursor.fetchall()
        
        history = []
        for row in rows:
            history.append({
                "timestamp": row["timestamp"].isoformat() if isinstance(row["timestamp"], datetime) else str(row["timestamp"]),
                "decoded": {
                    "Type": row["type"],
                    "Battery": row["battery"],
                    "Temperature": row["temperature"],
                    "T_min": row["t_min"],
                    "T_max": row["t_max"],
                    "Humidity": row["humidity"],
                    "Pressure": row["pressure"],
                    "Irradiation": row["irradiation"],
                    "Irr_max": row["irr_max"],
                    "Rain": row["rain"],
                    "Rain_min_time": row["rain_min_time"]
                }
            })
        return history
    except mysql.connector.Error as err:
        print(f"Error fetching data: {err}")
        return []
    finally:
        cursor.close()
        conn.close()
