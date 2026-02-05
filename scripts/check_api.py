import requests
import json

def check_sensors():
    url = "http://localhost:8080/api/sensors"
    # Note: need a session/cookie if not admin? 
    # But usually locally it might work if session is handled.
    # Actually, I'll just run it against the container or skip session if I can.
    # If session is required, I'll use a session object.
    
    s = requests.Session()
    # Login first
    s.post("http://localhost:8080/login", data={"username": "admin", "password": "admin123"})
    
    resp = s.get(url)
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        print(json.dumps(resp.json(), indent=2))
    else:
        print(resp.text)

if __name__ == "__main__":
    check_sensors()
