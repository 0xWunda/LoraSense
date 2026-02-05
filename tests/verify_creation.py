
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'services', 'dashboard', 'src'))

import database
import app
from flask import session

def test_user_creation():
    print("Testing User Creation...")
    
    # Init DB
    database.init_db()
    
    # 1. Test direct database function
    print("\n1. Testing database.create_user...")
    test_user = "verify_user_" + str(os.getpid())
    success = database.create_user(test_user, "password123", is_admin=False)
    if success:
        print(f"SUCCESS: Created user {test_user}")
    else:
        print(f"FAILURE: Could not create user {test_user}")
        
    # Verify user exists
    u = database.get_user_by_username(test_user)
    if u:
        print(f"SUCCESS: User {test_user} found in DB")
    else:
        print(f"FAILURE: User {test_user} NOT found in DB")

    # 2. Test API endpoint
    print("\n2. Testing API /api/admin/users/create...")
    client = app.app.test_client()
    
    # Login as admin first (mock session)
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'admin'
        sess['is_admin'] = True
        
    api_user = "api_user_" + str(os.getpid())
    res = client.post('/api/admin/users/create', json={
        "username": api_user,
        "password": "apipassword",
        "is_admin": True
    })
    
    if res.status_code == 200 and res.json.get('success'):
        print(f"SUCCESS: API created user {api_user}")
    else:
        print(f"FAILURE: API failed. Status: {res.status_code}, Response: {res.get_data(as_text=True)}")

    # Verify API user
    u2 = database.get_user_by_username(api_user)
    if u2 and u2['is_admin']:
        print(f"SUCCESS: API User {api_user} found and is admin")
    else:
        print(f"FAILURE: API User {api_user} verification failed")

if __name__ == "__main__":
    test_user_creation()
