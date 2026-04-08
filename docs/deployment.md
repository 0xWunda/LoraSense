# 3.6 Deployment und Systembetrieb

## 3.6.1 Deployment mit Docker Compose

### Überblick der Container-Architektur

Das LoraSense-System wird vollständig containerisiert über Docker Compose betrieben. Die Architektur besteht aus vier Services, die in einem gemeinsamen Docker-Netzwerk kommunizieren:

```
┌──────────────────────────────────────────────────────────────┐
│                    Docker Compose Umgebung                    │
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐  ┌──────────┐ │
│  │    db     │    │  uplink  │    │dashboard │  │phpmyadmin│ │
│  │MariaDB   │◄───│  Flask   │    │  Flask   │  │   Web    │ │
│  │10.6      │◄───│  :5000   │    │  :8080   │──│   :80    │ │
│  │  :3306   │    │          │    │          │  │          │ │
│  └──────────┘    └──────────┘    └──────────┘  └──────────┘ │
│       ▲                                             │        │
│       └─────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────────┘
     :3306            :5001            :8080         :8081
   (optional)    (Uplink API)     (Dashboard)    (DB Admin)
```

### Docker Compose Konfiguration

Die gesamte Infrastruktur wird in der Datei `docker-compose.yml` definiert:

```yaml
services:
  db:
    image: mariadb:10.6
    restart: always
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: ${MYSQL_DATABASE}
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    volumes:
      - db_data:/var/lib/mysql        # Persistenter Speicher für DB-Daten
    ports:
      - "${DB_PORT:-3306}:3306"       # Externer Zugriff (optional)
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost",
             "-u", "${MYSQL_USER}", "-p${MYSQL_PASSWORD}"]
      timeout: 20s
      retries: 10

  uplink:
    build:
      context: .                       # Build-Context = Projektwurzel
      dockerfile: apps/uplink/Dockerfile
    depends_on:
      db:
        condition: service_started
    environment:
      - MYSQL_HOST=db                  # Docker-interner Hostname
      - MYSQL_USER=${MYSQL_USER}
      - MYSQL_PASSWORD=${MYSQL_PASSWORD}
      - MYSQL_DATABASE=${MYSQL_DATABASE}
      - PYTHONUNBUFFERED=1             # Echtzeit-Logging in Docker
    ports:
      - "${UPLINK_PORT:-5001}:5000"
    command: python uplink_app.py
    volumes:
      - ./apps/uplink/src:/app         # Live-Code-Mounting (Entwicklung)
      - ./libs/common:/app/common      # Shared Library
      - ./storage/data:/storage/data   # SQLite-Fallback-Datenbank
      - ./storage/logs/uplink:/storage/logs  # Log-Dateien

  dashboard:
    build:
      context: .
      dockerfile: apps/dashboard/Dockerfile
    depends_on:
      db:
        condition: service_started
    volumes:
      - ./apps/dashboard/src:/app
      - ./apps/dashboard/static:/app/static
      - ./libs/common:/app/common
      - ./storage/data:/storage/data
      - ./storage/logs/dashboard:/storage/logs
    environment:
      - MYSQL_HOST=db
      - MYSQL_USER=${MYSQL_USER}
      - MYSQL_PASSWORD=${MYSQL_PASSWORD}
      - MYSQL_DATABASE=${MYSQL_DATABASE}
      - FLASK_SECRET=${FLASK_SECRET}   # Schlüssel für Session-Cookies
    ports:
      - "${DASHBOARD_PORT:-8080}:8080"
    command: python dashboard_app.py

  phpmyadmin:
    image: phpmyadmin:latest
    restart: always
    depends_on:
      db:
        condition: service_healthy     # Wartet auf Healthcheck
    environment:
      - PMA_HOST=db
      - PMA_USER=${MYSQL_USER}
      - PMA_PASSWORD=${MYSQL_PASSWORD}
    ports:
      - "${PHPMYADMIN_PORT:-8081}:80"

volumes:
  db_data:                             # Named Volume für MariaDB
```

### Service-Beschreibung

| Service | Image / Build | Port (Host) | Funktion |
|---|---|---|---|
| `db` | `mariadb:10.6` | 3306 | Primäre Datenbank (MariaDB) |
| `uplink` | Custom (Python 3.11) | 5001 | Empfängt LoRaWAN-Uplinks, dekodiert Payloads |
| `dashboard` | Custom (Python 3.11) | 8080 | Web-Frontend, REST API, Benutzerverwaltung |
| `phpmyadmin` | `phpmyadmin:latest` | 8081 | Datenbank-Administration (Web-GUI) |

