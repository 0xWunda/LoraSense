from flask import Flask, render_template, jsonify
from flask_cors import CORS
import os
import json
from datetime import datetime

# Pfade
BASE_DIR = os.getcwd()
DATA_DIR = os.path.join(BASE_DIR, "data")
WEBSITE_DIR = os.path.join(BASE_DIR, "website")

# Flask App
app = Flask(__name__, template_folder=WEBSITE_DIR, static_folder=WEBSITE_DIR)
CORS(app)

def load_latest_data(limit=20):
    """Lädt die letzten JSON-Dateien aus /data"""
    files = sorted(os.listdir(DATA_DIR))
    json_files = [f for f in files if f.endswith(".json")]
    history = []

    for f in json_files[-limit:]:
        path = os.path.join(DATA_DIR, f)
        try:
            with open(path, "r") as file:
                obj = json.load(file)
                # Zeitstempel und decoded Werte
                history.append({
                    "timestamp": obj.get("timestamp", ""),
                    "decoded": obj.get("decoded", {})
                })
        except:
            continue
    return history

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/data")
def api_data():
    history = load_latest_data()
    return jsonify(history)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
