import os
import sys
sys.path.append(os.getcwd())
from common import database

# Set env for local run
os.environ['MYSQL_HOST'] = 'localhost'

MOCK_IDS = [
    "LoraSense-Alpha-01",
    "LoraSense-Beta-02", 
    "LoraSense-Gamma-03",
    "LoraSense-Delta-04"
]

def cleanup():
    conn = database.get_db_connection()
    if not conn:
        print("❌ Could not connect to DB")
        return
        
    cursor = None
    try:
        cursor = conn.cursor()
        for s_id in MOCK_IDS:
            print(f"🗑️ Deleting data and device for {s_id}...", end=" ")
            
            # Delete from user_sensors
            cursor.execute("DELETE FROM user_sensors WHERE sensor_id = %s", (s_id,))
            
            # Delete from sensor_data
            cursor.execute("DELETE FROM sensor_data WHERE device_id = %s", (s_id,))
            
            # Delete from uplinks
            cursor.execute("DELETE FROM uplinks WHERE dev_eui = %s", (s_id,))
            
            # Delete from devices
            cursor.execute("DELETE FROM devices WHERE dev_eui = %s", (s_id,))
            
            print("DONE")
            
        conn.commit()
        print("✨ Cleanup finished.")
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

if __name__ == "__main__":
    cleanup()
