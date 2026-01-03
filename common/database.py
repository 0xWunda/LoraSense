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
        print("❌ Skip DB Init: No connection")
        return
    
    cursor = None
    try:
        cursor = conn.cursor()
        db_name = os.getenv('MYSQL_DATABASE', 'lorasense_db')
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        cursor.execute(f"USE {db_name}")
        
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
                rain_min_time FLOAT,
                device_id VARCHAR(100)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_sensors (
                user_id INT,
                sensor_id VARCHAR(100),
                PRIMARY KEY (user_id, sensor_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Create default admin user if not exists (password: admin123 - hash is simplified for this demo)
        # In a real app, use werkzeug.security.generate_password_hash
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            print("🔹 Creating default admin user")
            # Using a mock hash for now, app.py will handle verified hashing
            cursor.execute("INSERT INTO users (username, password_hash, is_admin) VALUES ('admin', 'pbkdf2:sha256:260000$mockhash', TRUE)")
        
        # Migration: Ensure device_id column exists if table was already there
        try:
            cursor.execute("SHOW COLUMNS FROM sensor_data LIKE 'device_id'")
            result = cursor.fetchone()
            if not result:
                print("🔹 Migrating: Adding 'device_id' column to sensor_data table")
                cursor.execute("ALTER TABLE sensor_data ADD COLUMN device_id VARCHAR(100)")
        except mysql.connector.Error as err:
            print(f"Migration error: {err}")
            
        conn.commit()
    except mysql.connector.Error as err:
        print(f"Error initializing DB: {err}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def save_sensor_data(raw_payload, decoded, device_id="Unknown"):
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = None
    try:
        cursor = conn.cursor()
        sql = """
            INSERT INTO sensor_data 
            (raw_payload, type, battery, temperature, t_min, t_max, humidity, pressure, irradiation, irr_max, rain, rain_min_time, device_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            decoded.get("Rain_min_time"),
            device_id
        )
        cursor.execute(sql, values)
        conn.commit()
        return True
    except mysql.connector.Error as err:
        print(f"Error saving data: {err}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_latest_data(limit=100, sensor_id=None):
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        if sensor_id:
            cursor.execute("SELECT * FROM sensor_data WHERE device_id = %s ORDER BY timestamp DESC LIMIT %s", (sensor_id, limit))
        else:
            cursor.execute("SELECT * FROM sensor_data ORDER BY timestamp DESC LIMIT %s", (limit,))
            
        rows = cursor.fetchall()
        
        history = []
        for row in rows:
            history.append({
                "sensor_id": row["device_id"] or "Unknown",
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
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_unique_sensors():
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT device_id FROM sensor_data")
        rows = cursor.fetchall()
        return [row[0] for row in rows if row[0]]
    except mysql.connector.Error as err:
        print(f"Error fetching sensors: {err}")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
def get_user_by_username(username):
    conn = get_db_connection()
    if not conn:
        return None
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        return cursor.fetchone()
    except mysql.connector.Error as err:
        print(f"Error fetching user: {err}")
        return None
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def get_allowed_sensors(user_id):
    conn = get_db_connection()
    if not conn:
        return []
    cursor = None
    try:
        cursor = conn.cursor()
        # Admin gets all sensors
        cursor.execute("SELECT is_admin FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        if user and user[0]:
            cursor.execute("SELECT DISTINCT device_id FROM sensor_data")
            return [row[0] for row in cursor.fetchall() if row[0]]
        
        # Regular user gets mapped sensors
        cursor.execute("SELECT sensor_id FROM user_sensors WHERE user_id = %s", (user_id,))
        return [row[0] for row in cursor.fetchall()]
    except mysql.connector.Error as err:
        print(f"Error fetching allowed sensors: {err}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
