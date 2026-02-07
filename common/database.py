import mysql.connector
import sqlite3
import os
import time
from datetime import datetime, timedelta
import random
from werkzeug.security import generate_password_hash

# Load .env manually if exists (for local dev compatibility)
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            if '=' in line:
                key, value = line.strip().split('=', 1)
                if key and not os.getenv(key):
                     os.environ[key] = value

SQLITE_DB_PATH = "/data/lorasense_fallback.db"

class DBConnection:
    """Wrapper to handle differences between MySQL and SQLite connections."""
    def __init__(self, conn, db_type):
        self.conn = conn
        self.db_type = db_type

    def cursor(self, dictionary=False):
        if self.db_type == 'mysql':
            return self.conn.cursor(dictionary=dictionary)
        else:
            if dictionary:
                self.conn.row_factory = sqlite3.Row
            else:
                self.conn.row_factory = None
            return self.conn.cursor()

    def commit(self):
        return self.conn.commit()

    def close(self):
        return self.conn.close()

    def rollback(self):
        return self.conn.rollback()

def normalize_query(sql, db_type):
    """Replaces %s with ? for SQLite queries."""
    if db_type == 'sqlite':
        return sql.replace('%s', '?')
    return sql

def get_db_connection():
    """
    Establishes and returns a connection to the MariaDB database.
    Retries up to 10 times with a 3-second delay if the connection fails.
    Falls back to SQLite if MariaDB is unavailable.
    """
    max_retries = 3 # Reduced for faster fallback in production
    retry_delay = 2
    
    # Credentials from environment variables
    db_host = os.getenv("MYSQL_HOST", "db")
    db_user = os.getenv("MYSQL_USER", "lora_user")
    db_pass = os.getenv("MYSQL_PASSWORD", "lora_pass")
    db_name = os.getenv("MYSQL_DATABASE", "lorasense_db")

    # Try MariaDB first
    for attempt in range(max_retries):
        try:
            conn = mysql.connector.connect(
                host=db_host,
                user=db_user,
                password=db_pass,
                database=db_name,
                connect_timeout=5
            )
            return DBConnection(conn, 'mysql')
        except mysql.connector.Error as err:
            print(f"Waiting for MariaDB... ({max_retries - attempt - 1} retries left). Error: {err}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    
    # Fallback to SQLite
    print("WARNING: MariaDB unavailable. Falling back to SQLite.")
    try:
        # Ensure data directory exists (if running outside docker)
        dir_name = os.path.dirname(SQLITE_DB_PATH)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        conn = sqlite3.connect(SQLITE_DB_PATH)
        return DBConnection(conn, 'sqlite')
    except Exception as e:
        print(f"ERROR: Critical Error: Could not connect to SQLite fallback: {e}")
        return None

def init_db():
    """
    Initializes the database schema by creating necessary tables if they don't exist.
    Also handles migrations for legacy versions (e.g., adding columns) and seeds default users.
    """
    conn = get_db_connection()
    if not conn:
        print("Skip DB Init: No connection")
        return
    
    cursor = None
    try:
        cursor = conn.cursor()
        db_type = conn.db_type
        
        if db_type == 'mysql':
            db_name = os.getenv('MYSQL_DATABASE', 'lorasense_db')
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
            cursor.execute(f"USE {db_name}")
        
        # Table definitions (standard SQL used, works on both mostly)
        # Replacing AUTO_INCREMENT with AUTOINCREMENT logic if needed, but INT PRIMARY KEY is usually enough in SQLite
        def exec_q(sql, params=()):
            cursor.execute(normalize_query(sql, db_type), params)

        exec_q(f"""
            CREATE TABLE IF NOT EXISTS sensor_data (
                id INTEGER PRIMARY KEY {"AUTO_INCREMENT" if db_type == "mysql" else "AUTOINCREMENT"},
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

        exec_q(f"""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY {"AUTO_INCREMENT" if db_type == "mysql" else "AUTOINCREMENT"},
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE
            )
        """)

        exec_q("""
            CREATE TABLE IF NOT EXISTS user_sensors (
                user_id INT,
                sensor_id VARCHAR(100),
                PRIMARY KEY (user_id, sensor_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        exec_q(f"""
            CREATE TABLE IF NOT EXISTS sensor_types (
                id INTEGER PRIMARY KEY {"AUTO_INCREMENT" if db_type == "mysql" else "AUTOINCREMENT"},
                name VARCHAR(100) UNIQUE NOT NULL,
                decoder_config TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        exec_q(f"""
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY {"AUTO_INCREMENT" if db_type == "mysql" else "AUTOINCREMENT"},
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

        exec_q(f"""
            CREATE TABLE IF NOT EXISTS uplinks (
                id INTEGER PRIMARY KEY {"AUTO_INCREMENT" if db_type == "mysql" else "AUTOINCREMENT"},
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

        # Migration logic (simplified for SQLite as it starts blank usually)
        if db_type == 'mysql':
            try:
                cursor.execute("SHOW COLUMNS FROM users LIKE 'is_admin'")
                if not cursor.fetchone():
                    print("Migrating: Adding 'is_admin' column to users table")
                    cursor.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")
            except mysql.connector.Error as err:
                print(f"Migration error (is_admin): {err}")
        else:
            # SQLite handles PRAGMA table_info(users)
            cursor.execute("PRAGMA table_info(users)")
            cols = [c[1] for c in cursor.fetchall()]
            if 'is_admin' not in cols:
                cursor.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")

        # Create default admin user if not exists
        exec_q("SELECT id FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            print("Creating default admin user")
            pw_hash = generate_password_hash("admin123") 
            exec_q("INSERT INTO users (username, password_hash, is_admin) VALUES ('admin', %s, TRUE)", (pw_hash,))
        else:
             print("Updating admin user permissions")
             exec_q("UPDATE users SET is_admin = TRUE WHERE username = 'admin'")
            
        exec_q("SELECT id FROM users WHERE username = 'testuser'")
        test_user = cursor.fetchone()
        if not test_user:
            print("Creating test user")
            pw_hash = generate_password_hash("test123")
            exec_q("INSERT INTO users (username, password_hash, is_admin) VALUES ('testuser', %s, FALSE)", (pw_hash,))
            exec_q("SELECT id FROM users WHERE username = 'testuser'")
            res = cursor.fetchone()
            test_user_id = res['id'] if isinstance(res, dict) else res[0]
        else:
             test_user_id = test_user['id'] if isinstance(test_user, dict) else test_user[0]

        for i in range(1, 3):
            u_name = f"testuser{i}"
            exec_q("SELECT id FROM users WHERE username = %s", (u_name,))
            if not cursor.fetchone():
                 print(f"Creating {u_name}")
                 pw_hash = generate_password_hash(f"test{i}123")
                 exec_q("INSERT INTO users (username, password_hash, is_admin) VALUES (%s, %s, FALSE)", (u_name, pw_hash))

        exec_q("SELECT id FROM sensor_types LIMIT 1")
        if not cursor.fetchone():
            print("Seeding sensor types")
            exec_q("INSERT INTO sensor_types (name, decoder_config) VALUES ('Barani MeteoHelix', 'v1')")
            exec_q("INSERT INTO sensor_types (name, decoder_config) VALUES ('Dragino LHT65', 'v1')")
            exec_q("INSERT INTO sensor_types (name, decoder_config) VALUES ('Custom Payload', 'custom')")
        
        if db_type == 'mysql':
            try:
                cursor.execute("SHOW COLUMNS FROM sensor_data LIKE 'device_id'")
                if not cursor.fetchone():
                    print("Migrating: Adding 'device_id' column to sensor_data table")
                    cursor.execute("ALTER TABLE sensor_data ADD COLUMN device_id VARCHAR(100)")
            except mysql.connector.Error as err:
                print(f"Migration error: {err}")
        else:
            cursor.execute("PRAGMA table_info(sensor_data)")
            cols = [c[1] for c in cursor.fetchall()]
            if 'device_id' not in cols:
                cursor.execute("ALTER TABLE sensor_data ADD COLUMN device_id VARCHAR(100)")

        conn.commit()
    except Exception as err:
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

def save_sensor_data(raw_payload, decoded, device_id="Unknown", timestamp=None):
    """
    Saves decoded sensor measurement data into the sensor_data table.
    """
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = None
    try:
        cursor = conn.cursor()
        db_type = conn.db_type
        
        if timestamp:
            sql = """
                INSERT INTO sensor_data 
                (timestamp, raw_payload, type, battery, temperature, t_min, t_max, humidity, pressure, irradiation, irr_max, rain, rain_min_time, device_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            values = (
                timestamp,
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
        else:
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
        cursor.execute(normalize_query(sql, db_type), values)
        conn.commit()
        return True
    except Exception as err:
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
        db_type = conn.db_type
        if sensor_id:
            sql = "SELECT * FROM sensor_data WHERE device_id = %s ORDER BY timestamp DESC LIMIT %s"
            cursor.execute(normalize_query(sql, db_type), (sensor_id, limit))
        else:
            sql = "SELECT * FROM sensor_data ORDER BY timestamp DESC LIMIT %s"
            cursor.execute(normalize_query(sql, db_type), (limit,))
            
        rows = cursor.fetchall()
        
        history = []
        for row in rows:
            # Handle potential string timestamps from SQLite
            ts = row["timestamp"]
            if isinstance(ts, str):
                try:
                    ts = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                except:
                    pass

            history.append({
                "sensor_id": row["device_id"] or "Unknown",
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime) else str(ts),
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
    except Exception as err:
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
        db_type = conn.db_type
        sql = "SELECT DISTINCT device_id FROM sensor_data"
        cursor.execute(normalize_query(sql, db_type))
        rows = cursor.fetchall()
        return [row[0] for row in rows if row[0]]
    except Exception as err:
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
        db_type = conn.db_type
        sql = "SELECT * FROM users WHERE username = %s"
        cursor.execute(normalize_query(sql, db_type), (username,))
        return cursor.fetchone()
    except Exception as err:
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
        db_type = conn.db_type
        sql = "SELECT id, username, is_admin FROM users"
        cursor.execute(normalize_query(sql, db_type))
        return cursor.fetchall()
    except Exception as err:
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
        db_type = conn.db_type
        # Delete existing mappings
        sql_del = "DELETE FROM user_sensors WHERE user_id = %s"
        cursor.execute(normalize_query(sql_del, db_type), (user_id,))
        
        # Insert new mappings
        if sensor_ids:
            sql_ins = "INSERT INTO user_sensors (user_id, sensor_id) VALUES (%s, %s)"
            if db_type == 'mysql':
                values = [(user_id, s_id) for s_id in sensor_ids]
                cursor.executemany(sql_ins, values)
            else:
                # SQLite executemany works similar but parameters are different
                for s_id in sensor_ids:
                    cursor.execute(normalize_query(sql_ins, db_type), (user_id, s_id))
        
        conn.commit()
        return True
    except Exception as err:
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
        db_type = conn.db_type
        # Admin gets all sensors
        sql_admin_check = "SELECT is_admin FROM users WHERE id = %s"
        cursor.execute(normalize_query(sql_admin_check, db_type), (user_id,))
        user_row = cursor.fetchone()
        
        # Consistent row access
        is_admin = False
        if user_row:
            if isinstance(user_row, dict):
                is_admin = user_row.get('is_admin')
            else:
                is_admin = user_row[0]

        if is_admin:
            # Return unique IDs from both devices table and sensor_data table
            sql_union = """
                SELECT dev_eui FROM devices 
                UNION 
                SELECT DISTINCT device_id FROM sensor_data
            """
            cursor.execute(normalize_query(sql_union, db_type))
            return [row[0] for row in cursor.fetchall() if row[0]]
        
        # Regular user gets mapped sensors
        sql_user_sensors = "SELECT sensor_id FROM user_sensors WHERE user_id = %s"
        cursor.execute(normalize_query(sql_user_sensors, db_type), (user_id,))
        return [row[0] for row in cursor.fetchall()]
    except Exception as err:
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
        db_type = conn.db_type
        sql = "INSERT INTO users (username, password_hash, is_admin) VALUES (%s, %s, %s)"
        cursor.execute(normalize_query(sql, db_type), (username, pw_hash, is_admin))
        conn.commit()
        return True
    except Exception as err:
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
        db_type = conn.db_type
        sql = """INSERT INTO devices 
                 (dev_eui, name, sensor_type_id, tenant_id, join_eui, app_key, nwk_key) 
                 VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        cursor.execute(normalize_query(sql, db_type), (dev_eui, name, sensor_type_id, tenant_id, join_eui, app_key, nwk_key))
        conn.commit()
        return True
    except Exception as err:
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
        db_type = conn.db_type
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
            
        cursor.execute(normalize_query(sql, db_type), params)
        return cursor.fetchall()
    except Exception as err:
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
        db_type = conn.db_type
        sql = """
            SELECT d.*, st.decoder_config 
            FROM devices d 
            LEFT JOIN sensor_types st ON d.sensor_type_id = st.id 
            WHERE d.dev_eui = %s
        """
        cursor.execute(normalize_query(sql, db_type), (dev_eui,))
        return cursor.fetchone()
    except Exception as err:
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
        db_type = conn.db_type
        sql = "UPDATE devices SET status = %s WHERE dev_eui = %s"
        cursor.execute(normalize_query(sql, db_type), (status, dev_eui))
        conn.commit()
        return True
    except Exception as err:
        print(f"Error updating device status: {err}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def delete_device(dev_eui):
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        db_type = conn.db_type
        
        # 1. Delete from user_sensors mapping
        sql1 = "DELETE FROM user_sensors WHERE sensor_id = %s"
        cursor.execute(normalize_query(sql1, db_type), (dev_eui,))
        
        # 2. Delete from sensor_data
        sql2 = "DELETE FROM sensor_data WHERE device_id = %s"
        cursor.execute(normalize_query(sql2, db_type), (dev_eui,))
        
        # 3. Delete from uplinks
        sql3 = "DELETE FROM uplinks WHERE dev_eui = %s"
        cursor.execute(normalize_query(sql3, db_type), (dev_eui,))
        
        # 4. Finally delete the device itself
        sql4 = "DELETE FROM devices WHERE dev_eui = %s"
        cursor.execute(normalize_query(sql4, db_type), (dev_eui,))
        
        conn.commit()
        return True
    except Exception as err:
        print(f"Error deleting device: {err}")
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
        db_type = conn.db_type
        sql = "SELECT * FROM sensor_types"
        cursor.execute(normalize_query(sql, db_type))
        return cursor.fetchall()
    except Exception as err:
        print(f"Error getting sensor types: {err}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- Uplink Functions ---

def save_uplink(dev_eui, payload_raw, fcnt=0, port=1, rssi=0, snr=0, device_db_id=None, received_at=None):
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        db_type = conn.db_type
        if received_at:
             sql = """
                INSERT INTO uplinks (device_id, dev_eui, fcnt, port, payload_raw, rssi, snr, received_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
             cursor.execute(normalize_query(sql, db_type), (device_db_id, dev_eui, fcnt, port, payload_raw, rssi, snr, received_at))
        else:
            sql = """
                INSERT INTO uplinks (device_id, dev_eui, fcnt, port, payload_raw, rssi, snr)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(normalize_query(sql, db_type), (device_db_id, dev_eui, fcnt, port, payload_raw, rssi, snr))
        conn.commit()
        return True
    except Exception as err:
        print(f"Error saving uplink: {err}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
