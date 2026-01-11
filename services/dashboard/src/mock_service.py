from datetime import datetime, timedelta
import random

def generate_mock_data():
    """Generiert hochwertige Test-Daten für mehrere Sensoren."""
    sensors = [
        {"id": "LoraSense-Alpha-01", "temp": 22, "hum": 45},
        {"id": "LoraSense-Beta-02", "temp": 18, "hum": 60},
        {"id": "LoraSense-Gamma-03", "temp": 25, "hum": 35},
        {"id": "LoraSense-Delta-04", "temp": 15, "hum": 70}
    ]
    history = []
    now = datetime.now()
    for s in sensors:
        for i in range(50): # More points for history
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
    return history
