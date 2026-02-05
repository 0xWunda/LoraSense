from flask import Flask, request, jsonify
import os
import json
import base64
from datetime import datetime
import database

app = Flask(__name__)

from common.decoder import decode_payload

# Decoder logic moved to common/decoder.py


@app.route("/uplink", methods=["GET", "POST"])
def uplink():
    """
    Main endpoint for receiving LoRaWAN uplink messages.
    POST: Processes base64 payloads, decodes them, and saves to database.
    GET: Returns server status.
    """
    if request.method == "GET":
        return jsonify({
            "status": "online",
            "message": "Uplink server is active. Use POST to send LoRa data.",
            "endpoint": "/uplink"
        }), 200
    
    try:
        data = request.get_json(force=True)
        print(f"DEBUG: Received JSON: {json.dumps(data)}")
        payload_b64 = data.get("data")
        # Support multiple field names, but prioritize dev_eui for consistency
        device_id = data.get("dev_eui") or data.get("device_id") or data.get("sensor_id") or "Hardware_Sensor_01"
        
        print(f"DEBUG: Final device_id used: {device_id}")
        
        if not payload_b64:
            raise ValueError("Feld 'data' fehlt im JSON oder ist leer.")

        # 1. Lookup Device
        device = database.get_device_by_eui(device_id)
        
        # 2. Decode using the correct sensor type logic
        payload_bytes = base64.b64decode(payload_b64)
        config_str = device.get('decoder_config', 'v1') if device else 'v1'
        decoded = decode_payload(payload_bytes, config_str=config_str)
        
        print(f"DEBUG: Decoded using config '{config_str}': {decoded}")

        # 3. Save Raw Uplink
        database.save_uplink(
            dev_eui=device_id,
            payload_raw=payload_b64,
            device_db_id=device['id'] if device else None
        )

        # 4. Save Measurements (only if valid device or lenient mode?)
        # For now, save even if unknown device (legacy behavior) but link to device_id if known
        success = database.save_sensor_data(payload_b64, decoded, device_id)
        
        if success:
            print(f"✅ Data saved to DB: {decoded}")
        else:
            print(f"❌ Failed to save data to DB")

        return jsonify({
            "status": "ok" if success else "error",
            "decoded": decoded,
            "device_known": bool(device)
        }), 200 if success else 500

    except Exception as e:
        print(f"❌ Fehler: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == "__main__":
    # Initialize DB (create table if not exists)
    database.init_db()
    app.run(host="0.0.0.0", port=5000)
