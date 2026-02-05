import requests
import json
import base64
import time

BASE_URL = "http://localhost:8080"
UPLINK_URL = "http://localhost:5000"

# 1. Login
session = requests.Session()
login_payload = {"username": "admin", "password": "admin123"} # Using fallback credentials or db defaults
print(f"Logging in to {BASE_URL}...")
try:
    res = session.post(f"{BASE_URL}/api/login", json=login_payload)
    print(f"Login Status: {res.status_code}, Response: {res.text}")
    if not res.json().get("success"):
        print("Login failed.")
        exit(1)
except Exception as e:
    print(f"Connection failed: {e}")
    exit(1)

# 2. Get Sensor Types
print("\nFetching Sensor Types...")
res = session.get(f"{BASE_URL}/api/sensor-types")
print(f"Types: {res.text}")
types = res.json()
if not types:
    print("No sensor types found.")
    exit(1)
type_id = types[0]['id']

# 3. Create Device
dev_eui = "AA00000000000001"
print(f"\nCreating Device {dev_eui}...")
create_payload = {
    "dev_eui": dev_eui,
    "name": "Test Sensor MVP",
    "sensor_type_id": type_id
}
res = session.post(f"{BASE_URL}/api/devices", json=create_payload)
print(f"Create Status: {res.status_code}, Response: {res.text}")

# 4. Verify Device in List (via Sensors API which now returns devices)
print("\nVerifying Device in List...")
res = session.get(f"{BASE_URL}/api/sensors")
sensors = res.json()
found = any(s['id'] == dev_eui for s in sensors)
print(f"Device found in list: {found}")

# 5. Send Uplink
print("\nSending Uplink...")
# Payload: 00 (Type) + ... (some random bytes to fake valid decoder input if simple)
# Decoder: 
# Type = bitShift(2) -> 00
# Battery = bitShift(5)*0.05 + 3 -> 00000 -> 3V
# etc.
# data2bits converts bytes to bits. 
# Let's send 8 bytes of zeros, should decode safely.
payload_bytes = b'\x00\x00\x00\x00\x00\x00\x00\x00'
payload_b64 = base64.b64encode(payload_bytes).decode('utf-8')

uplink_payload = {
    "device_id": dev_eui,
    "data": payload_b64
}

try:
    res = requests.post(f"{UPLINK_URL}/uplink", json=uplink_payload)
    print(f"Uplink Status: {res.status_code}, Response: {res.text}")
except Exception as e:
    print(f"Uplink Connection failed: {e}")

# 6. Check Data in Dashboard
print("\nChecking Data...")
time.sleep(1) # Wait for db write
res = session.get(f"{BASE_URL}/api/data/{dev_eui}")
data = res.json()
print(f"Data records: {len(data)}")
if len(data) > 0:
    print(f"Latest Record: {data[0]}")
else:
    print("No data found.")

print("\nMVP Verification Complete.")
