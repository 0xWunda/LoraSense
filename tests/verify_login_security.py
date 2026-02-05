
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add paths
sys.path.append(os.path.join(os.getcwd(), 'services', 'dashboard', 'src'))
sys.path.append(os.path.join(os.getcwd(), 'common'))

import dashboard_app as app
import database
from werkzeug.security import generate_password_hash

class TestSecurity(unittest.TestCase):
    def setUp(self):
        app.app.testing = True
        self.client = app.app.test_client()
        # Mock database user response
        self.mock_user = {
            'id': 1,
            'username': 'admin',
            'password_hash': generate_password_hash('admin123'),
            'is_admin': True
        }

    @patch('database.get_user_by_username')
    def test_login_success(self, mock_get_user):
        print("\n--- Testing Valid Login ---")
        mock_get_user.return_value = self.mock_user
        
        res = self.client.post('/api/login', json={
            'username': 'admin',
            'password': 'admin123'
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json['success'])
        print("✅ Valid login successful")

    @patch('database.get_user_by_username')
    def test_login_failure_wrong_password(self, mock_get_user):
        print("\n--- Testing Invalid Password ---")
        mock_get_user.return_value = self.mock_user
        
        res = self.client.post('/api/login', json={
            'username': 'admin',
            'password': 'wrongpassword'
        })
        self.assertEqual(res.status_code, 401)
        self.assertFalse(res.json['success'])
        print("✅ Invalid password rejected")

    @patch('database.get_user_by_username')
    def test_backdoor_removed(self, mock_get_user):
        print("\n--- Testing Backdoor Removal ---")
        # Ensure that if DB returns None, the hardcoded backdoor doesn't catch it
        mock_get_user.return_value = None
        
        res = self.client.post('/api/login', json={
            'username': 'admin',
            'password': 'admin123'
        })
        
        # If backdoor was present, this would be 200. Now it should be 401.
        self.assertEqual(res.status_code, 401)
        print("✅ Backdoor verified removed (admin/admin123 failed when DB returned None)")

if __name__ == '__main__':
    unittest.main()
