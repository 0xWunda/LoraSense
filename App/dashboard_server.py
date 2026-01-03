from flask import Flask, render_template, jsonify
from flask_cors import CORS
import os
import json
from datetime import datetime

import random
from datetime import datetime, timedelta

# Pfade
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
WEBSITE_DIR = os.path.join(BASE_DIR, "website")

# Sicherstellen, dass das Datenverzeichnis existiert
os.makedirs(DATA_DIR, exist_ok=True)

# Flask App
app = Flask(__name__, template_folder=WEBSITE_DIR, static_folder=WEBSITE_DIR)
CORS(app)

def generate_mock_data():
    """Generiert hochwertige Test-Daten für mehrere Sensoren."""
    sensors = [
        {"id": "LoraSense-Alpha-01", "temp": 22, "hum": 45},
        {"id": "LoraSense-Beta-02", "temp": 18, "hum": 60},
        {"id": "LoraSense-Gamma-03", "temp": 25, "hum": 35}
    ]
    history = []
    now = datetime.now()
    
    # Letzte 24 Stunden simulieren (alle 30 Minuten ein Punkt)
    for s in sensors:
        for i in range(48):
            ts = now - timedelta(minutes=i*30)
            history.append({
                "sensor_id": s["id"],
                "timestamp": ts.isoformat(),
                "decoded": {
                    "Temperature": round(s["temp"] + random.uniform(-3, 3), 1),
                    "Humidity": round(s["hum"] + random.uniform(-5, 5), 1),
                    "Pressure": round(1013 + random.uniform(-10, 10), 1),
                    "Battery": round(3.6 + random.uniform(-0.4, 0.4), 2),
                    "Rain": round(max(0, random.uniform(-2, 5)), 1),
                    "Irradiation": round(random.uniform(0, 1000), 0)
                }
            })
    return sorted(history, key=lambda x: x["timestamp"])

def load_all_data():
    """Lädt JSON-Dateien oder nutzt Mock-Daten."""
    history = []
    if os.path.exists(DATA_DIR):
        files = sorted(os.listdir(DATA_DIR))
        json_files = [f for f in files if f.endswith(".json")]
        
        for f in json_files:
            path = os.path.join(DATA_DIR, f)
            try:
                with open(path, "r") as file:
                    obj = json.load(file)
                    sensor_id = obj.get("device_id") or obj.get("sensor_id") or "Hardware_Sensor_01"
                    history.append({
                        "sensor_id": sensor_id,
                        "timestamp": obj.get("timestamp", ""),
                        "decoded": obj.get("decoded", {})
                    })
            except:
                continue
    
    # Mock-Daten hinzufügen, wenn keine oder wenig reale Daten vorhanden sind
    mock_data = generate_mock_data()
    if len(history) < 10:
        return mock_data
    
    return history + mock_data

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/sensors")
def get_sensors():
    data = load_all_data()
    sensor_ids = list(set(item["sensor_id"] for item in data))
    
    sensor_list = []
    for s_id in sensor_ids:
        # Letzte Werte für diesen Sensor finden
        sensor_history = [item for item in data if item["sensor_id"] == s_id]
        latest = sorted(sensor_history, key=lambda x: x["timestamp"])[-1] if sensor_history else None
             
        sensor_list.append({
            "id": s_id,
            "last_seen": latest["timestamp"] if latest else "N/A",
            "latest_values": latest["decoded"] if latest else {}
        })
    return jsonify(sensor_list)

@app.route("/api/data/<sensor_id>")
def api_sensor_data(sensor_id):
    data = load_all_data()
    sensor_data = [item for item in data if item["sensor_id"] == sensor_id]
    # Sortieren nach Zeit und die letzten 50 Punkte zurückgeben
    sorted_data = sorted(sensor_data, key=lambda x: x["timestamp"])
    return jsonify(sorted_data[-50:])

if __name__ == "__main__":
    print("🚀 LoraSense Dashboard starting on http://localhost:8080")
    app.run(host="0.0.0.0", port=8080, debug=True)

