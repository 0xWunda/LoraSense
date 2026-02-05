from flask import Flask, render_template, jsonify, Response, request, session, redirect, url_for
import json
import io
import csv
from datetime import datetime
from flask_cors import CORS
import os
import database
from werkzeug.security import generate_password_hash, check_password_hash

# Paths inside container
WEBSITE_DIR = os.path.join(os.getcwd(), "website")

app = Flask(__name__, template_folder=WEBSITE_DIR, static_folder=WEBSITE_DIR)
app.secret_key = os.getenv("FLASK_SECRET")
if not app.secret_key:
    # Generate a random key for this session (invalidates sessions on restart, but secure)
    import secrets
    app.secret_key = secrets.token_hex(32)
    print("WARNING: FLASK_SECRET not set. Using generated random key.")
CORS(app)

@app.route("/")
def home():
    """Renders the main dashboard page. Shows login modal if not authenticated."""
    if 'user_id' not in session:
        return render_template("index.html", show_login=True)
    return render_template("index.html", show_login=False)

# Initialize DB immediately to ensure tables exist
def init_app_db():
    try:
        with app.app_context():
            database.init_db()
    except Exception as e:
        print(f"Warning: DB Init failed: {e}")

init_app_db()

@app.route("/api/login", methods=["POST"])
def login():
    """
    Authenticates a user.
    Expects JSON: {'username': '...', 'password': '...'}
    """
    data = request.json
    username = data.get("username")
    password = data.get("password")
    
    print(f"DEBUG: Login attempt for {username}")
    user = database.get_user_by_username(username)

    # Emergency Fallback REMOVED

    
    if not user:
        print(f"DEBUG: User {username} not found")
        return jsonify({"success": False, "message": "User not found"}), 401
    
    if check_password_hash(user['password_hash'], password):
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['is_admin'] = bool(user.get('is_admin', False))
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
            "is_admin": session.get('is_admin', False)
        })
    return jsonify({"logged_in": False})

@app.route("/api/devices", methods=["GET"])
def get_devices_api():
    if 'user_id' not in session:
        return jsonify([]), 401
    
    # Validation: user access?
    # For now, let's assume all users can see devices, or tenant logic
    # In database.py we have tenant_id. Let's assume single tenant for now or user-based.
    # But wait, get_devices takes tenant_id.
    # Let's return all devices for admin, and maybe filter for others?
    
    rows = database.get_devices(tenant_id=1) # Default tenant
    return jsonify(rows)

@app.route("/api/devices", methods=["POST"])
def create_device_api():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json
    dev_eui = data.get("dev_eui")
    name = data.get("name")
    sensor_type_id = data.get("sensor_type_id")
    join_eui = data.get("join_eui")
    app_key = data.get("app_key")
    nwk_key = data.get("nwk_key")
    
    if not all([dev_eui, name, sensor_type_id]):
        return jsonify({"success": False, "message": "Missing fields"}), 400
        
    success = database.create_device(dev_eui, name, sensor_type_id, join_eui=join_eui, app_key=app_key, nwk_key=nwk_key)
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "message": "Failed to create device"}), 500

@app.route("/api/sensors/<dev_eui>", methods=["DELETE"])
def delete_sensor(dev_eui):
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 401
        
    success = database.delete_device(dev_eui)
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "message": "Failed to delete device"}), 500

@app.route("/api/sensor-types", methods=["GET"])
def get_sensor_types_api():
    if 'user_id' not in session:
        return jsonify([]), 401
    types = database.get_sensor_types()
    return jsonify(types)

@app.route("/api/sensors")
def get_sensors():
    """
    Returns a list of sensors the current user is allowed to see,
    including their name, last seen timestamp, and latest measured values.
    """
    if 'user_id' not in session:
        return jsonify([]), 401
        
    allowed_ids = database.get_allowed_sensors(session['user_id'])
    
    # NEW: Also fetch real devices from DB (which now includes seeded mock devices)
    # If admin, we mostly rely on allowed_ids which should include everything if we implemented get_allowed_sensors for admin correctly
    # database.get_allowed_sensors(admin) returns ALL devices in sensor_data.
    
    # Also fetch from DEVICES table to ensure even those without data are shown
    all_devices = database.get_devices(tenant_id=1)
    
    # Merge list
    final_list = []
    
    # 1. Map existing allowed_ids
    import sys
    print(f"DEBUG: allowed_ids: {allowed_ids}", file=sys.stderr, flush=True)
    for s_id in allowed_ids:
        device_info = next((d for d in all_devices if d['dev_eui'] == s_id), None)
        name = device_info['name'] if device_info else s_id
        
        latest_data = database.get_latest_data(limit=1, sensor_id=s_id)
        print(f"DEBUG: s_id='{s_id}', latest_data_len={len(latest_data)}", file=sys.stderr, flush=True)
        latest = latest_data[0] if latest_data else None
        if latest:
            print(f"DEBUG: latest: {json.dumps(latest)}", file=sys.stderr, flush=True)
        
        final_list.append({
            "id": s_id,
            "name": name,
            "last_seen": latest["timestamp"] if latest else "N/A",
            "latest_values": latest["decoded"] if latest else {}
        })

    print(f"DEBUG: returning sensors list of length {len(final_list)}", file=sys.stderr, flush=True)
    if len(final_list) > 0:
        print(f"DEBUG: first sensor data: {json.dumps(final_list[0])}", file=sys.stderr, flush=True)
    return jsonify(final_list)

