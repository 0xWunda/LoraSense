"""
Hauptmodul für das Dashboard-Backend (Flask-App).
Verwaltet API-Endpunkte, Benutzer-Sessions und die Bereitstellung des Frontends.
"""

from flask import Flask, render_template, jsonify, Response, request, session, redirect, url_for
import json
import io
import csv
from datetime import datetime
from flask_cors import CORS
import os
from common import database
from werkzeug.security import generate_password_hash, check_password_hash
from common.logging_config import setup_logging

# Setup Logging für den Dashboard-Service
logger = setup_logging("dashboard")

# Verzeichnisse für statische Dateien (Frontend) definieren
WEBSITE_DIR = os.path.join(os.getcwd(), "static")

# Flask-App Instanz erstellen
app = Flask(__name__, template_folder=WEBSITE_DIR, static_folder=WEBSITE_DIR)

# Secret Key für Session-Management
# Bevorzugt aus Umgebungsvariablen, sonst wird ein zufälliger Schlüssel generiert
app.secret_key = os.getenv("FLASK_SECRET")
if not app.secret_key:
    import secrets
    app.secret_key = secrets.token_hex(32)
    logger.warning("FLASK_SECRET nicht gesetzt. Nutze zufälligen Schlüssel (Sessions gehen bei Neustart verloren).")

# CORS erlauben (hilfreich für lokale Entwicklung)
CORS(app)

@app.route("/")
def home():
    """
    Einstiegspunkt für das Dashboard.
    Prüft die Session und signalisiert dem Frontend, ob der Login-Dialog angezeigt werden soll.
    """
    if 'user_id' not in session:
        return render_template("index.html", show_login=True)
    return render_template("index.html", show_login=False)

@app.route("/display")
def display():
    """
    Optimierte Ansicht für Raspberry Pi Displays.
    Wechselt automatisch zwischen den Sensoren.
    """
    if 'user_id' not in session:
        return redirect(url_for('home'))
    return render_template("display.html")

def init_app_db():
    """Initialisiert die Datenbanktabellen beim Start der App."""
    try:
        with app.app_context():
            database.init_db()
    except Exception as e:
        logger.error(f"Datenbank-Initialisierung fehlgeschlagen: {e}")

# DB beim App-Start initialisieren
init_app_db()

@app.route("/api/login", methods=["POST"])
def login():
    """
    Authentifiziert einen Benutzer.
    Erwartet JSON: {'username': '...', 'password': '...'}
    Speichert Benutzerdaten in der Flask-Session bei Erfolg.
    """
    data = request.json
    username = data.get("username")
    password = data.get("password")
    
    logger.info(f"Login-Versuch für Benutzer: {username}")
    user = database.get_user_by_username(username)
    
    # Nutzer validieren
    if not user:
        logger.warning(f"Login fehlgeschlagen: Benutzer {username} nicht gefunden")
        return jsonify({"success": False, "message": "Benutzer nicht gefunden"}), 401
    
    # Passwort-Hash prüfen
    if user and check_password_hash(user['password_hash'], password):
        try:
            is_admin = user['is_admin']
        except (KeyError, TypeError, IndexError):
            is_admin = False
            
        # Session-Variablen setzen
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['is_admin'] = bool(is_admin)
        logger.info(f"Login erfolgreich: {username}")
        return jsonify({"success": True})
        
    logger.warning(f"Login fehlgeschlagen: Ungültiges Passwort für {username}")
    return jsonify({"success": False, "message": "Ungültige Anmeldedaten"}), 401

@app.route("/api/logout")
def logout():
    """Löscht die aktuelle Benutzer-Session."""
    session.clear()
    return jsonify({"success": True})

@app.route("/api/status")
def status():
    """Gibt den aktuellen Authentifizierungsstatus des Benutzers zurück."""
    if 'user_id' in session:
        return jsonify({
            "logged_in": True, 
            "username": session.get('username'),
            "is_admin": session.get('is_admin', False)
        })
    return jsonify({"logged_in": False})

@app.route("/api/devices", methods=["GET"])
def get_devices_api():
    """Listet alle registrierten Geräte auf (erfordert Login)."""
    if 'user_id' not in session:
        return jsonify([]), 401
    
    # In dieser Version nutzen wir eine globale Geräteliste (Tenant ID 1)
    return jsonify(rows)

