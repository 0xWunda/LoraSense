import requests
import time
import random
import base64
import argparse
import sys
import json
from datetime import datetime

# URL of the Uplink Service (locally)
UPLINK_URL = "http://localhost:5001/uplink"

# Default Mock Devices
MOCK_DEVICES = [
    "LoraSense-Alpha-01",
    "LoraSense-Beta-02",
    "LoraSense-Gamma-03",
    "LoraSense-Delta-04"
]

class BaraniEncoder:
    """
    Helps construct a payload that matches the Barani decoder expectations.
    """
    def __init__(self):
        self.bits = ""

    def add_value(self, value, bit_length, transform_func=None):
        """
        encodes a value into 'bit_length' bits.
        transform_func: lambda v: transformed_v (inverse of decoder logic)
        """
        if transform_func:
            value = transform_func(value)
        
        value = int(round(value))
        
        # Clamp to max value for those bits to avoid overflow
        max_val = (1 << bit_length) - 1
        if value < 0: value = 0 # Simple clamping
        if value > max_val: value = max_val
            
        # Convert to binary string
        bin_str = bin(value)[2:].zfill(bit_length)
        if len(bin_str) > bit_length:
             bin_str = bin_str[-bit_length:] # Should not happen due to clamp, but safety
        
        self.bits += bin_str

    def get_bytes(self):
        # Pad with zeros to make full bytes
        while len(self.bits) % 8 != 0:
            self.bits += "0"
            
        # Convert to bytes
        byte_array = bytearray()
        for i in range(0, len(self.bits), 8):
            byte_chunk = self.bits[i:i+8]
            byte_array.append(int(byte_chunk, 2))
        return byte_array

def generate_random_payload():
    enc = BaraniEncoder()
    
    # 1. Type (2 bits)
    enc.add_value(1, 2) 
    
    # 2. Battery (5 bits) -> decoder: val*0.05 + 3
    # Inverse: (Target - 3) / 0.05
    batt = random.uniform(3.6, 4.2)
    enc.add_value(batt, 5, lambda x: (x - 3) / 0.05)
    
    # 3. Temperature (11 bits) -> decoder: val*0.1 - 100
    # Inverse: (Target + 100) / 0.1
    temp = random.uniform(15.0, 30.0)
    enc.add_value(temp, 11, lambda x: (x + 100) / 0.1)
    
    # 4. T_min offset (6 bits) -> decoder: Temp - val*0.1
    # Actually decoder says: T_min = Temp - bitShift(6)*0.1
    # So valid range is 0-6.3 degrees below current temp
    t_min_offset = random.uniform(0, 5)
    enc.add_value(t_min_offset, 6, lambda x: x / 0.1)
    
    # 5. T_max offset (6 bits) -> decoder: Temp + val*0.1
    t_max_offset = random.uniform(0, 5)
    enc.add_value(t_max_offset, 6, lambda x: x / 0.1)
    
    # 6. Humidity (9 bits) -> decoder: val*0.2
    # Inverse: Target / 0.2
    hum = random.uniform(30, 80)
    enc.add_value(hum, 9, lambda x: x / 0.2)
    
    # 7. Pressure (14 bits) -> decoder: val*5 + 50000
    # Inverse: (Target - 50000) / 5
    press = random.uniform(98000, 103000) # Pa
    enc.add_value(press, 14, lambda x: (x - 50000) / 5)
    
    # 8. Irradiation (10 bits) -> decoder: val*2
    irr = random.uniform(0, 800)
    enc.add_value(irr, 10, lambda x: x / 2)
    
    # 9. Irr_max offset (9 bits) -> decoder: Irr + val*2
    irr_max_offset = random.uniform(0, 100)
    enc.add_value(irr_max_offset, 9, lambda x: x / 2)
    
    # 10. Rain (8 bits) -> decoder: val
    rain = 0 # Mostly no rain
    if random.random() > 0.8:
        rain = random.uniform(0, 10)
    enc.add_value(rain, 8)
    
    # 11. Rain_min_time (8 bits)
    enc.add_value(0, 8)
    
    return enc.get_bytes()

def send_uplink(device_id):
    payload_bytes = generate_random_payload()
    payload_b64 = base64.b64encode(payload_bytes).decode('utf-8')
    
    data = {
        "dev_eui": device_id,
        "data": payload_b64
    }
    
    try:
        print(f"DEBUG: Sending data for device_id: {device_id}")
        # print(f"Sending data for {device_id}...", end=" ")
        resp = requests.post(UPLINK_URL, json=data, timeout=5)
        if resp.status_code not in [200, 201]:
             print(f"Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"\nConnection Error: {e}")
        print("   (Ensure Docker is running: docker-compose up)")

def main():
    parser = argparse.ArgumentParser(description="Simulate LoRaWAN Sensor Uplinks")
    parser.add_argument("--device-id", help="Device EUI to simulate", default=None)
    parser.add_argument("--mocks", action="store_true", help="Simulate all default mock sensors")
    parser.add_argument("--loop", action="store_true", help="Run in a loop")
    parser.add_argument("--interval", type=int, default=10, help="Interval in seconds for loop")
    
    args = parser.parse_args()
    
    devices = []
    if args.device_id:
        devices.append(args.device_id)
        
    if args.mocks:
        devices.extend(MOCK_DEVICES)
        
    if not devices:
        print("⚠️ No devices specified.")
        print("Use --device-id <EUI> to simulate a specific sensor.")
        print("Use --mocks to simulate existing mock sensors (Alpha, Beta, etc).")
        return

    print(f"Starting simulation for {len(devices)} devices: {', '.join(devices)}")
    print(f"Target: {UPLINK_URL}")
    
    if args.loop:
        try:
            while True:
                for dev in devices:
                    send_uplink(dev)
                print(f"Waiting {args.interval}s...")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nSimulation stopped.")
    else:
        for dev in devices:
            send_uplink(dev)

if __name__ == "__main__":
    main()
