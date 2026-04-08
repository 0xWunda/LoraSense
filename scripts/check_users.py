from common import database
import os

print(f"MYSQL_HOST: {os.getenv('MYSQL_HOST')}")
print(f"MYSQL_USER: {os.getenv('MYSQL_USER')}")

database.init_db()
user = database.get_user_by_username("admin")
if user:
    print(f"User 'admin' found: ID={user['id']}, is_admin={user['is_admin']}")
    print(f"Hash: {user['password_hash']}")
else:
    print("User 'admin' not found.")

# Try to list all users
users = database.get_all_users()
print("All users:", users)