@app.route("/api/devices", methods=["POST"])
def create_device_api():
    """
    Registriert ein neues Gerät im System.
    Erfordert Authentifizierung.
    """
    if 'user_id' not in session:
        return jsonify({"error": "Nicht autorisiert"}), 401
        
    data = request.json
    dev_eui = data.get("dev_eui")
    name = data.get("name")
    sensor_type_id = data.get("sensor_type_id")
    join_eui = data.get("join_eui")
    app_key = data.get("app_key")
    nwk_key = data.get("nwk_key")
    
    if not all([dev_eui, name, sensor_type_id]):
        return jsonify({"success": False, "message": "Fehlende Pflichtfelder"}), 400
        
    success = database.create_device(dev_eui, name, sensor_type_id, join_eui=join_eui, app_key=app_key, nwk_key=nwk_key)
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "message": "Gerät konnte nicht erstellt werden"}), 500

@app.route("/api/sensors/<dev_eui>", methods=["DELETE"])
def delete_sensor(dev_eui):
    """
    Löscht ein Gerät und alle zugehörigen Daten.
    Nur für Administratoren erlaubt.
    """
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({"error": "Nicht autorisiert"}), 401
        
    success = database.delete_device(dev_eui)
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "message": "Löschen fehlgeschlagen"}), 500

@app.route("/api/sensor-types", methods=["GET"])
def get_sensor_types_api():
    """Gibt alle verfügbaren Sensortypen/Decoder-Profile zurück."""
    if 'user_id' not in session:
        return jsonify([]), 401
    types = database.get_sensor_types()
    return jsonify(types)

@app.route("/api/sensors")
def get_sensors():
    """
    Gibt eine Liste aller Sensoren zurück, auf die der Benutzer Zugriff hat.
    Beinhaltet den Namen, Zeitstempel des letzten Kontakts und die aktuellsten Messwerte.
    """
    if 'user_id' not in session:
        return jsonify([]), 401
        
    # Erlaubte IDs für diesen Benutzer abrufen
    allowed_ids = database.get_allowed_sensors(session['user_id'])
    
    # Alle registrierten Geräte holen, um Namen und Metadaten zu mappen
    all_devices = database.get_devices(tenant_id=1)
    
    final_list = []
    
    for s_id in allowed_ids:
        # Geräte-Informationen aus der Registry suchen
        device_info = next((d for d in all_devices if d['dev_eui'] == s_id), None)
        name = device_info['name'] if device_info else s_id
        
        # Den absolut letzten Messwert für diesen Sensor aus der Historie holen
        latest_data = database.get_latest_data(limit=1, sensor_id=s_id)
        latest = latest_data[0] if latest_data else None
        
        final_list.append({
            "id": s_id,
            "name": name,
            "last_seen": latest["timestamp"] if latest else "N/A",
            "latest_values": latest["decoded"] if latest else {}
        })

    return jsonify(final_list)

@app.route("/api/data/<sensor_id>")
def api_sensor_data(sensor_id):
    """
    Ruft die historischen Messwerte eines Sensors ab.
    Wird für die Diagramm-Darstellung im Frontend verwendet.
    """
    if 'user_id' not in session:
        return jsonify([]), 401
    
    # Zugriffsberechtigung prüfen
    allowed_ids = database.get_allowed_sensors(session['user_id'])
    if sensor_id not in allowed_ids:
        return jsonify({"error": "Zugriff verweigert"}), 403
        
    # Die letzten 100 Datenpunkte abrufen
    data = database.get_latest_data(limit=100, sensor_id=sensor_id)
    return jsonify(data)

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
    """
    Gibt eine Liste aller Benutzer zurück.
    Nur für Administratoren zugänglich.
    """
    if 'user_id' not in session:
        return jsonify([]), 401
    
    if not session.get('is_admin'):
         return jsonify({"error": "Nicht autorisiert"}), 403
         
    users = database.get_all_users()
    
    # Fallback-Daten, falls die DB leer ist (für UI-Entwicklung)
    if not users:
        users = [
            {"id": 1, "username": "admin", "is_admin": 1},
            {"id": 2, "username": "testuser", "is_admin": 0}
        ]
        
    return jsonify(users)

