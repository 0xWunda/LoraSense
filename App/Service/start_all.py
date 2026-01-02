import subprocess
import time

# Pfade zu deinen Servern
uplink_script = "/home/wunder/Lorasense/uplink_server.py"
dashboard_script = "/home/wunder/Lorasense/dashboard_server.py"

print("🚀 Starte LoraSense Uplink-Server...")
uplink_proc = subprocess.Popen(["python3", uplink_script])

# kurz warten, bis uplink läuft
time.sleep(2)

print("🌐 Starte LoraSense Dashboard...")
dashboard_proc = subprocess.Popen(["python3", dashboard_script])

print("✅ Beide Server laufen. (Uplink:5000, Dashboard:443)")

try:
    uplink_proc.wait()
    dashboard_proc.wait()
except KeyboardInterrupt:
    print("\n🛑 Stoppe beide Server...")
    uplink_proc.terminate()
    dashboard_proc.terminate()
