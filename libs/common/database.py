"""
Dieses Modul verwaltet alle Datenbankinteraktionen für das LoraSense-Projekt.
Es unterstützt sowohl MariaDB (Produktion) als auch SQLite (Fallback/Lokale Entwicklung).
"""

import mysql.connector
import sqlite3
import os
import time
from datetime import datetime, timedelta
import random
from werkzeug.security import generate_password_hash
from .logging_config import setup_logging

# Setup Logging
# Da database.py von mehreren Services genutzt wird, verwenden wir einen "database" Logger
logger = setup_logging("database")

# .env manuell laden, falls vorhanden (für lokale Entwicklungskompatibilität)
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            if '=' in line:
                key, value = line.strip().split('=', 1)
                if key and not os.getenv(key):
                     os.environ[key] = value

# Pfad zur SQLite-Fallback-Datenbank im neuen storage-System
SQLITE_DB_PATH = "/storage/data/lorasense_fallback.db"

class DBConnection:
    """
    Ein Wrapper-Klasse, um die Unterschiede zwischen MariaDB- und SQLite-Verbindungen zu vereinheitlichen.
    """
    def __init__(self, conn, db_type):
        """
        Initialisiert die Verbindung.
        
        Args:
            conn: Das native Verbindungsobjekt (mysql.connector oder sqlite3).
            db_type (str): 'mysql' oder 'sqlite'.
        """
        self.conn = conn
        self.db_type = db_type

    def cursor(self, dictionary=False):
        """
        Erstellt einen Cursor für die Datenbankabfrage.
        
        Args:
            dictionary (bool): Falls True, werden Ergebnisse als Dictionary (Spaltenname -> Wert) zurückgegeben.
            
        Returns:
            Ein Cursor-Objekt.
        """
        if self.db_type == 'mysql':
            return self.conn.cursor(dictionary=dictionary)
        else:
            if dictionary:
                self.conn.row_factory = sqlite3.Row
            else:
                self.conn.row_factory = None
            return self.conn.cursor()

    def commit(self):
        """Bestätigt die aktuelle Transaktion."""
        return self.conn.commit()

    def close(self):
        """Schließt die Datenbankverbindung."""
        return self.conn.close()

    def rollback(self):
        """Rollback der aktuellen Transaktion im Fehlerfall."""
        return self.conn.rollback()

def normalize_query(sql, db_type):
    """
    Passt SQL-Queries an den Datenbanktyp an (z.B. %s Platzhalter für MySQL zu ? für SQLite).
    
    Args:
        sql (str): Der SQL-String.
        db_type (str): 'mysql' oder 'sqlite'.
        
    Returns:
        str: Die angepasste SQL-Query.
    """
    if db_type == 'sqlite':
        return sql.replace('%s', '?')
    return sql

