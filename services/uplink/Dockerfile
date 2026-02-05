FROM python:3.11-slim

WORKDIR /app

COPY services/uplink/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/uplink/src/ .
COPY common/database.py .
RUN mkdir -p common
COPY common/decoder.py common/decoder.py
RUN touch common/__init__.py

EXPOSE 5000

CMD ["python", "uplink_app.py"]
