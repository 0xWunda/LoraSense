from flask import Flask, request, jsonify
import os
import json
import base64
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

from datetime import datetime

# ===============================
# Flask-App
# ===============================

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE_DIR, "json")   # rohe Serverdaten
DECODED_DIR = os.path.join(BASE_DIR, "data")  # entschlüsselte Daten

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(DECODED_DIR, exist_ok=True)

# ===============================
# Hilfsfunktionen vom Decoder
# ===============================

pos = 0
bindata = ""

def pad(num):
    s = "00000000" + str(num)
    return s[-8:]

def dec2bin(num):
    return pad(bin(num)[2:])

def bin2dec(num):
    return int(num, 2)

def data2bits(data):
    binary = ""
    for b in data:
        binary += dec2bin(b)
    return binary

def bitShift(bits):
    global pos, bindata
    num = bin2dec(bindata[pos:pos+bits])
    pos += bits
    return num

def precisionRound(number, precision):
    factor = 10 ** precision
    return round(number * factor) / factor

def Decoder(payload_bytes):
    global pos, bindata
    pos = 0
    bindata = data2bits(payload_bytes)

    Type = bitShift(2)
    Battery = precisionRound(bitShift(5)*0.05 + 3, 2)
    Temperature = precisionRound(bitShift(11)*0.1 - 100, 1)
    T_min = precisionRound(Temperature - bitShift(6)*0.1, 1)
    T_max = precisionRound(Temperature + bitShift(6)*0.1, 1)
    Humidity = precisionRound(bitShift(9)*0.2, 1)
    Pressure = bitShift(14)*5 + 50000
    Irradiation = bitShift(10)*2
    Irr_max = Irradiation + bitShift(9)*2
    Rain = precisionRound(bitShift(8), 1)
    Rain_min_time = precisionRound(bitShift(8), 1)

    decoded = {
        "Type": Type,
        "Battery": Battery,
        "Temperature": Temperature,
        "T_min": T_min,
        "T_max": T_max,
        "Humidity": Humidity,
        "Pressure": Pressure / 100,  # in hPa
        "Irradiation": Irradiation,
        "Irr_max": Irr_max,
        "Rain": Rain,
        "Rain_min_time": Rain_min_time
    }

    return decoded

# ===============================
# Uplink-Endpoint
# ===============================

@app.route("/uplink", methods=["POST"])
def uplink():
    try:
        # rohen JSON-Body vom Server holen
        data = request.get_json(force=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        # 1) rohe Daten in /home/wunder/json speichern
        raw_filename = os.path.join(RAW_DIR, f"uplink_{timestamp}.json")
        with open(raw_filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        # 2) verschlüsseltes Feld "data" aus dem JSON holen
        payload_b64 = data.get("data")
        device_id = data.get("device_id", "unknown_device")

        if not payload_b64:
            raise ValueError("Feld 'data' fehlt im JSON oder ist leer.")

        # Base64 → Bytes
        payload_bytes = base64.b64decode(payload_b64)

        # Dekodieren mit eurem Decoder
        decoded = Decoder(payload_bytes)

        # 3) entschlüsselte Daten in /home/wunder/data speichern
        decoded_obj = {
            "timestamp": datetime.now().isoformat(),
            "device_id": device_id,
            "raw_data": payload_b64,
            "decoded": decoded
        }

        decoded_filename = os.path.join(DECODED_DIR, f"data_{timestamp}.json")
        with open(decoded_filename, "w", encoding="utf-8") as f:
            json.dump(decoded_obj, f, indent=4, ensure_ascii=False)

        print(f"✅ Rohe Daten gespeichert:     {raw_filename}")
        print(f"✅ Entschlüsselte Daten nach:  {decoded_filename}")

        # 4) Save to Database
        if database.save_sensor_data(device_id, payload_b64, decoded):
            print(f"✅ Data saved to Database (Device: {device_id})")
        else:
            print("❌ Failed to save data to Database")

        return jsonify({
            "status": "ok",
            "device_id": device_id,
            "raw_file": raw_filename,
            "decoded_file": decoded_filename,
            "decoded": decoded
        }), 200

    except Exception as e:
        print(f"❌ Fehler: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

# ===============================
# Main
# ===============================

if __name__ == "__main__":
    print("Initializing Database...")
    database.init_db()

    app.run(host="0.0.0.0", port=5001)
