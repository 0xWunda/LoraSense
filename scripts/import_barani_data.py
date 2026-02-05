import openpyxl
import os
import sys
import base64
from datetime import datetime

# Setup paths (add root to path)
sys.path.append(os.getcwd())

from common import database
from common.decoder import decode_payload

FILE_PATH = r"c:\Users\Wieserling\Downloads\Barani_Payload_LoRa.xlsx"
DEVICE_EUI = "Barani_Import_Device"
DEVICE_NAME = "Barani MeteoHelix (Imported)"
SENSOR_TYPE_NAME = "Barani MeteoHelix" # Must match DB

def run_import():
    if not os.path.exists(FILE_PATH):
        print(f"❌ File not found: {FILE_PATH}")
        return

    print("Connecting to DB...")
    database.init_db()

    # 1. Ensure Device Exists
    device = database.get_device_by_eui(DEVICE_EUI)
    if not device:
        print(f"Creating new device: {DEVICE_NAME} ({DEVICE_EUI})")
        # Find sensor type ID
        types = database.get_sensor_types()
        type_id = next((t['id'] for t in types if t['name'] == SENSOR_TYPE_NAME), 1)
        
        database.create_device(
            dev_eui=DEVICE_EUI, 
            name=DEVICE_NAME, 
            sensor_type_id=type_id
        )
        device = database.get_device_by_eui(DEVICE_EUI)
    else:
        print(f"Found existing device: {device['name']}")

    # 2. Read Excel
    print(f"Reading {FILE_PATH}...")
    try:
        wb = openpyxl.load_workbook(FILE_PATH, read_only=True, data_only=True)
        sheet = wb.active
        
        count = 0
        errors = 0
        
        # Skip header (row 1)
        rows = sheet.iter_rows(min_row=2, values_only=True)
        
        for row in rows:
            if not row or len(row) < 2:
                continue
                
            ts_str, payload_hex = row[0], row[1]
            
            if not ts_str or not payload_hex:
                 continue

            try:
                # Parse Timestamp (ISO)
                # Example: 2026-01-21T13:06:09.911Z
                # Python < 3.11 fromisoformat might struggle with Z. 
                # Let's simple fix
                ts_str = str(ts_str).replace("Z", "+00:00")
                timestamp = datetime.fromisoformat(ts_str)
                
                # Convert Hex to Bytes
                payload_bytes = bytes.fromhex(payload_hex)
                payload_b64 = base64.b64encode(payload_bytes).decode('utf-8')
                
                # Decode
                decoded = decode_payload(payload_bytes)
                
                # Save Uplink
                database.save_uplink(
                    dev_eui=DEVICE_EUI,
                    payload_raw=payload_b64,
                    device_db_id=device['id'],
                    received_at=timestamp
                )
                
                # Save Sensor Data
                database.save_sensor_data(
                    raw_payload=payload_b64,
                    decoded=decoded,
                    device_id=DEVICE_EUI,
                    timestamp=timestamp
                )
                
                count += 1
                if count % 100 == 0:
                    print(f"   Processed {count} records...", end='\r')
                    
            except Exception as e:
                print(f"Error processing row {row}: {e}")
                errors += 1
        
        print(f"\nImport finished. Imported: {count}, Errors: {errors}")
        
    except Exception as e:
        print(f"Error reading Excel: {e}")

if __name__ == "__main__":
    run_import()