@app.route("/api/data/<sensor_id>")
def api_sensor_data(sensor_id):
    if 'user_id' not in session:
        return jsonify([]), 401
    
    allowed_ids = database.get_allowed_sensors(session['user_id'])
    is_admin = session.get('is_admin', False)

    # Check access
    has_access = False
    if sensor_id in allowed_ids:
        has_access = True
    elif is_admin:
        # Admin can access all sensors by default if they exist in DB
        # Note: database.get_allowed_sensors(admin) already returns all sensors with data
        has_access = True
        
    if not has_access:
        return jsonify([]), 403

    history = database.get_latest_data(limit=100, sensor_id=sensor_id)
    return jsonify(history)

@app.route("/api/admin/users", methods=["GET"])
def get_all_users():
    if 'user_id' not in session:
        return jsonify([]), 401
    
    # Check if admin (trust session)
    if not session.get('is_admin'):
         print(f"DEBUG: get_all_users unauthorized. User: {session.get('username')}, IsAdmin: {session.get('is_admin')}")
         return jsonify({"error": "Unauthorized"}), 403
         
    users = database.get_all_users()
    print(f"DEBUG: get_all_users returning {len(users)} users")
    
    # Fallback if DB is empty or fails (ensure admin page always shows something)
    if not users:
        print("DEBUG: User list empty, using fallback users")
        users = [
            {"id": 1, "username": "admin", "is_admin": 1},
            {"id": 2, "username": "testuser", "is_admin": 0},
            {"id": 3, "username": "testuser1", "is_admin": 0},
            {"id": 4, "username": "testuser2", "is_admin": 0}
        ]
        
    return jsonify(users)

@app.route("/api/admin/users/<int:user_id>/sensors", methods=["GET"])
def get_user_sensors(user_id):
    if 'user_id' not in session:
        return jsonify([]), 401

    # Check if admin (trust session)
    if not session.get('is_admin'):
         return jsonify({"error": "Unauthorized"}), 403

    sensors = database.get_allowed_sensors(user_id)
    return jsonify(sensors)

@app.route("/api/admin/users/<int:user_id>/sensors", methods=["POST"])
def update_user_sensors(user_id):
    if 'user_id' not in session:
        return jsonify([]), 401

    # Check if admin (trust session)
    if not session.get('is_admin'):
         return jsonify({"error": "Unauthorized"}), 403
         
    data = request.json
    sensor_ids = data.get("sensors", [])
    
    print(f"DEBUG: update_user_sensors request for user_id={user_id}. Sensors: {sensor_ids}")
    
    success = database.update_user_sensors(user_id, sensor_ids)
    print(f"DEBUG: update_user_sensors result: {success}")
    
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "message": "Update failed"}), 500

@app.route("/api/admin/users/create", methods=["POST"])
def create_user():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    # Check if admin (trust session)
    if not session.get('is_admin'):
         return jsonify({"error": "Unauthorized"}), 403
         
    data = request.json
    username = data.get("username")
    password = data.get("password")
    is_admin = data.get("is_admin", False)
    
    if not username or not password:
        return jsonify({"success": False, "message": "Missing username or password"}), 400
        
    success = database.create_user(username, password, is_admin)
    
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "message": "Creation failed (username might exist)"}), 500

@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    if not session.get('is_admin'):
         return jsonify({"error": "Unauthorized"}), 403
         
    # Prevent deleting yourself
    if session['user_id'] == user_id:
        return jsonify({"success": False, "message": "Cannot delete yourself"}), 400
        
    try:
        success = database.delete_user(user_id)
        
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "message": "Deletion failed"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"Server Error: {str(e)}"}), 500

@app.route("/api/export")
def export_data():
    if 'user_id' not in session:
        return "Unauthorized", 401
        
    allowed_ids = database.get_allowed_sensors(session['user_id'])
    selected_sensor_ids = request.args.getlist('sensor_ids')
    
    history = database.get_latest_data(limit=1000)
    
    # Filter only allowed sensors
    filtered = []
    for item in history:
        sid = item['sensor_id']
        # Check if sensor is allowed
        if sid in allowed_ids:
             # If selection exists, check against it
             if selected_sensor_ids:
                 if sid in selected_sensor_ids:
                     filtered.append(item)
             else:
                 filtered.append(item)

    # Generate filename based on selection
    if selected_sensor_ids:
        if len(selected_sensor_ids) == 1:
            # Single sensor - use sensor name in filename
            filename = f"lorasense_{selected_sensor_ids[0]}_{datetime.now().strftime('%Y%m%d')}.csv"
        else:
            # Multiple sensors - use count in filename
            filename = f"lorasense_{len(selected_sensor_ids)}_stations_{datetime.now().strftime('%Y%m%d')}.csv"
    else:
        # All sensors
        filename = f"lorasense_export_{datetime.now().strftime('%Y%m%d')}.csv"

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
    return Response(generate(), mimetype="text/csv", headers={"Content-disposition": f"attachment; filename={filename}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