def get_db_connection():
    """
    Baut eine Verbindung zur MariaDB auf. Falls diese fehlschlägt (nach Retries),
    wird automatisch auf SQLite ausgewichen.
    
    Returns:
        DBConnection: Ein Wrapper-Objekt der Verbindung oder None bei fatalem Fehler.
    """
    max_retries = 3 # Reduziert für schnelleres Fallback in der Produktion
    retry_delay = 2
    
    # Anmeldedaten aus Umgebungsvariablen laden
    db_host = os.getenv("MYSQL_HOST", "db")
    db_user = os.getenv("MYSQL_USER", "lora_user")
    db_pass = os.getenv("MYSQL_PASSWORD", "lora_pass")
    db_name = os.getenv("MYSQL_DATABASE", "lorasense_db")

    # Zuerst MariaDB versuchen
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
            logger.warning(f"Warten auf MariaDB... ({max_retries - attempt - 1} Versuche übrig). Fehler: {err}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    
    # Fallback auf SQLite, falls MariaDB nicht erreichbar ist
    logger.warning("MariaDB nicht verfügbar. Nutze SQLite Fallback.")
    try:
        # Sicherstellen, dass das Datenverzeichnis existiert
        dir_name = os.path.dirname(SQLITE_DB_PATH)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        conn = sqlite3.connect(SQLITE_DB_PATH)
        return DBConnection(conn, 'sqlite')
    except Exception as e:
        logger.error(f"Kritischer Fehler: Verbindung zum SQLite-Fallback fehlgeschlagen: {e}")
        return None

def init_db():
    """
    Initialisiert das Datenbank-Schema. Erstellt Tabellen, falls diese nicht existieren,
    führt einfache Migrationen durch und legt Standard-Benutzer an.
    """
    conn = get_db_connection()
    if not conn:
        logger.error("DB-Init übersprungen: Keine Verbindung möglich")
        return
    
    cursor = None
    try:
        cursor = conn.cursor()
        db_type = conn.db_type
        
        # Falls MariaDB: Datenbank erstellen, falls sie noch nicht existiert
        if db_type == 'mysql':
            db_name = os.getenv('MYSQL_DATABASE', 'lorasense_db')
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
            cursor.execute(f"USE {db_name}")
        
        # Hilfsfunktion zum Ausführen von Queries mit automatischer Platzhalter-Anpassung
        def exec_q(sql, params=()):
            cursor.execute(normalize_query(sql, db_type), params)

        # 1. Tabelle für Sensordaten (Messwerte)
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

        # 2. Tabelle für Benutzer
        exec_q(f"""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY {"AUTO_INCREMENT" if db_type == "mysql" else "AUTOINCREMENT"},
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE
            )
        """)

        # 3. Mappings von Benutzern zu erlaubten Sensoren (ACL)
        exec_q("""
            CREATE TABLE IF NOT EXISTS user_sensors (
                user_id INT,
                sensor_id VARCHAR(100),
                PRIMARY KEY (user_id, sensor_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # 4. Definition von Sensortypen (für verschiedene Decoder)
        exec_q(f"""
            CREATE TABLE IF NOT EXISTS sensor_types (
                id INTEGER PRIMARY KEY {"AUTO_INCREMENT" if db_type == "mysql" else "AUTOINCREMENT"},
                name VARCHAR(100) UNIQUE NOT NULL,
                decoder_config TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 5. Registrierte Geräte (Sensoren)
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

        # 6. Tabelle für rohe Uplink-Logs (Debugging)
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

        # --- Migrationen ---
        # Fügt Spalten hinzu, die in älteren Versionen des Schemas fehlten
        if db_type == 'mysql':
            try:
                cursor.execute("SHOW COLUMNS FROM users LIKE 'is_admin'")
                if not cursor.fetchone():
                    print("Migration: 'is_admin' Spalte zur Tabelle users hinzugefügt")
                    cursor.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")
            except mysql.connector.Error as err:
                print(f"Migrationsfehler (is_admin): {err}")
        else:
            cursor.execute("PRAGMA table_info(users)")
            cols = [c[1] for c in cursor.fetchall()]
            if 'is_admin' not in cols:
                cursor.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")

        # Standard-Admin anlegen falls nicht vorhanden
        exec_q("SELECT id FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            print("Erstelle Standard-Admin-Benutzer")
            pw_hash = generate_password_hash("admin123") 
            exec_q("INSERT INTO users (username, password_hash, is_admin) VALUES ('admin', %s, TRUE)", (pw_hash,))
        else:
             exec_q("UPDATE users SET is_admin = TRUE WHERE username = 'admin'")
            
        # Test-Benutzer anlegen
        exec_q("SELECT id FROM users WHERE username = 'testuser'")
        test_user = cursor.fetchone()
        if not test_user:
            print("Erstelle Test-Benutzer")
            pw_hash = generate_password_hash("test123")
            exec_q("INSERT INTO users (username, password_hash, is_admin) VALUES ('testuser', %s, FALSE)", (pw_hash,))
        
        # Weitere Test-Benutzer für Demos
        for i in range(1, 3):
            u_name = f"testuser{i}"
            exec_q("SELECT id FROM users WHERE username = %s", (u_name,))
            if not cursor.fetchone():
                 print(f"Erstelle {u_name}")
                 pw_hash = generate_password_hash(f"test{i}123")
                 exec_q("INSERT INTO users (username, password_hash, is_admin) VALUES (%s, %s, FALSE)", (u_name, pw_hash))

        # Sensortypen initial befüllen
        exec_q("SELECT id FROM sensor_types LIMIT 1")
        if not cursor.fetchone():
            print("Befülle Sensortypen")
            exec_q("INSERT INTO sensor_types (name, decoder_config) VALUES ('Barani MeteoHelix', 'v1')")
            exec_q("INSERT INTO sensor_types (name, decoder_config) VALUES ('Dragino LHT65', 'v1')")
            exec_q("INSERT INTO sensor_types (name, decoder_config) VALUES ('Custom Payload', 'custom')")
        
        # Weitere Migration für Sensordaten
        if db_type == 'mysql':
            try:
                cursor.execute("SHOW COLUMNS FROM sensor_data LIKE 'device_id'")
                if not cursor.fetchone():
                    print("Migration: 'device_id' Spalte zur Tabelle sensor_data hinzugefügt")
                    cursor.execute("ALTER TABLE sensor_data ADD COLUMN device_id VARCHAR(100)")
            except mysql.connector.Error as err:
                print(f"Migrationsfehler: {err}")
        else:
            cursor.execute("PRAGMA table_info(sensor_data)")
            cols = [c[1] for c in cursor.fetchall()]
            if 'device_id' not in cols:
                cursor.execute("ALTER TABLE sensor_data ADD COLUMN device_id VARCHAR(100)")

        conn.commit()
    except Exception as err:
        logger.error(f"Fehler bei der DB-Initialisierung: {err}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def seed_mock_data():
    """
    Erstellt Demo-Daten für die LoraSense Dashboard-Präsentation.
    Generiert fiktive Geräte und historischen Verlauf.
    """
    conn = get_db_connection()
    if not conn: return
    cursor = None
    try:
        cursor = conn.cursor()
        
        # 1. Sicherstellen, dass die Mock-Geräte existieren
        mock_sensors = [
            {"id": "LoraSense-Alpha-01", "name": "Alpha Station (Mock)", "temp": 22, "hum": 45},
            {"id": "LoraSense-Beta-02", "name": "Beta Station (Mock)", "temp": 18, "hum": 60},
            {"id": "LoraSense-Gamma-03", "name": "Gamma Station (Mock)", "temp": 25, "hum": 35},
            {"id": "LoraSense-Delta-04", "name": "Delta Station (Mock)", "temp": 15, "hum": 70}
        ]
        
        # Den ersten verfügbaren Sensortyp (Standard) holen
        cursor.execute("SELECT id FROM sensor_types LIMIT 1")
        res = cursor.fetchone()
        type_id = res[0] if res else 1

        for s in mock_sensors:
            cursor.execute("SELECT id FROM devices WHERE dev_eui = %s", (s['id'],))
            if not cursor.fetchone():
                print(f"🔹 Erstelle Mock-Gerät {s['id']}")
                cursor.execute("""
                    INSERT INTO devices (dev_eui, name, sensor_type_id, status) 
                    VALUES (%s, %s, %s, 'active')
                """, (s['id'], s['name'], type_id))
        
        conn.commit()

        # 2. Historische Daten generieren (falls nicht genügend vorhanden)
        cursor.execute("SELECT count(*) FROM sensor_data WHERE device_id = 'LoraSense-Alpha-01'")
        count = cursor.fetchone()[0]
        
        if count < 10:
            print("🔹 Generiere historische Demo-Daten...")
            now = datetime.now()
            
            for s in mock_sensors:
                for i in range(50): # Daten für ca. 24 Stunden generieren
                    ts = now - timedelta(minutes=i*30)
                    
                    # Zufallsvariationen um den Basiswert
                    temp = round(s["temp"] + random.uniform(-3, 3), 1)
                    hum = round(s["hum"] + random.uniform(-5, 5), 1)
                    press = round(1013 + random.uniform(-10, 10), 1)
                    batt = round(3.6 + random.uniform(-0.4, 0.4), 2)
                    rain = round(max(0, random.uniform(-2, 5)), 1)
                    irr = round(random.uniform(0, 1000), 0)
                    
                    sql = """
                        INSERT INTO sensor_data 
                        (timestamp, raw_payload, type, battery, temperature, t_min, t_max, humidity, pressure, irradiation, irr_max, rain, rain_min_time, device_id)
                        VALUES (%s, 'MOCK', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    values = (
                        ts, 0, batt, temp, temp-1, temp+1, hum, press, irr, irr, rain, 0, s['id']
                    )
                    cursor.execute(normalize_query(sql, conn.db_type), values)
            conn.commit()
            print("✅ Demo-Daten erfolgreich eingespielt.")
            
    except Exception as err:
        print(f"Fehler beim Seeden der Demo-Daten: {err}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def save_sensor_data(raw_payload, decoded, device_id="Unknown", timestamp=None):
    """
    Speichert dekodierte Sensormessdaten in die Tabelle 'sensor_data'.
    
    Args:
        raw_payload (str): Die rohe Base64-Payload.
        decoded (dict): Das Dictionary mit den dekodierten Werten.
        device_id (str): Die Kennung des Sensors (z.B. DevEUI).
        timestamp (datetime, optional): Manueller Zeitstempel (für Backfills).
        
    Returns:
        bool: True bei Erfolg, sonst False.
    """
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = None
    try:
        cursor = conn.cursor()
        db_type = conn.db_type
        
        # SQL-Query vorbereiten (mit oder ohne Zeitstempel)
        if timestamp:
            sql = """
                INSERT INTO sensor_data 
                (timestamp, raw_payload, type, battery, temperature, t_min, t_max, humidity, pressure, irradiation, irr_max, rain, rain_min_time, device_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            values = (
                timestamp, raw_payload, decoded.get("Type"), decoded.get("Battery"),
                decoded.get("Temperature"), decoded.get("T_min"), decoded.get("T_max"),
                decoded.get("Humidity"), decoded.get("Pressure"), decoded.get("Irradiation"),
                decoded.get("Irr_max"), decoded.get("Rain"), decoded.get("Rain_min_time"), device_id
            )
        else:
            sql = """
                INSERT INTO sensor_data 
                (raw_payload, type, battery, temperature, t_min, t_max, humidity, pressure, irradiation, irr_max, rain, rain_min_time, device_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            values = (
                raw_payload, decoded.get("Type"), decoded.get("Battery"),
                decoded.get("Temperature"), decoded.get("T_min"), decoded.get("T_max"),
                decoded.get("Humidity"), decoded.get("Pressure"), decoded.get("Irradiation"),
                decoded.get("Irr_max"), decoded.get("Rain"), decoded.get("Rain_min_time"), device_id
            )
        cursor.execute(normalize_query(sql, db_type), values)
        conn.commit()
        return True
    except Exception as err:
        print(f"Fehler beim Speichern der Sensordaten: {err}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def get_latest_data(limit=100, sensor_id=None):
    """
    Ruft die neuesten Sensordaten ab. Kann auf einen bestimmten Sensor gefiltert werden.
    
    Args:
        limit (int): Maximale Anzahl der Datensätze.
        sensor_id (str, optional): Filter für eine bestimmte DevEUI.
        
    Returns:
        list: Eine Liste von Dictionaries mit Zeitstempel und dekodierten Werten.
    """
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
            # Datetime-Handhabung für SQLite (kommt oft als String zurück)
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
                    "Type": row["type"], "Battery": row["battery"], "Temperature": row["temperature"],
                    "T_min": row["t_min"], "T_max": row["t_max"], "Humidity": row["humidity"],
                    "Pressure": row["pressure"], "Irradiation": row["irradiation"],
                    "Irr_max": row["irr_max"], "Rain": row["rain"], "Rain_min_time": row["rain_min_time"]
                }
            })
        return history
    except Exception as err:
        print(f"Fehler beim Abrufen der Sensordaten: {err}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def get_unique_sensors():
    """
    Listet alle eindeutigen Sensor-IDs auf, die jemals Daten gesendet haben.
    
    Returns:
        list: Liste von IDs (Strings).
    """
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
        print(f"Fehler beim Abrufen der Sensoren: {err}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def get_user_by_username(username):
    """
    Sucht einen Benutzer anhand seines Namens.
    
    Args:
        username (str): Der gesuchte Benutzername.
        
    Returns:
        dict: Benutzerdaten oder None.
    """
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
        print(f"Fehler beim Abrufen des Benutzers: {err}")
        return None
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def get_all_users():
    """
    Gibt eine Liste aller registrierten Benutzer zurück.
    
    Returns:
        list: Liste von Dictionaries (id, username, is_admin).
    """
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
        print(f"Fehler beim Abrufen aller Benutzer: {err}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def update_user_sensors(user_id, sensor_ids):
    """
    Aktualisiert die Liste der erlaubten Sensoren für einen Benutzer (ACL).
    
    Args:
        user_id (int): Die ID des Benutzers.
        sensor_ids (list): Liste von Sensor-IDs (DevEUIs).
        
    Returns:
        bool: True bei Erfolg.
    """
    conn = get_db_connection()
    if not conn:
        return False
    cursor = None
    try:
        cursor = conn.cursor()
        db_type = conn.db_type
        # Vorhandene Mappings löschen
        sql_del = "DELETE FROM user_sensors WHERE user_id = %s"
        cursor.execute(normalize_query(sql_del, db_type), (user_id,))
        
        # Neue Mappings einfügen
        if sensor_ids:
            sql_ins = "INSERT INTO user_sensors (user_id, sensor_id) VALUES (%s, %s)"
            if db_type == 'mysql':
                values = [(user_id, s_id) for s_id in sensor_ids]
                cursor.executemany(sql_ins, values)
            else:
                for s_id in sensor_ids:
                    cursor.execute(normalize_query(sql_ins, db_type), (user_id, s_id))
        
        conn.commit()
        return True
    except Exception as err:
        print(f"Fehler beim Aktualisieren der Sensorrechte: {err}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def get_allowed_sensors(user_id):
    """
    Gibt die Liste der Sensor-IDs zurück, auf die ein Benutzer zugreifen darf.
    Admins dürfen alle Sensoren sehen.
    
    Args:
        user_id (int): Die ID des Benutzers.
        
    Returns:
        list: Liste von IDs.
    """
    conn = get_db_connection()
    if not conn:
        return []
    cursor = None
    try:
        cursor = conn.cursor()
        db_type = conn.db_type
        
        # Admin-Check
        sql_admin_check = "SELECT is_admin FROM users WHERE id = %s"
        cursor.execute(normalize_query(sql_admin_check, db_type), (user_id,))
        user_row = cursor.fetchone()
        
        is_admin = False
        if user_row:
            is_admin = user_row.get('is_admin') if isinstance(user_row, dict) else user_row[0]

        if is_admin:
            # Admins sehen alles (aus Registry und aus Daten-Historie)
            sql_union = """
                SELECT dev_eui FROM devices 
                UNION 
                SELECT DISTINCT device_id FROM sensor_data
            """
            cursor.execute(normalize_query(sql_union, db_type))
            return [row[0] for row in cursor.fetchall() if row[0]]
        
        # Normale Benutzer sehen nur Zugewiesenes
        sql_user_sensors = "SELECT sensor_id FROM user_sensors WHERE user_id = %s"
        cursor.execute(normalize_query(sql_user_sensors, db_type), (user_id,))
        return [row[0] for row in cursor.fetchall()]
    except Exception as err:
        print(f"Fehler beim Abrufen der erlaubten Sensoren: {err}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def create_user(username, password, is_admin=False):
    """
    Erstellt einen neuen Benutzer in der Datenbank.
    
    Args:
        username (str): Gewünschter Name.
        password (str): Klartext-Passwort (wird gehasht).
        is_admin (bool): Administrator-Rechte vergeben?
        
    Returns:
        bool: True bei Erfolg.
    """
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
        print(f"Fehler beim Erstellen des Benutzers: {err}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- Gerätemanagement Funktionen ---

def create_device(dev_eui, name, sensor_type_id, tenant_id=1, join_eui=None, app_key=None, nwk_key=None):
    """
    Registriert ein neues LoRaWAN-Gerät.
    """
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
        print(f"Fehler beim Erstellen des Geräts: {err}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def get_devices(tenant_id=None):
    """
    Listet alle registrierten Geräte auf.
    """
    conn = get_db_connection()
    if not conn: return []
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        db_type = conn.db_type
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
        print(f"Fehler beim Abrufen der Geräte: {err}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def get_device_by_eui(dev_eui):
    """
    Sucht ein Gerät anhand seiner DevEUI.
    """
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
        print(f"Fehler beim Abrufen des Geräts per EUI: {err}")
        return None
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def update_device_status(dev_eui, status):
    """Aktualisiert den Status eines Geräts (z.B. active/inactive)."""
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
        print(f"Fehler beim Status-Update: {err}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def delete_device(dev_eui):
    """
    Löscht ein Gerät und ALLE damit verbundenen Daten (Messwerte, Logs, Rechte).
    """
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        db_type = conn.db_type
        
        # 1-3. Verknüpfte Daten löschen
        exec_q = lambda s, v: cursor.execute(normalize_query(s, db_type), v)
        exec_q("DELETE FROM user_sensors WHERE sensor_id = %s", (dev_eui,))
        exec_q("DELETE FROM sensor_data WHERE device_id = %s", (dev_eui,))
        exec_q("DELETE FROM uplinks WHERE dev_eui = %s", (dev_eui,))
        # 4. Gerät selbst löschen
        exec_q("DELETE FROM devices WHERE dev_eui = %s", (dev_eui,))
        
        conn.commit()
        return True
    except Exception as err:
        print(f"Fehler beim Löschen des Geräts: {err}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def get_sensor_types():
    """Gibt alle verfügbaren Sensortypen/Decoder-Konfigurationen zurück."""
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
        print(f"Fehler beim Abrufen der Sensortypen: {err}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def save_uplink(dev_eui, payload_raw, fcnt=0, port=1, rssi=0, snr=0, device_db_id=None, received_at=None):
    """
    Loggt einen rohen Uplink in der Datenbank. Hilfreich für Debugging und Payload-Analysen.
    """
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
             params = (device_db_id, dev_eui, fcnt, port, payload_raw, rssi, snr, received_at)
        else:
            sql = """
                INSERT INTO uplinks (device_id, dev_eui, fcnt, port, payload_raw, rssi, snr)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            params = (device_db_id, dev_eui, fcnt, port, payload_raw, rssi, snr)
        
        cursor.execute(normalize_query(sql, db_type), params)
        conn.commit()
        return True
    except Exception as err:
        print(f"Fehler beim Speichern des Uplinks: {err}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
