FROM python:3.11-slim

WORKDIR /app

COPY apps/dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/dashboard/src/ .
COPY libs/common/database.py .
RUN mkdir -p common
COPY libs/common/logging_config.py common/logging_config.py
RUN touch common/__init__.py
COPY apps/dashboard/static/ static/

EXPOSE 8080

CMD ["python", "dashboard_app.py"]
