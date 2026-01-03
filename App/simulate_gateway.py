
import urllib.request
import json
import base64
import time
import sys
import random

def to_bin(value, num_bits):
    """Convert integer to binary string with zero padding."""
    return format(int(value), f'0{num_bits}b')

def generate_random_payload():
    """
    Generates a realistic random payload encoded for the LoRaSense decoder.
    Total bits: 88 bits (11 bytes)
    """
    # 1. Type (2 bits)
    pkt_type = 1  # Standard Sensor Data
    
    # 2. Battery (5 bits): val = bits * 0.05 + 3
    # Range: 3.0V - 4.2V
    battery_v = random.uniform(3.0, 4.2)
    battery_bits = int((battery_v - 3.0) / 0.05)
    battery_bits = max(0, min(31, battery_bits))
    
    # 3. Temperature (11 bits): val = bits * 0.1 - 100
    # Range: -10C to 35C
    temp_c = random.uniform(-10.0, 35.0)
    temp_bits = int((temp_c + 100.0) / 0.1)
    temp_bits = max(0, min(2047, temp_bits))
    
    # 4. T_min (6 bits offset): T_min = Temp - bits * 0.1
    # Offset: 0 to 5 degrees
    t_min_off_c = random.uniform(0, 5.0)
    t_min_bits = int(t_min_off_c / 0.1)
    t_min_bits = max(0, min(63, t_min_bits))

    # 5. T_max (6 bits offset): T_max = Temp + bits * 0.1
    t_max_off_c = random.uniform(0, 5.0)
    t_max_bits = int(t_max_off_c / 0.1)
    t_max_bits = max(0, min(63, t_max_bits))
    
    # 6. Humidity (9 bits): val = bits * 0.2
    # Range: 20% to 90%
    humidity_p = random.uniform(20.0, 90.0)
    humidity_bits = int(humidity_p / 0.2)
    humidity_bits = max(0, min(511, humidity_bits))
    
    # 7. Pressure (14 bits): val = bits * 5 + 50000
    # Range: 980 hPa to 1030 hPa (98000 - 103000 Pa)
    pressure_pa = random.uniform(98000, 103000)
    pressure_bits = int((pressure_pa - 50000) / 5)
    pressure_bits = max(0, min(16383, pressure_bits))
    
    # 8. Irradiation (10 bits): val = bits * 2
    # Range: 0 to 800
    irr_val = random.uniform(0, 800)
    irr_bits = int(irr_val / 2)
    irr_bits = max(0, min(1023, irr_bits))
    
    # 9. Irr_max (9 bits offset): Irr_max = Irr + bits * 2
    irr_max_off = random.uniform(0, 200)
    irr_max_bits = int(irr_max_off / 2)
    irr_max_bits = max(0, min(511, irr_max_bits))
    
    # 10. Rain (8 bits): val = bits
    rain_val = 0 if random.random() > 0.3 else random.uniform(0, 50) # 30% chance of rain
    rain_bits = int(rain_val)
    rain_bits = max(0, min(255, rain_bits))
    
    # 11. Rain_min_time (8 bits)
    rain_time_val = random.randint(0, 255)
    rain_time_bits = rain_time_val
    
    # Concatenate bits
    binary_string = (
        to_bin(pkt_type, 2) +
        to_bin(battery_bits, 5) +
        to_bin(temp_bits, 11) +
        to_bin(t_min_bits, 6) +
        to_bin(t_max_bits, 6) +
        to_bin(humidity_bits, 9) +
        to_bin(pressure_bits, 14) +
        to_bin(irr_bits, 10) +
        to_bin(irr_max_bits, 9) +
        to_bin(rain_bits, 8) +
        to_bin(rain_time_bits, 8)
    )
    
    # Convert binary to bytes
    # Pad to make sure it's a multiple of 8 if needed (though 88 is)
    num_bytes = len(binary_string) // 8
    byte_array = bytearray()
    for i in range(num_bytes):
        byte_chunk = binary_string[i*8 : (i+1)*8]
        byte_array.append(int(byte_chunk, 2))
        
    return base64.b64encode(byte_array).decode('utf-8')

def simulate_uplink(url="http://localhost:5001/uplink", device_id="WeatherStation_1"):
    """
    Sends a test payload to the uplink server.
    """
    payload_b64 = generate_random_payload()
    
    data = {
        "device_id": device_id,
        "data": payload_b64
    }
    
    json_data = json.dumps(data).encode("utf-8")
    
    req = urllib.request.Request(
        url, 
        data=json_data, 
        headers={'Content-Type': 'application/json'}
    )
    
    print(f"Sending POST request to {url}...")
    print(f"Device: {device_id}")
    print(f"Payload (Base64): {payload_b64}")
    
    try:
        with urllib.request.urlopen(req) as response:
            status = response.status
            body = response.read().decode('utf-8')
            print(f"\n✅ Server responded with status {status}")
            print(f"Response body: {body}")
            
            # Print decoded values just to verify they make sense
            try:
                resp_json = json.loads(body)
                decoded = resp_json.get("decoded", {})
                print("\nEncoded Values Check:")
                print(f"  Temp: {decoded.get('Temperature')} °C")
                print(f"  Hum:  {decoded.get('Humidity')} %")
                print(f"  Batt: {decoded.get('Battery')} V")
                print(f"  Pres: {decoded.get('Pressure')} hPa")
            except:
                pass
                
            return True
            
    except urllib.error.URLError as e:
        print(f"\n❌ Failed to connect to server: {e}")
        print("Make sure the uplink server is running (python3 App/uplink_server.py)")
        return False
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
        return False

if __name__ == "__main__":
    device_id = "WeatherStation_1"
    if len(sys.argv) > 1:
        device_id = sys.argv[1]
    simulate_uplink(device_id=device_id)
