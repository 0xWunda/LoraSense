from flask import Flask, render_template, jsonify
from flask_cors import CORS
import os
import json
from datetime import datetime

# Pfade
# Pfade
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
WEBSITE_DIR = os.path.join(BASE_DIR, "website")

# Flask App
app = Flask(__name__, template_folder=WEBSITE_DIR, static_folder=WEBSITE_DIR)
CORS(app)


import sys
# Add parent directory to path to import common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import database

# Configure DB for local testing if not set
if not os.getenv("MYSQL_HOST"):
    os.environ["MYSQL_HOST"] = "127.0.0.1"
    os.environ["MYSQL_USER"] = "lora_user"
    os.environ["MYSQL_PASSWORD"] = "lora_pass"
    os.environ["MYSQL_DATABASE"] = "lorasense_db"
    os.environ["MYSQL_PORT"] = "3307"

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/devices")
def api_devices():
    devices = database.get_devices()
    return jsonify(devices)

@app.route("/api/data")
def api_data_all():
    # Legacy support or aggregate
    history = database.get_latest_data(limit=50)
    return jsonify(history)

@app.route("/api/data/<device_id>")
def api_data_device(device_id):
    history = database.get_latest_data(device_id=device_id, limit=50)
    return jsonify(history)

@app.route("/api/export/csv")
def api_export_csv():
    # Fetch all data (limit to recent 1000 for performance in this demo)
    data = database.get_latest_data(limit=1000)
    
    # Generate CSV
    def generate():
        yield "Timestamp,DeviceID,Temperature,Humidity,Pressure,Battery,Rain\n"
        for row in data:
            d = row['decoded']
            yield f"{row['timestamp']},{row.get('device_id','')},{d.get('Temperature','')},{d.get('Humidity','')},{d.get('Pressure','')},{d.get('Battery','')},{d.get('Rain','')}\n"
    
    from flask import Response
    return Response(generate(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=sensor_data_export.csv"})

@app.route("/api/logs")
def api_logs():
    # Derive logs from sensor data timestamps
    data = database.get_latest_data(limit=50)
    logs = []
    for row in data:
        logs.append({
            "timestamp": row['timestamp'],
            "device": row.get('device_id', 'Unknown'),
            "event": "Uplink packet received successfully",
            "level": "INFO"
        })
    return jsonify(logs)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
