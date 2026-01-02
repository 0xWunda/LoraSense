from flask import Flask, render_template, jsonify, Response
import io
import csv
from flask_cors import CORS
import os
import database

# Paths inside container
WEBSITE_DIR = os.path.join(os.getcwd(), "website")

app = Flask(__name__, template_folder=WEBSITE_DIR, static_folder=WEBSITE_DIR)
CORS(app)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/data")
def api_data():
    history = database.get_latest_data(limit=20)
    return jsonify(history)

@app.route("/api/export")
def export_data():
    history = database.get_latest_data(limit=1000)
    
    def generate():
        data = io.StringIO()
        writer = csv.writer(data)
        
        # Header
        writer.writerow(['Timestamp', 'Type', 'Battery_V', 'Temp_C', 'Humidity_%', 'Pressure_hPa', 'Irradiation', 'Rain'])
        yield data.getvalue()
        data.seek(0)
        data.truncate(0)
        
        for item in history:
            d = item['decoded']
            writer.writerow([
                item['timestamp'],
                d.get('Type'),
                d.get('Battery'),
                d.get('Temperature'),
                d.get('Humidity'),
                d.get('Pressure'),
                d.get('Irradiation'),
                d.get('Rain')
            ])
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=lorasense_data.csv"}
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
