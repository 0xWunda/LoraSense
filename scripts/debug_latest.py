import os
import sys
sys.path.append(os.getcwd())
from common import database
import json

# Set env for local run
os.environ['MYSQL_HOST'] = 'localhost'

def test():
    sensor_id = 'AABBCC01020306'
    print(f"Testing get_latest_data for {sensor_id}...")
    data = database.get_latest_data(limit=1, sensor_id=sensor_id)
    print(f"Result: {json.dumps(data, indent=2)}")

if __name__ == "__main__":
    test()
