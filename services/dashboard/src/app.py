from flask import Flask, render_template, jsonify, Response, request, session, redirect, url_for
import io
import csv
from flask_cors import CORS
import os
import database
import random
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

# Paths inside container
WEBSITE_DIR = os.path.join(os.getcwd(), "website")

app = Flask(__name__, template_folder=WEBSITE_DIR, static_folder=WEBSITE_DIR)
app.secret_key = os.getenv("FLASK_SECRET", "super-secret-dev-key")
CORS(app)

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

@app.route("/")
def home():
    if 'user_id' not in session:
        return render_template("index.html", show_login=True)
    return render_template("index.html", show_login=False)

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    
    print(f"DEBUG: Login attempt for {username}")
    user = database.get_user_by_username(username)
    
    if not user:
        print(f"DEBUG: User {username} not found")
        return jsonify({"success": False, "message": "User not found"}), 401
        
    # Handle default admin with mock hash or plain text fallback
    if user['username'] == 'admin' and password == 'admin123':
        if user['password_hash'] in ['pbkdf2:sha256:260000$mockhash', 'admin123']:
            session['user_id'] = user['id']
            session['username'] = user['username']
            print(f"DEBUG: Login successful for admin (fallback)")
            return jsonify({"success": True})
    
    if check_password_hash(user['password_hash'], password):
        session['user_id'] = user['id']
        session['username'] = user['username']
        print(f"DEBUG: Login successful for {username}")
        return jsonify({"success": True})
        
    print(f"DEBUG: Login failed for {username} - Invalid password")
    return jsonify({"success": False, "message": "Invalid credentials"}), 401

@app.route("/api/logout")
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/api/status")
def status():
    if 'user_id' in session:
        return jsonify({
            "logged_in": True, 
            "username": session.get('username'),
            "is_admin": session.get('username') == 'admin'
        })
    return jsonify({"logged_in": False})

@app.route("/api/sensors")
def get_sensors():
    if 'user_id' not in session:
        return jsonify([]), 401
        
    allowed_ids = database.get_allowed_sensors(session['user_id'])
    
    # Always include mock sensors for admin/testing
    mock_sensor_ids = ["LoraSense-Alpha-01", "LoraSense-Beta-02", "LoraSense-Gamma-03", "LoraSense-Delta-04"]
    for m_id in mock_sensor_ids:
        if m_id not in allowed_ids:
            allowed_ids.append(m_id)
    
    mock_data = generate_mock_data()
    sensor_list = []
    for s_id in allowed_ids:
        latest_data = database.get_latest_data(limit=1, sensor_id=s_id)
        latest = latest_data[0] if latest_data else None
        
        # Fallback auf mock
        if not latest and "LoraSense" in s_id:
            latest = next((item for item in mock_data if item["sensor_id"] == s_id), None)

        sensor_list.append({
            "id": s_id,
            "last_seen": latest["timestamp"] if latest else "N/A",
            "latest_values": latest["decoded"] if latest else {}
        })
    return jsonify(sensor_list)

@app.route("/api/data/<sensor_id>")
def api_sensor_data(sensor_id):
    if 'user_id' not in session:
        return jsonify([]), 401
    
    # Simplified check: admin or if sensor in mock list
    mock_sensor_ids = ["LoraSense-Alpha-01", "LoraSense-Beta-02", "LoraSense-Gamma-03", "LoraSense-Delta-04"]
    allowed_ids = database.get_allowed_sensors(session['user_id'])
    
    if sensor_id not in allowed_ids and sensor_id not in mock_sensor_ids:
        return jsonify([]), 403

    history = database.get_latest_data(limit=100, sensor_id=sensor_id)
    
    if not history and "LoraSense" in sensor_id:
        mock = generate_mock_data()
        history = [item for item in mock if item["sensor_id"] == sensor_id]
        
    return jsonify(history)

@app.route("/api/export")
def export_data():
    if 'user_id' not in session:
        return "Unauthorized", 401
        
    allowed_ids = database.get_allowed_sensors(session['user_id'])
    mock_sensor_ids = ["LoraSense-Alpha-01", "LoraSense-Beta-02", "LoraSense-Gamma-03", "LoraSense-Delta-04"]
    
    history = database.get_latest_data(limit=1000)
    mock_history = generate_mock_data()
    
    # Combine real and mock history
    combined = history + mock_history
    
    # Filter only allowed/mock sensors
    filtered = [item for item in combined if item['sensor_id'] in allowed_ids or item['sensor_id'] in mock_sensor_ids]

    def generate():
        data = io.StringIO()
        writer = csv.writer(data)
        writer.writerow(['Timestamp', 'SensorID', 'Temp_C', 'Humidity_%', 'Pressure_hPa', 'Battery_V', 'Rain_mm', 'Irradiation_W/m2'])
        yield data.getvalue()
        data.seek(0)
        data.truncate(0)
        for item in filtered:
            d = item['decoded']
            writer.writerow([
                item['timestamp'],
                item['sensor_id'],
                d.get('Temperature'),
                d.get('Humidity'),
                d.get('Pressure'),
                d.get('Battery'),
                d.get('Rain'),
                d.get('Irradiation')
            ])
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)
    return Response(generate(), mimetype="text/csv", headers={"Content-disposition": f"attachment; filename=lorasense_export_{datetime.now().strftime('%Y%m%d')}.csv"})

if __name__ == "__main__":
    database.init_db()
    app.run(host="0.0.0.0", port=8080)
