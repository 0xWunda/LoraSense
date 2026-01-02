from flask import Flask, request, jsonify
import os
import json
import base64
from datetime import datetime
import database

app = Flask(__name__)

# Hilfsfunktionen vom Decoder
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
    if pos + bits > len(bindata):
        return 0
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

@app.route("/uplink", methods=["GET", "POST"])
def uplink():
    if request.method == "GET":
        return jsonify({
            "status": "online",
            "message": "Uplink server is active. Use POST to send LoRa data.",
            "endpoint": "/uplink"
        }), 200
    
    try:
        data = request.get_json(force=True)
        payload_b64 = data.get("data")
        if not payload_b64:
            raise ValueError("Feld 'data' fehlt im JSON oder ist leer.")

        payload_bytes = base64.b64decode(payload_b64)
        decoded = Decoder(payload_bytes)

        # Save to MySQL
        success = database.save_sensor_data(payload_b64, decoded)
        
        if success:
            print(f"✅ Data saved to DB: {decoded}")
        else:
            print(f"❌ Failed to save data to DB")

        return jsonify({
            "status": "ok" if success else "error",
            "decoded": decoded
        }), 200 if success else 500

    except Exception as e:
        print(f"❌ Fehler: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == "__main__":
    # Initialize DB (create table if not exists)
    database.init_db()
    app.run(host="0.0.0.0", port=5000)
