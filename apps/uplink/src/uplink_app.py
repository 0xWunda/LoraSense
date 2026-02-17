"""
Uplink-Service für das LoraSense-System.
Dieser Webservice empfängt Daten-Payloads von LoRaWAN-Netzwerkservern (z.B. ChirpStack).
Die Daten werden dekodiert, validiert und in der Datenbank gespeichert.
"""

from flask import Flask, request, jsonify
import os
import json
import base64
from datetime import datetime
from common import database
from common.logging_config import setup_logging
from common.decoder import decode_payload

# Setup Logging für den Uplink-Service
logger = setup_logging("uplink")

app = Flask(__name__)

@app.route("/uplink", methods=["GET", "POST"])
def uplink():
    """
    Zentraler Endpunkt für LoRaWAN-Uplink-Nachrichten.
    
    POST: Verarbeitet Base64-Payloads, dekodiert sie und speichert sie in der DB.
    GET: Gibt den Status des Uplink-Servers zurück.
    
    Returns:
        JSON-Antwort mit Status und (bei POST) den dekodierten Daten.
    """
    if request.method == "GET":
        return jsonify({
            "status": "online",
            "message": "Uplink-Server ist aktiv. Nutzen Sie POST für LoRa-Daten.",
            "endpoint": "/uplink"
        }), 200
    
    try:
        # Rohdaten vom Netzwerkserver abrufen
        data = request.get_json(force=True)
        logger.debug(f"JSON empfangen: {json.dumps(data)}")
        
        payload_b64 = data.get("data")
        # Identifikation des Sensors (DevEUI)
        device_id = data.get("dev_eui") or data.get("device_id") or data.get("sensor_id") or "Hardware_Sensor_01"
        
        logger.info(f"Verarbeite Uplink für Gerät: {device_id}")
        
        if not payload_b64:
            raise ValueError("Feld 'data' fehlt im JSON oder ist leer.")

        # 1. Gerät in der Datenbank suchen (um den richtigen Decoder zu finden)
        device = database.get_device_by_eui(device_id)
        
        # 2. Payload dekodieren
        payload_bytes = base64.b64decode(payload_b64)
        config_str = device.get('decoder_config', 'v1') if device else 'v1'
        decoded = decode_payload(payload_bytes, config_str=config_str)
        
        logger.debug(f"Dekodiert mit Profil '{config_str}': {decoded}")

        # 3. Rohen Uplink loggen (für Debugging & Analyse)
        database.save_uplink(
            dev_eui=device_id,
            payload_raw=payload_b64,
            device_db_id=device['id'] if device else None
        )

        # 4. Dekodierte Messwerte in der sensor_data Tabelle speichern
        success = database.save_sensor_data(payload_b64, decoded, device_id)
        
        if success:
            logger.info(f"Daten erfolgreich in DB gespeichert für {device_id}: {decoded}")
        else:
            logger.error(f"Fehler beim Speichern der Daten in DB für {device_id}")

        return jsonify({
            "status": "ok" if success else "error",
            "decoded": decoded,
            "device_known": bool(device)
        }), 200 if success else 500

    except Exception as e:
        logger.error(f"Uplink-Fehler: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == "__main__":
    # Datenbank sicherheitshalber initialisieren
    database.init_db()
    # Server auf Port 5000 starten
    app.run(host="0.0.0.0", port=5000)
