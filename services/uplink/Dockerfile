FROM python:3.11-slim

WORKDIR /app

COPY services/uplink/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/uplink/src/ .
COPY common/database.py .

EXPOSE 5000

CMD ["python", "app.py"]
