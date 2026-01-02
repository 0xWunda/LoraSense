from flask import Flask, render_template, jsonify
from flask_cors import CORS
import os
import json
from datetime import datetime
import mysql.connector

# Pfade
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Note: Assuming website folder is one level up in the source structure or in the same dir in container.
# Based on list_dir output: App/Service/dashboard_server.py and App/website/index.html
# So relative to dashboard_server.py, website is at ../website
WEBSITE_DIR = os.path.join(os.path.dirname(BASE_DIR), "website")

# Flask App
app = Flask(__name__, template_folder=WEBSITE_DIR, static_folder=WEBSITE_DIR)
CORS(app)

# Database Config
DB_HOST = os.environ.get("DB_HOST", "db")
DB_USER = os.environ.get("DB_USER", "user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
DB_NAME = os.environ.get("DB_NAME", "lorasense")

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

def load_latest_data(limit=20):
    """Lädt die letzten Datensätze aus der Datenbank"""
    history = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT * FROM measurements ORDER BY timestamp DESC LIMIT %s"
        cursor.execute(query, (limit,))
        
        rows = cursor.fetchall()
        
        for row in rows:
            # Reconstruct the "decoded" object to match previous frontend expectations
            decoded = {
                "Type": row["type"],
                "Battery": row["battery"],
                "Temperature": row["temperature"],
                "T_min": row["t_min"],
                "T_max": row["t_max"],
                "Humidity": row["humidity"],
                "Pressure": row["pressure"],
                "Irradiation": row["irradiation"],
                "Irr_max": row["irr_max"],
                "Rain": row["rain"],
                "Rain_min_time": row["rain_min_time"]
            }
            
            history.append({
                "timestamp": row["timestamp"].isoformat(),
                "decoded": decoded
            })
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error loading data: {e}")
        
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
