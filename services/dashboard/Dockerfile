FROM python:3.11-slim

WORKDIR /app

COPY services/dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/dashboard/src/ .
# COPY common/database.py .
COPY services/dashboard/website/ website/

EXPOSE 8080

CMD ["python", "app.py"]
