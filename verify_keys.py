import requests
import json
import base64
import time

BASE_URL = "http://localhost:8080"
UPLINK_URL = "http://localhost:5000"

# 1. Login
session = requests.Session()
login_payload = {"username": "admin", "password": "admin123"}
print(f"Logging in to {BASE_URL}...")
try:
    res = session.post(f"{BASE_URL}/api/login", json=login_payload)
    print(f"Login Status: {res.status_code}")
    if not res.json().get("success"):
        print("Login failed.")
        exit(1)
except Exception as e:
    print(f"Connection failed: {e}")
    exit(1)

# 2. Get Sensor Types
print("\nFetching Sensor Types...")
res = session.get(f"{BASE_URL}/api/sensor-types")
types = res.json()
if not types:
    print("No sensor types found.")
    exit(1)
type_id = types[0]['id']

# 3. Create Device with Keys
dev_eui = "BB00000000000002" # New device
print(f"\nCreating Device {dev_eui} with Keys...")
create_payload = {
    "dev_eui": dev_eui,
    "name": "Secure Sensor Test",
    "sensor_type_id": type_id,
    "join_eui": "1122334455667788",
    "app_key": "AABBCCDDEEFFAABBCCDDEEFFAABBCCDD",
    "nwk_key": "11223344556677889900112233445566"
}
res = session.post(f"{BASE_URL}/api/devices", json=create_payload)
print(f"Create Status: {res.status_code}, Response: {res.text}")

# 4. Verify Device in List (via Sensors API)
print("\nVerifying Device in List...")
res = session.get(f"{BASE_URL}/api/sensors")
sensors = res.json()
found = any(s['id'] == dev_eui for s in sensors)
print(f"Device found in list: {found}")

# 5. Send Uplink
print("\nSending Uplink...")
payload_bytes = b'\x01\x02\x03\x04'
payload_b64 = base64.b64encode(payload_bytes).decode('utf-8')

uplink_payload = {
    "device_id": dev_eui,
    "data": payload_b64
}

res = requests.post(f"{UPLINK_URL}/uplink", json=uplink_payload)
print(f"Uplink Status: {res.status_code}, Response: {res.text}")

# 6. Check Data
print("\nChecking Data...")
time.sleep(1) 
res = session.get(f"{BASE_URL}/api/data/{dev_eui}")
data = res.json()
if len(data) > 0:
    print(f"Latest Record: {data[0]}")
else:
    print("No data found.")

print("\nVerification Complete.")
