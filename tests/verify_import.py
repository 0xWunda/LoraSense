
from common import database
import os

# Set env for local run
os.environ['MYSQL_HOST'] = 'localhost'

database.init_db()

print("Checking for Imported Device...")
device = database.get_device_by_eui("Barani_Import_Device")
if device:
    print(f"✅ Device Found: {device['name']}")
    
    print("Checking Data...")
    history = database.get_latest_data(limit=5, sensor_id="Barani_Import_Device")
    if history:
        print(f"✅ Data Found: {len(history)} recent records")
        print("Sample:", history[0])
    else:
        print("❌ No data found yet.")
else:
    print("❌ Device not found.")
