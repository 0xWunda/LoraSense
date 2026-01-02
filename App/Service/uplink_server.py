from flask import Flask, request, jsonify
import os
import json
import base64
from datetime import datetime
import mysql.connector

# ===============================
# Flask-App
# ===============================

app = Flask(__name__)

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

        # 2) verschlüsseltes Feld "data" aus dem JSON holen
        payload_b64 = data.get("data")
        if not payload_b64:
            raise ValueError("Feld 'data' fehlt im JSON oder ist leer.")

        # Base64 → Bytes
        payload_bytes = base64.b64decode(payload_b64)

        # Dekodieren mit eurem Decoder
        d = Decoder(payload_bytes)

        # In Datenbank speichern
        conn = get_db_connection()
        cursor = conn.cursor()
        
        sql = """
            INSERT INTO measurements (
                timestamp, type, battery, temperature, t_min, t_max, 
                humidity, pressure, irradiation, irr_max, rain, 
                rain_min_time, raw_data
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        val = (
            datetime.now(),
            d["Type"], d["Battery"], d["Temperature"], d["T_min"], d["T_max"],
            d["Humidity"], d["Pressure"], d["Irradiation"], d["Irr_max"], d["Rain"],
            d["Rain_min_time"], payload_b64
        )
        
        cursor.execute(sql, val)
        conn.commit()
        
        cursor.close()
        conn.close()

        print(f"✅ Daten in DB gespeichert: {d}")

        return jsonify({
            "status": "ok",
            "message": "Data saved to database",
            "decoded": d
        }), 200

    except Exception as e:
        print(f"❌ Fehler: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

# ===============================
# Main
# ===============================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
