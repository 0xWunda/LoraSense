import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add the necessary paths
sys.path.append(os.path.join(os.getcwd(), "services", "uplink", "src"))
sys.path.append(os.path.join(os.getcwd(), "common"))

import app as uplink_app
import database

class TestLoRaSenseLogic(unittest.TestCase):
    def setUp(self):
        uplink_app.app.testing = True
        self.client = uplink_app.app.test_client()

    def test_decoder(self):
        print("\n--- Testing Decoder ---")
        # Sample payload from the original code
        payload_b64 = "XyxAArEz8AAAAP8=" 
        import base64
        payload_bytes = base64.b64decode(payload_b64)
        
        decoded = uplink_app.Decoder(payload_bytes)
        print(f"Decoded values: {decoded}")
        
        # Verify some key values (based on original file's results)
        self.assertIn("Temperature", decoded)
        self.assertIn("Battery", decoded)
        self.assertIn("Humidity", decoded)
        print("✅ Decoder logic verified.")

    @patch("database.save_sensor_data")
    @patch("database.init_db")
    def test_uplink_endpoint(self, mock_init, mock_save):
        print("\n--- Testing Uplink Endpoint (Mocked DB) ---")
        mock_save.return_value = True
        
        test_data = {"data": "XyxAArEz8AAAAP8="}
        response = self.client.post("/uplink", json=test_data)
        
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(mock_save.called)
        print("✅ Uplink endpoint handles requests and calls database.")

if __name__ == "__main__":
    unittest.main()
