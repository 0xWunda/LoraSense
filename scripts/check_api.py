"""
Skript zum Testen der Erreichbarkeit der internen API-Endpunkte.
Simuliert einen Login und fragt Sensordaten ab.
"""
import requests
import json

def check_sensors():
    url = "http://localhost:8080/api/sensors"
    s = requests.Session()
    # Login first
    s.post("http://localhost:8080/api/login", json={"username": "admin", "password": "admin123"})
    
    resp = s.get(url)
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        print(json.dumps(resp.json(), indent=2))
    else:
        print(resp.text)

if __name__ == "__main__":
    check_sensors()
