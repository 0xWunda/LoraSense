import requests
import os
import time
import random
import base64
import argparse
import sys
import json
from datetime import datetime, timedelta

try:
    import openpyxl
except ImportError:
    openpyxl = None


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
    """Helps construct a payload that matches the Barani decoder expectations."""
    def __init__(self):
        self.bits = ""

    def add_value(self, value, bit_length, transform_func=None):
        if transform_func:
            value = transform_func(value)
        
        value = int(round(value))
        max_val = (1 << bit_length) - 1
        if value < 0: value = 0
        if value > max_val: value = max_val
            
        bin_str = bin(value)[2:].zfill(bit_length)
        if len(bin_str) > bit_length:
             bin_str = bin_str[-bit_length:]
        self.bits += bin_str

    def get_bytes(self):
        while len(self.bits) % 8 != 0:
            self.bits += "0"
        byte_array = bytearray()
        for i in range(0, len(self.bits), 8):
            byte_chunk = self.bits[i:i+8]
            byte_array.append(int(byte_chunk, 2))
        return byte_array

class SensorState:
    def __init__(self, device_id):
        self.device_id = device_id
        # Start mit halbwegs logischen Durchschnittswerten
        self.temp = random.uniform(15.0, 25.0)
        self.batt = random.uniform(3.8, 4.2)
        self.hum = random.uniform(40.0, 60.0)
        self.press = random.uniform(101000, 102000)
        self.irr = random.uniform(0, 800)
        
        # Basis-Tendenz (Tag/Nacht Zyklus Andeutung für Bewölkung etc.)
        self.temp_trend = random.choice([0.1, -0.1, 0.2, -0.2])

    def drift(self, minutes_passed=10.0):
        """Simuliert eine realistische Drift der Sensorwerte für die verstrichene Zeit."""
        hours = minutes_passed / 60.0
        
        # Temperatur: Langsamer Random Walk mit Tendenz
        self.temp += random.uniform(-0.5, 0.5) * hours + (self.temp_trend * hours)
        if self.temp > 35.0: self.temp_trend = -abs(self.temp_trend)
        if self.temp < -10.0: self.temp_trend = abs(self.temp_trend)
        self.temp = max(-20.0, min(50.0, self.temp))
        
        # Batterie: Entlädt sich gaaaaanz langsam
        self.batt -= random.uniform(0.0001, 0.0005) * hours
        self.batt = max(3.0, self.batt)
        
        # Luftfeuchtigkeit
        self.hum += random.uniform(-2.0, 2.0) * (minutes_passed / 10.0)
        self.hum = max(20.0, min(100.0, self.hum))
        
        # Luftdruck
        self.press += random.uniform(-100, 100) * hours
        self.press = max(95000, min(105000, self.press))
        
        # Einstrahlung kann schnell schwanken (Wolken)
        if random.random() > 0.8:
            self.irr = 0 # Plötzlich schattig/Nacht
        else:
            self.irr += random.uniform(-100, 100) * (minutes_passed / 10.0)
        self.irr = max(0, min(1200, self.irr))

    def generate_payload(self):
        enc = BaraniEncoder()
        
        enc.add_value(1, 2) # Type
        enc.add_value(self.batt, 5, lambda x: (x - 3) / 0.05)
        enc.add_value(self.temp, 11, lambda x: (x + 100) / 0.1)
        
        t_min_offset = random.uniform(0, 1.5)
        enc.add_value(t_min_offset, 6, lambda x: x / 0.1)
        
        t_max_offset = random.uniform(0, 1.5)
        enc.add_value(t_max_offset, 6, lambda x: x / 0.1)
        
        enc.add_value(self.hum, 9, lambda x: x / 0.2)
        enc.add_value(self.press, 14, lambda x: (x - 50000) / 5)
        enc.add_value(self.irr, 10, lambda x: x / 2)
        
        irr_max_offset = random.uniform(0, 50)
        enc.add_value(irr_max_offset, 9, lambda x: x / 2)
        
        rain = 0
        if random.random() > 0.95:
            rain = random.uniform(0, 5)
        enc.add_value(rain, 8)
        
        enc.add_value(0, 8) # rain_min_time
        
        return enc.get_bytes()

