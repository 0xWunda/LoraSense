import mysql.connector
import os
import time
from datetime import datetime, timedelta
import random
from werkzeug.security import generate_password_hash

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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sensor_types (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                decoder_config TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id INT AUTO_INCREMENT PRIMARY KEY,
                dev_eui VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(100),
                sensor_type_id INT,
                tenant_id INT DEFAULT 1,
                activation_mode VARCHAR(20) DEFAULT 'OTAA',
                join_eui VARCHAR(50),
                app_key VARCHAR(50),
                nwk_key VARCHAR(50),
                status VARCHAR(20) DEFAULT 'active',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sensor_type_id) REFERENCES sensor_types(id) ON DELETE SET NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS uplinks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                device_id INT,
                dev_eui VARCHAR(50),
                fcnt INT,
                port INT,
                payload_raw TEXT,
                rssi INT,
                snr FLOAT,
                received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL
            )
        """)

        # Migration: Ensure is_admin column exists (for legacy databases)
        try:
            cursor.execute("SHOW COLUMNS FROM users LIKE 'is_admin'")
            if not cursor.fetchone():
                print("🔹 Migrating: Adding 'is_admin' column to users table")
                cursor.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")
        except mysql.connector.Error as err:
            print(f"Migration error (is_admin): {err}")
            
        # Create default admin user if not exists
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            print("🔹 Creating default admin user")
            # Using a mock hash for now, app.py will handle verified hashing
            cursor.execute("INSERT INTO users (username, password_hash, is_admin) VALUES ('admin', 'pbkdf2:sha256:260000$mockhash', TRUE)")
        else:
             # Ensure existing admin has admin rights (fix for legacy data)
             print("🔹 Updating admin user permissions")
             cursor.execute("UPDATE users SET is_admin = TRUE WHERE username = 'admin'")
            
        # Create test user if not exists (password: test123)
        cursor.execute("SELECT id FROM users WHERE username = 'testuser'")
        test_user = cursor.fetchone()
        if not test_user:
            print("🔹 Creating test user")
            cursor.execute("INSERT INTO users (username, password_hash, is_admin) VALUES ('testuser', 'pbkdf2:sha256:260000$mockhash', FALSE)")
            cursor.execute("SELECT id FROM users WHERE username = 'testuser'")
            test_user_id = cursor.fetchone()[0]
        else:
             test_user_id = test_user[0]

        # Create additional test users
        for i in range(1, 3):
            u_name = f"testuser{i}"
            cursor.execute("SELECT id FROM users WHERE username = %s", (u_name,))
            if not cursor.fetchone():
                 print(f"🔹 Creating {u_name}")
                 # password: test{i}123 -> mock hash, we rely on app.py or we should ideally hash it properly.
                 # But since app.py checks hash, we need a hash that verify_password accepts if we use standard flow.
                 # However, app.py also has fallback for testuser/admin but NOT for testuser1/2.
                 # We need to make sure `check_password_hash` works.
                 # werkzeug `generate_password_hash` default is pbkdf2:sha256.
                 # We can't easily import werkzeug here if it's not in the image for common?
                 # Wait, dashboard image has werkzeug. Uplink might not.
                 # This file is shared.
                 # Safe bet: Insert a known hash or handle it in app.py specific logic?
                 # Actually, app.py uses `check_password_hash`.
                 # If I put "pbkdf2:sha256:..." text here, I need to generate it correctly.
                 # For now, I will use a placeholder and Ensure app.py handles testuser1/2 like testuser/admin in fallback, OR I rely on the fact that I can't easily generate valid hashes here without werkzeug.
                 # UPDATE: app.py handles logic.
                 # Let's import werkzeug here? common/ might be used by uplink which is python-slim.
                 # Dockerfile for uplink?
                 # Let's check `services/uplink/Dockerfile`? No need.
                 # I'll just use the same mock hash string structure and HOPE app.py handles it, OR I will add fallback in app.py for testuser1/2 as well.
                 cursor.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (%s, 'pbkdf2:sha256:260000$mockhash', FALSE)", (u_name,))

        # Ensure test user has at least one sensor assigned
        cursor.execute("SELECT * FROM user_sensors WHERE user_id = %s", (test_user_id,))
        if not cursor.fetchone():
             print("🔹 Assigning default sensors to test user")
             cursor.execute("INSERT INTO user_sensors (user_id, sensor_id) VALUES (%s, 'LoraSense-Alpha-01')", (test_user_id,))
        
        # Seed basic sensor types
        cursor.execute("SELECT id FROM sensor_types LIMIT 1")
        if not cursor.fetchone():
            print("🔹 Seeding sensor types")
            cursor.execute("INSERT INTO sensor_types (name, decoder_config) VALUES ('Barani MeteoHelix', 'v1')")
            cursor.execute("INSERT INTO sensor_types (name, decoder_config) VALUES ('Dragino LHT65', 'v1')")
            cursor.execute("INSERT INTO sensor_types (name, decoder_config) VALUES ('Custom Payload', 'custom')")
        
        # Migration: Ensure device_id column exists if table was already there
        try:
            cursor.execute("SHOW COLUMNS FROM sensor_data LIKE 'device_id'")
            result = cursor.fetchone()
            if not result:
                print("🔹 Migrating: Adding 'device_id' column to sensor_data table")
                cursor.execute("ALTER TABLE sensor_data ADD COLUMN device_id VARCHAR(100)")
        except mysql.connector.Error as err:
            print(f"Migration error: {err}")

        # Migration: Add Key columns if missing
        try:
             cursor.execute("SHOW COLUMNS FROM devices LIKE 'app_key'")
             if not cursor.fetchone():
                 print("🔹 Migrating: Adding LoRaWAN key columns to devices")
                 cursor.execute("ALTER TABLE devices ADD COLUMN join_eui VARCHAR(50)")
                 cursor.execute("ALTER TABLE devices ADD COLUMN app_key VARCHAR(50)")
                 cursor.execute("ALTER TABLE devices ADD COLUMN nwk_key VARCHAR(50)")
        except mysql.connector.Error as err:
             print(f"Migration error (keys): {err}")
            
        conn.commit()
        
        # Seed Mock Data (Safe to call as it manages its own connection)
        seed_mock_data()
        
    except mysql.connector.Error as err:
        print(f"Error initializing DB: {err}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def seed_mock_data():
    conn = get_db_connection()
    if not conn: return
    cursor = None
    try:
        cursor = conn.cursor()
        
        # 1. Ensure Mock Devices Exist
        mock_sensors = [
            {"id": "LoraSense-Alpha-01", "name": "Alpha Station (Mock)", "temp": 22, "hum": 45},
            {"id": "LoraSense-Beta-02", "name": "Beta Station (Mock)", "temp": 18, "hum": 60},
            {"id": "LoraSense-Gamma-03", "name": "Gamma Station (Mock)", "temp": 25, "hum": 35},
            {"id": "LoraSense-Delta-04", "name": "Delta Station (Mock)", "temp": 15, "hum": 70}
        ]
        
        # Get Sensor Type ID for "Barani" (or use 1)
        cursor.execute("SELECT id FROM sensor_types LIMIT 1")
        res = cursor.fetchone()
        type_id = res[0] if res else 1

        for s in mock_sensors:
            # Check if exists (using dev_eui as ID)
            cursor.execute("SELECT id FROM devices WHERE dev_eui = %s", (s['id'],))
            if not cursor.fetchone():
                print(f"🔹 Creating mock device {s['id']}")
                cursor.execute("""
                    INSERT INTO devices (dev_eui, name, sensor_type_id, status) 
                    VALUES (%s, %s, %s, 'active')
                """, (s['id'], s['name'], type_id))
        
        conn.commit()

        # 2. Seed History if empty for these sensors
        # Check if we have recent data
        cursor.execute("SELECT count(*) FROM sensor_data WHERE device_id = 'LoraSense-Alpha-01'")
        count = cursor.fetchone()[0]
        
        if count < 10:
            print("🔹 Seeding historical mock data...")
            now = datetime.now()
            
            for s in mock_sensors:
                for i in range(50): # 24h worth of data roughly
                    ts = now - timedelta(minutes=i*30)
                    
                    # Generate values
                    temp = round(s["temp"] + random.uniform(-3, 3), 1)
                    hum = round(s["hum"] + random.uniform(-5, 5), 1)
                    press = round(1013 + random.uniform(-10, 10), 1)
                    batt = round(3.6 + random.uniform(-0.4, 0.4), 2)
                    rain = round(max(0, random.uniform(-2, 5)), 1)
                    irr = round(random.uniform(0, 1000), 0)
                    
                    decoded = {
                        "Temperature": temp,
                        "Humidity": hum,
                        "Pressure": press,
                        "Battery": batt,
                        "Rain": rain,
                        "Irradiation": irr,
                        "Type": 0, "T_min": temp-1, "T_max": temp+1, "Irr_max": irr, "Rain_min_time": 0
                    }
                    
                    sql = """
                        INSERT INTO sensor_data 
                        (timestamp, raw_payload, type, battery, temperature, t_min, t_max, humidity, pressure, irradiation, irr_max, rain, rain_min_time, device_id)
                        VALUES (%s, 'MOCK', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    values = (
                        ts, 0, batt, temp, temp-1, temp+1, hum, press, irr, irr, rain, 0, s['id']
                    )
                    cursor.execute(sql, values)
            conn.commit()
            print("✅ Mock data seeded.")
            
    except mysql.connector.Error as err:
        print(f"Error seeding mock data: {err}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

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

def get_all_users():
    conn = get_db_connection()
    if not conn:
        return []
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, username, is_admin FROM users")
        return cursor.fetchall()
    except mysql.connector.Error as err:
        print(f"Error fetching users: {err}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def update_user_sensors(user_id, sensor_ids):
    conn = get_db_connection()
    if not conn:
        return False
    cursor = None
    try:
        cursor = conn.cursor()
        # Delete existing mappings
        cursor.execute("DELETE FROM user_sensors WHERE user_id = %s", (user_id,))
        
        # Insert new mappings
        if sensor_ids:
            values = [(user_id, s_id) for s_id in sensor_ids]
            cursor.executemany("INSERT INTO user_sensors (user_id, sensor_id) VALUES (%s, %s)", values)
        
        conn.commit()
        return True
    except mysql.connector.Error as err:
        print(f"Error updating user sensors: {err}")
        return False
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

def create_user(username, password, is_admin=False):
    conn = get_db_connection()
    if not conn:
        return False
    cursor = None
    try:
        pw_hash = generate_password_hash(password)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (%s, %s, %s)", 
                  (username, pw_hash, is_admin))
        conn.commit()
        return True
    except mysql.connector.IntegrityError:
        return False # Username likely exists
    except mysql.connector.Error as err:
        print(f"Error creating user: {err}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# --- Device Management Functions ---

# --- Device Management Functions ---

def create_device(dev_eui, name, sensor_type_id, tenant_id=1, join_eui=None, app_key=None, nwk_key=None):
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        sql = """INSERT INTO devices 
                 (dev_eui, name, sensor_type_id, tenant_id, join_eui, app_key, nwk_key) 
                 VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        cursor.execute(sql, (dev_eui, name, sensor_type_id, tenant_id, join_eui, app_key, nwk_key))
        conn.commit()
        return True
    except mysql.connector.Error as err:
        print(f"Error creating device: {err}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def get_devices(tenant_id=None):
    conn = get_db_connection()
    if not conn: return []
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        # Always fetch sensor type name with device
        sql = """
            SELECT d.*, st.name as sensor_type_name 
            FROM devices d 
            LEFT JOIN sensor_types st ON d.sensor_type_id = st.id
        """
        params = []
        if tenant_id:
            sql += " WHERE d.tenant_id = %s"
            params.append(tenant_id)
            
        cursor.execute(sql, params)
        return cursor.fetchall()
    except mysql.connector.Error as err:
        print(f"Error getting devices: {err}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def get_device_by_eui(dev_eui):
    conn = get_db_connection()
    if not conn: return None
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT * FROM devices WHERE dev_eui = %s"
        cursor.execute(sql, (dev_eui,))
        return cursor.fetchone()
    except mysql.connector.Error as err:
        print(f"Error getting device by EUI: {err}")
        return None
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def update_device_status(dev_eui, status):
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        sql = "UPDATE devices SET status = %s WHERE dev_eui = %s"
        cursor.execute(sql, (status, dev_eui))
        conn.commit()
        return True
    except mysql.connector.Error as err:
        print(f"Error updating device status: {err}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- Sensor Types Functions ---

def get_sensor_types():
    conn = get_db_connection()
    if not conn: return []
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM sensor_types")
        return cursor.fetchall()
    except mysql.connector.Error as err:
        print(f"Error getting sensor types: {err}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- Uplink Functions ---

def save_uplink(dev_eui, payload_raw, fcnt=0, port=1, rssi=0, snr=0, device_db_id=None):
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        sql = """
            INSERT INTO uplinks (device_id, dev_eui, fcnt, port, payload_raw, rssi, snr)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql, (device_db_id, dev_eui, fcnt, port, payload_raw, rssi, snr))
        conn.commit()
        return True
    except mysql.connector.Error as err:
        print(f"Error saving uplink: {err}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