### Dockerfile-Aufbau

Beide Python-Services verwenden identische Build-Strategien auf Basis von `python:3.11-slim`:

```dockerfile
# Beispiel: apps/uplink/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 1. Dependencies installieren (eigene Schicht für Docker-Cache)
COPY apps/uplink/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Anwendungscode kopieren
COPY apps/uplink/src/ .

# 3. Shared Library einbinden
COPY libs/common/database.py .
RUN mkdir -p common
COPY libs/common/decoder.py common/decoder.py
COPY libs/common/logging_config.py common/logging_config.py
RUN touch common/__init__.py

EXPOSE 5000
CMD ["python", "uplink_app.py"]
```

**Design-Entscheidungen:**
- **`python:3.11-slim`**: Minimales Base-Image (~120 MB) für geringe Containergröße.
- **Zweistufiger COPY**: `requirements.txt` wird separat kopiert, damit der Docker-Build-Cache den `pip install`-Schritt nur bei Änderungen der Abhängigkeiten wiederholt.
- **Shared Library als Kopie**: Die `libs/common/`-Module werden in ein `common/`-Paket im Container kopiert und mittels `__init__.py` als Python-Package registriert.

### Python-Abhängigkeiten

**Uplink-Service** (`apps/uplink/requirements.txt`):
```
flask
mysql-connector-python
```

**Dashboard-Service** (`apps/dashboard/requirements.txt`):
```
flask
flask-cors
mysql-connector-python
werkzeug
```

### Umgebungsvariablen

Die Konfiguration erfolgt über eine `.env`-Datei im Projektstammverzeichnis (nicht im Git-Repository enthalten):

```bash
# .env – Beispielkonfiguration
MYSQL_ROOT_PASSWORD=sicheres_root_passwort
MYSQL_DATABASE=lorasense_db
MYSQL_USER=lora_user
MYSQL_PASSWORD=lora_pass

# Flask
FLASK_SECRET=ein_zufaelliger_geheimer_schluessel

# Port-Konfiguration (optional, Defaults in docker-compose.yml)
DB_PORT=3306
UPLINK_PORT=5001
DASHBOARD_PORT=8080
PHPMYADMIN_PORT=8081
```

| Variable | Beschreibung | Default |
|---|---|---|
| `MYSQL_ROOT_PASSWORD` | Root-Passwort der MariaDB | – (erforderlich) |
| `MYSQL_DATABASE` | Name der Datenbank | `lorasense_db` |
| `MYSQL_USER` | Datenbankbenutzer | `lora_user` |
| `MYSQL_PASSWORD` | Passwort des Datenbankbenutzers | `lora_pass` |
| `FLASK_SECRET` | Geheimer Schlüssel für Flask-Sessions | Zufällig generiert |
| `UPLINK_PORT` | Host-Port für den Uplink-Service | `5001` |
| `DASHBOARD_PORT` | Host-Port für das Dashboard | `8080` |
| `PHPMYADMIN_PORT` | Host-Port für phpMyAdmin | `8081` |

### Volume-Mounts und Datenorganisation

```
LoraSense/
├── storage/
│   ├── data/                          # Persistente Daten
│   │   ├── lorasense.db               # SQLite (Hauptdatenbank bei Fallback)
│   │   └── lorasense_fallback.db      # SQLite-Fallback-Datenbank
│   └── logs/                          # Log-Dateien aller Services
│       ├── dashboard/                 # Dashboard-Logs
│       │   └── dashboard.log
│       ├── uplink/                    # Uplink-Logs
│       │   └── uplink.log
│       ├── database.log               # Datenbankoperationen
│       └── simulation.out             # Sensor-Simulator-Ausgaben
└── docker-compose.yml
```

**Volume-Zuordnung:**

| Host-Pfad | Container-Pfad | Zweck |
|---|---|---|
| `./storage/data` | `/storage/data` | SQLite-Fallback-Datenbank |
| `./storage/logs/uplink` | `/storage/logs` | Log-Dateien des Uplink-Service |
| `./storage/logs/dashboard` | `/storage/logs` | Log-Dateien des Dashboards |
| `db_data` (Named Volume) | `/var/lib/mysql` | MariaDB-Datenbankdateien |