def process_excel(file_path, device_id):
    """Reads hex payloads and timestamps from an Excel file and sends them to the uplink."""
    if not openpyxl:
        print("❌ Error: 'openpyxl' is not installed. Run 'pip install openpyxl' to use this feature.")
        return

    if not os.path.exists(file_path):
        print(f"❌ Error: File not found: {file_path}")
        return

    print(f"Reading data from {file_path} for device {device_id}...")
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        sheet = wb.active
        
        count = 0
        # Assuming header Row 1: ['Timestamp(ISO)', 'Payload']
        rows = sheet.iter_rows(min_row=2, values_only=True)
        
        for row in rows:
            if not row or len(row) < 2:
                continue
                
            ts_val, payload_hex = row[0], row[1]
            if not ts_val or not payload_hex:
                continue

            try:
                # Handle timestamp
                if isinstance(ts_val, str):
                    ts_str = ts_val.replace("Z", "+00:00")
                    timestamp = datetime.fromisoformat(ts_str)
                elif isinstance(ts_val, datetime):
                    timestamp = ts_val
                else:
                    print(f"⚠️ Warning: Unsupported timestamp format: {type(ts_val)}")
                    continue
                
                # Payload Hex to Bytes
                payload_bytes = bytes.fromhex(payload_hex)
                
                if send_uplink(device_id, payload_bytes, timestamp=timestamp):
                    count += 1
                    if count % 10 == 0:
                        print(f"   Sent {count} records...", end='\r')
                
            except Exception as e:
                print(f"Error processing row: {e}")

        print(f"\n[SUCCESS] Imported {count} records from Excel!")
        
    except Exception as e:
        print(f"Error reading Excel: {e}")

def send_uplink(device_id, payload_bytes, timestamp=None):
    payload_b64 = base64.b64encode(payload_bytes).decode('utf-8')
    data = {
        "dev_eui": device_id,
        "data": payload_b64
    }
    if timestamp:
        data["timestamp"] = timestamp.isoformat()
        
    try:
        resp = requests.post(UPLINK_URL, json=data, timeout=5)
        if resp.status_code not in [200, 201]:
             print(f"Failed: {resp.status_code} - {resp.text}")
             return False
        return True
    except Exception as e:
        print(f"\nConnection Error: {e}")
        print("   (Ensure Docker is running: docker-compose up)")
        return False

def main():
    parser = argparse.ArgumentParser(description="Simulate Realistic LoRaWAN Sensor Uplinks")
    parser.add_argument("--device-id", help="Device EUI to simulate", default=None)
    parser.add_argument("--mocks", action="store_true", help="Simulate all default mock sensors")
    parser.add_argument("--loop", action="store_true", help="Run in a continuous real-time loop")
    parser.add_argument("--interval", type=int, default=10, help="Interval in seconds for loop mode")
    parser.add_argument("--history", type=int, default=0, help="Hours of historical data to simulate instantly")
    parser.add_argument("--history-interval", type=int, default=10, help="Interval in minutes between historical data points")
    parser.add_argument("--import-excel", help="Path to an Excel file with 'Timestamp(ISO)' and 'Payload' columns")

    
    args = parser.parse_args()
    
    devices = []
    if args.device_id: devices.append(args.device_id)
    if args.mocks: devices.extend(MOCK_DEVICES)
        
    if not devices:
        print("⚠️ No devices specified.")
        print("Use --device-id <EUI> to simulate a specific sensor, or --mocks.")
        return

    print(f"Target: {UPLINK_URL}")
    print(f"Devices: {', '.join(devices)}")
    
    # Initialize state for each device
    states = {dev: SensorState(dev) for dev in devices}

    # 0. Import from Excel
    if args.import_excel:
        if not args.device_id:
            print("⚠️ Please specify a --device-id for the imported data.")
            return
        import os # Ensure os is available
        process_excel(args.import_excel, args.device_id)
        return

    # 1. Simulate History (Fast-forward)
    if args.history > 0:
        print(f"\n=== Simulating {args.history} hours of history === (Data points every {args.history_interval} min)")
        now = datetime.now()
        start_time = now - timedelta(hours=args.history)
        
        current_time = start_time
        total_points = 0
        while current_time <= now:
            for dev in devices:
                states[dev].drift(minutes_passed=args.history_interval)
                payload = states[dev].generate_payload()
                if send_uplink(dev, payload, timestamp=current_time):
                    total_points += 1
            current_time += timedelta(minutes=args.history_interval)
            print(f"-> Simulated point for time: {current_time.strftime('%Y-%m-%d %H:%M')}", end="\r")
        print(f"\n[SUCCESS] Created {total_points} historical data points instantly!")

    # 2. Real-time loop
    if args.loop:
        print(f"\n=== Starting real-time simulation (interval: {args.interval}s) ===")
        try:
            while True:
                for dev in devices:
                    # In realtime mode we drift by the real interval in seconds, converted to minutes
                    states[dev].drift(minutes_passed=(args.interval / 60.0))
                    payload = states[dev].generate_payload()
                    send_uplink(dev, payload)
                    print(f"Live data sent for {dev} (Temp: {states[dev].temp:.1f}°C)")
                
                print(f"Waiting {args.interval}s...")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nSimulation stopped.")
    
    if not args.loop and args.history == 0:
        # Just send one single packet for each device
        for dev in devices:
            payload = states[dev].generate_payload()
            send_uplink(dev, payload)
            print(f"Sent single pulse for {dev}")

if __name__ == "__main__":
    main()
