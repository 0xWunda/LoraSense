import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.getcwd(), "lorasense.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialisiert die Datenbank mit Tabellen und Standard-Usern."""
    conn = get_db()
    c = conn.cursor()
    
    # User Tabelle
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin BOOLEAN DEFAULT 0
        )
    ''')
    
    # User-Sensor Zuordnung
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_sensors (
            user_id INTEGER,
            sensor_id TEXT,
            PRIMARY KEY (user_id, sensor_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    
    # Mock Data Tabelle (falls wir echte Daten speichern wollen, hier optional)
    c.execute('''
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id TEXT,
            timestamp DATETIME,
            data_json TEXT
        )
    ''')
    
    conn.commit()
    
    # Seed Users if not exist
    # Admin
    admin = c.execute("SELECT * FROM users WHERE username = ?", ("admin",)).fetchone()
    if not admin:
        pw_hash = generate_password_hash("admin123")
        c.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)", 
                  ("admin", pw_hash, True))
        print("Created admin user")

    # Test User
    testuser = c.execute("SELECT * FROM users WHERE username = ?", ("testuser",)).fetchone()
    if not testuser:
        pw_hash = generate_password_hash("test123")
        c.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)", 
                  ("testuser", pw_hash, False))
        print("Created testuser")

    # Additional Test Users
    for i in range(1, 3):
        u_name = f"testuser{i}"
        user = c.execute("SELECT * FROM users WHERE username = ?", (u_name,)).fetchone()
        if not user:
            pw_hash = generate_password_hash(f"test{i}123") # password: test1123, test2123
            c.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)", 
                      (u_name, pw_hash, False))
            print(f"Created {u_name}")
        
    conn.commit()
    conn.close()

def get_user_by_username(username):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if user:
        return dict(user)
    return None

def get_all_users():
    conn = get_db()
    users = conn.execute("SELECT id, username, is_admin FROM users").fetchall()
    conn.close()
    return [dict(u) for u in users]

def get_allowed_sensors(user_id):
    conn = get_db()
    # Check if admin
    user = conn.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
    if user and user['is_admin']:
        # Admin gets all known sensors (mock + real)
        # For now, just return what's in the mapping or hardcoded in app.py logic
        # But let's return all assigned sensors + we can verify strictly in app.py
        rows = conn.execute("SELECT DISTINCT sensor_id FROM user_sensors").fetchall()
        return [r['sensor_id'] for r in rows]
    
    rows = conn.execute("SELECT sensor_id FROM user_sensors WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    return [r['sensor_id'] for r in rows]

def update_user_sensors(user_id, sensor_ids):
    conn = get_db()
    try:
        conn.execute("DELETE FROM user_sensors WHERE user_id = ?", (user_id,))
        for sid in sensor_ids:
            conn.execute("INSERT INTO user_sensors (user_id, sensor_id) VALUES (?, ?)", (user_id, sid))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating sensors: {e}")
        return False
    finally:
        conn.close()

def create_user(username, password, is_admin=False):
    conn = get_db()
    try:
        pw_hash = generate_password_hash(password)
        conn.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)", 
                  (username, pw_hash, is_admin))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False # Username likely exists
    except Exception as e:
        print(f"Error creating user: {e}")
        return False
    finally:
        conn.close()

def get_latest_data(limit=1, sensor_id=None):
    # This is a stub since we rely mostly on mock data in app.py for now,
    # or the actual uplink server would write here.
    # For this task, we just return empty list so app.py falls back to mock.
    return []