@app.route("/api/admin/users/<int:user_id>/sensors", methods=["GET"])
def get_user_sensors(user_id):
    """Ruft die einem Benutzer zugewiesenen Sensoren ab (ACL)."""
    if 'user_id' not in session or not session.get('is_admin'):
         return jsonify({"error": "Nicht autorisiert"}), 403

    sensors = database.get_allowed_sensors(user_id)
    return jsonify(sensors)

@app.route("/api/admin/users/<int:user_id>/sensors", methods=["POST"])
def update_user_sensors_api(user_id):
    """Aktualisiert die Liste der erlaubten Sensoren für einen Benutzer."""
    if 'user_id' not in session or not session.get('is_admin'):
         return jsonify({"error": "Nicht autorisiert"}), 403
         
    data = request.json
    sensor_ids = data.get("sensors", [])
    
    success = database.update_user_sensors(user_id, sensor_ids)
    
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "message": "Update fehlgeschlagen"}), 500

@app.route("/api/admin/users/create", methods=["POST"])
def create_user_api():
    """Erstellt einen neuen Benutzer (Admin-Funktion)."""
    if 'user_id' not in session or not session.get('is_admin'):
         return jsonify({"error": "Nicht autorisiert"}), 403
         
    data = request.json
    username = data.get("username")
    password = data.get("password")
    is_admin = data.get("is_admin", False)
    
    if not username or not password:
        return jsonify({"success": False, "message": "Benutzername und Passwort sind erforderlich"}), 400
        
    success = database.create_user(username, password, is_admin)
    
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "message": "Benutzer konnte nicht erstellt werden (existiert evtl. bereits)"}), 500

@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
def delete_user_api(user_id):
    """Löscht einen Benutzer aus dem System."""
    if 'user_id' not in session or not session.get('is_admin'):
         return jsonify({"error": "Nicht autorisiert"}), 401
         
    # Verhindern, dass man sich selbst löscht
    if session['user_id'] == user_id:
        return jsonify({"success": False, "message": "Selbstlöschung nicht erlaubt"}), 400
        
    try:
        success = database.delete_user(user_id)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "message": "Löschen fehlgeschlagen"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"Serverfehler: {str(e)}"}), 500

@app.route("/api/export")
def export_data():
    """
    Exportiert Sensordaten als CSV-Datei.
    Berücksichtigt die Berechtigungen des aktuellen Benutzers.
    """
    if 'user_id' not in session:
        return "Nicht autorisiert", 401
        
    allowed_ids = database.get_allowed_sensors(session['user_id'])
    selected_sensor_ids = request.args.getlist('sensor_ids')
    
    # Letzte 1000 Datensätze für den Export laden
    history = database.get_latest_data(limit=1000)
    
    # Filterung nach Berechtigung und Selektion
    filtered = []
    for item in history:
        sid = item['sensor_id']
        if sid in allowed_ids:
             if not selected_sensor_ids or sid in selected_sensor_ids:
                 filtered.append(item)

    # Dynamischen Dateinamen basierend auf Auswahl generieren
    if selected_sensor_ids:
        if len(selected_sensor_ids) == 1:
            filename = f"lorasense_{selected_sensor_ids[0]}_{datetime.now().strftime('%Y%m%d')}.csv"
        else:
            filename = f"lorasense_{len(selected_sensor_ids)}_sensoren_{datetime.now().strftime('%Y%m%d')}.csv"
    else:
        filename = f"lorasense_export_{datetime.now().strftime('%Y%m%d')}.csv"

    def generate():
        """Generator zum Streamen der CSV-Daten."""
        data = io.StringIO()
        writer = csv.writer(data)
        # Header-Zeile
        writer.writerow(['Zeitstempel', 'Sensor-ID', 'Temperatur_C', 'Feuchtigkeit_%', 'Luftdruck_hPa', 'Batterie_V', 'Regen_mm', 'Einstrahlung_W/m2'])
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
    # Startet den Flask-Entwicklungsserver
    app.run(host="0.0.0.0", port=8080, debug=True)
