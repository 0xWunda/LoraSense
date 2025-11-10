import base64
import math

# ===============================
# Hilfsfunktionen vom JS-Decoder
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

# ===============================
# Decoder-Funktion
# ===============================

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
# Beispiel: Payload dekodieren
# ===============================

payload_b64 = "XyxAArEz8AAAAP8="  # Beispiel aus deinem JSON
payload_bytes = base64.b64decode(payload_b64)

result = Decoder(payload_bytes)
print("Dekodierte Werte:")
for k, v in result.items():
    print(f"{k}: {v}")
