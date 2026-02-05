import requests
import time

BASE_URL = "http://localhost:8080"
session = requests.Session()
login_payload = {"username": "admin", "password": "admin123"}

print(f"Logging in to {BASE_URL}...")
res = session.post(f"{BASE_URL}/api/login", json=login_payload)
if not res.json().get("success"):
    print("Login failed.")
    exit(1)

print("\nFetching Sensors...")
res = session.get(f"{BASE_URL}/api/sensors")
sensors = res.json()
print(f"Found {len(sensors)} sensors.")

# Check for Alpha
alpha = next((s for s in sensors if s['id'] == 'LoraSense-Alpha-01'), None)
if alpha:
    print(f"[OK] Found Alpha: {alpha['name']}")
    print(f"     Latest: {alpha['latest_values']}")
else:
    print("[FAIL] Alpha Mock Sensor not found!")

# Check History
print("\nChecking History for Alpha...")
res = session.get(f"{BASE_URL}/api/data/LoraSense-Alpha-01")
data = res.json()
print(f"Found {len(data)} records for Alpha.")
if len(data) > 0:
    print("[OK] History exists.")
else:
    print("[FAIL] No history found (Seeding might have failed or not triggered).")
