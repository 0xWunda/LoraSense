import sys
import os
import unittest
import base64

# Add common directory to path
sys.path.append(os.path.join(os.getcwd(), 'libs/common'))

from decoder import decode_payload, DecoderFactory

class TestMultiSensor(unittest.TestCase):
    def test_barani_v1_decoding(self):
        print("\n--- Testing Barani V1 (Weather Station) ---")
        # Sample Barani payload (from previous tests)
        payload_b64 = "XyxAArEz8AAAAP8=" 
        payload_bytes = base64.b64decode(payload_b64)
        
        # Test with explicit config
        decoded = decode_payload(payload_bytes, config_str="v1")
        print(f"Decoded (v1): {decoded}")
        self.assertIn("Temperature", decoded)
        self.assertIn("Battery", decoded)
        self.assertEqual(decoded["Type"], 1) # Corrected from 0 to 1 based on sample
        
        # Test with alias
        decoded_alias = decode_payload(payload_bytes, config_str="barani")
        self.assertEqual(decoded, decoded_alias)

    def test_simple_sensor_decoding(self):
        print("\n--- Testing Simple Sensor (Alternative Type) ---")
        # Simple sensor expects [Temp+40, Hum]
        # Let's send 25C (65) and 50% Hum (50)
        payload_bytes = bytes([65, 50])
        
        decoded = decode_payload(payload_bytes, config_str="simple")
        print(f"Decoded (simple): {decoded}")
        
        self.assertEqual(decoded["Temperature"], 25.0)
        self.assertEqual(decoded["Humidity"], 50.0)
        self.assertEqual(decoded["Status"], "Simple Decoded")

    def test_factory_fallback(self):
        print("\n--- Testing Factory Fallback (Unknown -> Barani) ---")
        payload_b64 = "XyxAArEz8AAAAP8=" 
        payload_bytes = base64.b64decode(payload_b64)
        
        decoded = decode_payload(payload_bytes, config_str="unknown_type")
        self.assertIn("Temperature", decoded)
        print("Fallback to default (Barani) verified.")

if __name__ == '__main__':
    unittest.main()
