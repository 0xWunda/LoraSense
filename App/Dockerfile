FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose ports
EXPOSE 5000 8080

# Command is overridden in docker-compose, but we can provide a default
CMD ["python3", "Service/uplink_server.py"]