### Deployment-Befehle

```bash
# 1. .env-Datei erstellen (einmalig)
cp .env.example .env
# → Werte anpassen (insbesondere Passwörter und FLASK_SECRET)

# 2. System starten (erster Start: baut Images automatisch)
docker-compose up -d

# 3. Status prüfen
docker-compose ps

# 4. Logs anzeigen (alle Services)
docker-compose logs -f

# 5. System stoppen
docker-compose down

# 6. System stoppen und Datenbank-Volume löschen (Neustart)
docker-compose down -v
```

## 3.6.2 Start- und Initialisierungsprozess

### Startreihenfolge der Services

Docker Compose startet die Services gemäß den definierten Abhängigkeiten:

```
1. db (MariaDB)           → Startet zuerst, Healthcheck aktiv
   │
   ├── 2a. uplink         → Startet nach db (condition: service_started)
   │
   ├── 2b. dashboard      → Startet nach db (condition: service_started)
   │
   └── 3. phpmyadmin      → Startet nach db (condition: service_healthy)
```

**Wichtig:** Die Python-Services (`uplink`, `dashboard`) starten bereits, sobald der DB-Container läuft (`service_started`), warten aber **nicht** auf den Abschluss des Healthchecks. Die Datenbankverbindung wird daher im Anwendungscode mit einem Retry-Mechanismus behandelt.

### Datenbankverbindung mit Retry und Fallback

Die Klasse `DBConnection` in `libs/common/database.py` implementiert eine resiliente Verbindungsstrategie:

```python
def get_db_connection():
    """
    Verbindungsaufbau mit 3 Versuchen zu MariaDB.
    Fallback auf SQLite bei dauerhafter Nichtverfügbarkeit.
    """
    max_retries = 3
    retry_delay = 2  # Sekunden

    # Anmeldedaten aus Umgebungsvariablen
    db_host = os.getenv("MYSQL_HOST", "db")
    db_user = os.getenv("MYSQL_USER", "lora_user")
    db_pass = os.getenv("MYSQL_PASSWORD", "lora_pass")
    db_name = os.getenv("MYSQL_DATABASE", "lorasense_db")

    # MariaDB-Versuche
    for attempt in range(max_retries):
        try:
            conn = mysql.connector.connect(
                host=db_host, user=db_user,
                password=db_pass, database=db_name,
                connect_timeout=5
            )
            return DBConnection(conn, 'mysql')
        except mysql.connector.Error as err:
            logger.warning(
                f"Warten auf MariaDB... ({max_retries - attempt - 1} Versuche übrig)"
            )
            if attempt < max_retries - 1:
                time.sleep(retry_delay)

    # Automatisches Fallback auf SQLite
    logger.warning("MariaDB nicht verfügbar. Nutze SQLite Fallback.")
    conn = sqlite3.connect("/storage/data/lorasense_fallback.db")
    return DBConnection(conn, 'sqlite')
```

**Zeitlicher Ablauf:**
1. **Versuch 1**: Sofortige Verbindung zu MariaDB (Timeout: 5s)
2. **Versuch 2**: Nach 2s Wartezeit erneuter Versuch
3. **Versuch 3**: Nach weiteren 2s letzter Versuch
4. **Fallback**: SQLite-Datenbank unter `/storage/data/lorasense_fallback.db`

### Datenbank-Schema-Initialisierung

Die Funktion `init_db()` wird beim Start jedes Services aufgerufen und erstellt das vollständige Datenbankschema idempotent (nur wenn Tabellen noch nicht existieren):

```python
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    db_type = conn.db_type

    # Automatische Anpassung der SQL-Syntax an den DB-Typ
    # MariaDB: AUTO_INCREMENT, %s Platzhalter
    # SQLite:  AUTOINCREMENT, ? Platzhalter

    # Tabellen erstellen (CREATE TABLE IF NOT EXISTS)
    # 1. sensor_data  – Messwerte
    # 2. users        – Benutzerkonten
    # 3. user_sensors – ACL (Benutzer ↔ Sensor-Zuordnung)
    # 4. sensor_types – Decoder-Profile
    # 5. devices      – Registrierte LoRaWAN-Geräte
    # 6. uplinks      – Rohe Uplink-Logs
```

**Erstellte Tabellen:**

