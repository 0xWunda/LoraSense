import sys
import os
from datetime import datetime

# Add common to path
sys.path.append(os.path.join(os.getcwd(), 'common'))
import database

def test_sqlite_fallback():
    print("Starting SQLite Fallback Test...")
    
    # 1. Force SQLite by using an invalid host
    os.environ["MYSQL_HOST"] = "non_existent_host_for_test"
    
    # 2. Test Connection
    print("Step 1: Testing connection fallback...")
    conn = database.get_db_connection()
    if conn and conn.db_type == 'sqlite':
        print("OK: Correctly fell back to SQLite.")
    else:
        print(f"ERROR: Failed to fall back to SQLite. DB type was: {conn.db_type if conn else 'None'}")
        return False

    # 3. Test Init DB
    print("\nStep 2: Testing init_db on SQLite...")
    try:
        database.init_db()
        print("OK: init_db completed on SQLite.")
    except Exception as e:
        print(f"ERROR: init_db failed on SQLite: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 4. Test User Creation
    print("\nStep 3: Testing user creation...")
    success = database.create_user("test_fallback_user", "pass123", is_admin=True)
    if success:
        print("OK: User created in SQLite.")
    else:
        print("ERROR: Failed to create user in SQLite.")
        return False

    # 5. Test Data Persistence
    print("\nStep 4: Testing sensor data saving...")
    payload = "AQIDBA==" # 01020304
    decoded = {"Temperature": 22.5, "Humidity": 50, "Battery": 3.6, "Type": 1}
    success = database.save_sensor_data(payload, decoded, device_id="FallbackDev01")
    if success:
        print("OK: Sensor data saved to SQLite.")
    else:
        print("ERROR: Failed to save sensor data to SQLite.")
        return False

    # 6. Test Data Retrieval
    print("\nStep 5: Testing data retrieval...")
    latest = database.get_latest_data(limit=1, sensor_id="FallbackDev01")
    if latest and latest[0]['sensor_id'] == "FallbackDev01":
        print(f"OK: Retrieved data: {latest[0]}")
    else:
        print(f"ERROR: Retrieval failed or data mismatch: {latest}")
        return False

    # 7. Test User Fetch
    print("\nStep 6: Testing user fetch...")
    user = database.get_user_by_username("test_fallback_user")
    if user and user['username'] == "test_fallback_user":
        print("OK: User fetched correctly.")
    else:
        print(f"ERROR: User fetch failed: {user}")
        return False

    print("\nALL SQLite Fallback tests PASSED!")
    return True

if __name__ == "__main__":
    # Ensure /data exists for local test if not in container
    if not os.path.exists("/data"):
        os.environ["SQLITE_DB_PATH"] = "test_fallback.db"
        database.SQLITE_DB_PATH = "test_fallback.db"
    
    success = test_sqlite_fallback()
    if not success:
        sys.exit(1)
    
    # Cleanup
    if os.path.exists("test_fallback.db"):
        os.remove("test_fallback.db")
    if os.path.exists("test_lorasense.db"):
        os.remove("test_lorasense.db")
