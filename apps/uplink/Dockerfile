FROM python:3.11-slim

WORKDIR /app

COPY apps/uplink/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/uplink/src/ .
COPY libs/common/database.py .
RUN mkdir -p common
COPY libs/common/decoder.py common/decoder.py
COPY libs/common/logging_config.py common/logging_config.py
RUN touch common/__init__.py

EXPOSE 5000

CMD ["python", "uplink_app.py"]