| Tabelle | Spalten (Auszug) | Zweck |
|---|---|---|
| `sensor_data` | `timestamp`, `temperature`, `humidity`, `pressure`, `device_id` | Dekodierte Messwerte |
| `users` | `username`, `password_hash`, `is_admin` | Benutzerkonten |
| `user_sensors` | `user_id`, `sensor_id` | Zugriffsrechte (ACL) |
| `sensor_types` | `name`, `decoder_config` | Decoder-Profile (z. B. Barani, Dragino) |
| `devices` | `dev_eui`, `name`, `sensor_type_id`, `app_key`, `nwk_key` | Registrierte Geräte |
| `uplinks` | `dev_eui`, `payload_raw`, `rssi`, `snr` | Debug-Logs der Rohdaten |

### Automatische Migrationen

Die `init_db()`-Funktion führt einfache Schema-Migrationen durch, um ältere Datenbankversionen kompatibel zu halten:

```python
# Beispiel: Migration der 'is_admin'-Spalte
if db_type == 'mysql':
    cursor.execute("SHOW COLUMNS FROM users LIKE 'is_admin'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")
else:
    cursor.execute("PRAGMA table_info(users)")
    cols = [c[1] for c in cursor.fetchall()]
    if 'is_admin' not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")
```

### Standard-Daten beim Erststart

Bei der ersten Initialisierung werden automatisch angelegt:

**Benutzer:**

| Benutzername | Passwort | Admin | Beschreibung |
|---|---|---|---|
| `admin` | `admin123` | ✅ | Standard-Administrator |
| `testuser` | `test123` | ❌ | Testbenutzer |
| `testuser1` | `test1123` | ❌ | Weiterer Testbenutzer |
| `testuser2` | `test2123` | ❌ | Weiterer Testbenutzer |

**Sensortypen:**

| Name | Decoder-Config | Beschreibung |
|---|---|---|
| Barani MeteoHelix | `v1` | Wetterstation mit Bit-Parsing |
| Dragino LHT65 | `v1` | Temperatur-/Feuchtigkeitssensor |
| Custom Payload | `custom` | Benutzerdefiniertes Format |

### Vollständiger Startablauf (Sequenzdiagramm)

```
Docker Compose                MariaDB              Uplink / Dashboard
     │                          │                        │
     │──── docker-compose up ──►│                        │
     │                          │ Starte MariaDB         │
     │                          │ Healthcheck: ping      │
     │                          │                        │
     │───────────────────────────────────────────────────►│
     │                          │                 Starte Python-App
     │                          │                        │
     │                          │    ◄── get_db_connection()
     │                          │    │   (max 3 Retries)
     │                          │    ├── Versuch 1 ──────►│
     │                          │    │   ◄── Verbunden   │
     │                          │    │                    │
     │                          │    ├── init_db() ──────►│
     │                          │    │   CREATE TABLE ... │
     │                          │    │   INSERT admin ... │
     │                          │    │   INSERT types ... │
     │                          │    │                    │
     │                          │    └── app.run() ──────►│
     │                          │         Server bereit   │
```

## 3.6.3 Wartung und Monitoring

### Logging-System

Das LoraSense-System verwendet ein zentrales Logging-Modul (`libs/common/logging_config.py`) mit **dualer Ausgabe** (Konsole + Datei):

```python
def setup_logging(service_name, log_dir="/storage/logs", log_level=logging.INFO):
    logger = logging.getLogger(service_name)

    # Format: 2026-03-04 10:15:23 - uplink - INFO - Nachricht
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 1. Konsolenausgabe (sichtbar via `docker-compose logs`)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. Rotierende Datei-Logs (max. 5 MB, 3 Backups)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5*1024*1024,   # 5 MB pro Datei
        backupCount=3           # Behält 3 ältere Versionen
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
```

**Log-Rotation:**
- Jede Log-Datei wird bei 5 MB Größe rotiert
- Es werden maximal 3 Backup-Dateien behalten (z. B. `uplink.log`, `uplink.log.1`, `uplink.log.2`, `uplink.log.3`)
- Maximaler Speicherverbrauch pro Service: **20 MB** (4 × 5 MB)

**Log-Dateien im System:**

| Datei | Quelle | Inhalt |
|---|---|---|
| `storage/logs/uplink/uplink.log` | Uplink-Service | Eingehende Payloads, Dekodierungsergebnisse |
| `storage/logs/dashboard/dashboard.log` | Dashboard-Service | API-Zugriffe, Login-Versuche |
| `storage/logs/database.log` | Datenbankmodul | Verbindungsfehler, Migrationen, Queries |

### Docker-Monitoring

```bash
# Container-Status und Ressourcenverbrauch
docker-compose ps
docker stats

# Echtzeit-Logs aller Services
docker-compose logs -f

# Logs eines einzelnen Services
docker-compose logs -f uplink
docker-compose logs -f dashboard

# MariaDB Healthcheck-Status
docker inspect --format='{{.State.Health.Status}}' lorasense-db-1
```

### Datenbank-Wartung

**Zugriff über phpMyAdmin:**

phpMyAdmin ist unter `http://localhost:8081` erreichbar und bietet eine grafische Oberfläche für:
- SQL-Abfragen und Datenexploration
- Tabellenstruktur-Inspektion
- Datenexport (CSV, SQL)

**Direkter MariaDB-Zugriff:**

```bash
# SQL-Shell im Container öffnen
docker-compose exec db mysql -u lora_user -plora_pass lorasense_db

# Beispiel-Abfragen:
# Anzahl der gespeicherten Messwerte
SELECT COUNT(*) FROM sensor_data;

# Letzten 10 Uplinks anzeigen
SELECT * FROM sensor_data ORDER BY timestamp DESC LIMIT 10;

# Registrierte Geräte auflisten
SELECT dev_eui, name, status FROM devices;
```

**Datenbank-Backup:**

```bash
# MariaDB-Dump erstellen
docker-compose exec db mysqldump -u lora_user -plora_pass lorasense_db > backup.sql

# Backup wiederherstellen
docker-compose exec -T db mysql -u lora_user -plora_pass lorasense_db < backup.sql
```

### Service-Neustart und Updates

```bash
# Einzelnen Service neu starten (ohne andere zu beeinflussen)
docker-compose restart uplink
docker-compose restart dashboard

# Images neu bauen (nach Code-Änderungen)
docker-compose build uplink dashboard

# Build und Neustart kombiniert
docker-compose up -d --build

# Vollständiger Neustart ohne Datenverlust
docker-compose down
docker-compose up -d

# Vollständiger Neustart MIT Datenlöschen (Zurücksetzen)
docker-compose down -v    # Löscht auch das db_data Volume
docker-compose up -d
```

### SQLite-Fallback-Überwachung

Das System erkennt Datenbankausfälle automatisch und wechselt zu SQLite. Um den aktuellen Zustand zu prüfen:

```bash
# Prüfen, ob SQLite-Fallback aktiv ist
# (Existenz und Größe der Fallback-DB prüfen)
ls -la storage/data/lorasense_fallback.db

# In den Logs nach Fallback-Hinweisen suchen
grep -i "sqlite" storage/logs/uplink/uplink.log
grep -i "fallback" storage/logs/database.log
```

Das `PYTHONUNBUFFERED=1`-Environment-Flag stellt sicher, dass alle Log-Ausgaben der Python-Services sofort in den Docker-Logs erscheinen und nicht im Ausgabepuffer verzögert werden.

### Sensorsimulation für Funktionstests

Für die Funktionsüberprüfung des laufenden Systems steht der Sensor-Simulator bereit:

```bash
# Einzelnen Test-Uplink senden
python scripts/simulate_sensor.py --device-id "TestSensor-01"

# Alle Mock-Sensoren mit Daten versorgen
python scripts/simulate_sensor.py --mocks

# Dauerbetrieb (alle 10 Sekunden neue Daten)
python scripts/simulate_sensor.py --mocks --loop --interval 10
```

### Übersicht wichtiger Pfade

| Pfad | Typ | Beschreibung |
|---|---|---|
| `docker-compose.yml` | Konfiguration | Docker-Infrastruktur |
| `.env` | Konfiguration | Umgebungsvariablen (nicht im Git) |
| `apps/uplink/Dockerfile` | Build | Container-Build Uplink |
| `apps/dashboard/Dockerfile` | Build | Container-Build Dashboard |
| `libs/common/` | Shared Code | Datenbank, Decoder, Logging |
| `storage/data/` | Persistenz | SQLite-Fallback-Datenbanken |
| `storage/logs/` | Monitoring | Rotierende Log-Dateien |
| `scripts/simulate_sensor.py` | Werkzeug | Sensorsimulation |
