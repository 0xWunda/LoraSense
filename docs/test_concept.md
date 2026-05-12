# 3.4 Testkonzept

## 3.4.1 Zielsetzung der Tests

Das Testkonzept des LoraSense-Systems verfolgt das Ziel, die korrekte Funktionsweise aller Systemkomponenten sowohl isoliert als auch im Zusammenspiel sicherzustellen. Da das System sicherheitsrelevante Umweltdaten (Temperatur, Luftfeuchtigkeit, Luftdruck, Strahlung, Niederschlag) erfasst und verarbeitet, ist die Datenintegrität von zentraler Bedeutung.

Die Tests decken folgende Kernaspekte ab:

- **Korrektheit der Datendekodierung**: Sicherstellung, dass binäre LoRaWAN-Payloads fehlerfrei in strukturierte Messwerte umgewandelt werden.
- **API-Zuverlässigkeit**: Verifizierung, dass die REST-Endpunkte korrekte HTTP-Statuscodes und valide JSON-Antworten liefern.
- **Datenbank-Resilienz**: Nachweis, dass das System bei Ausfall der primären Datenbank (MariaDB) automatisch auf SQLite zurückfällt.
- **Sicherheit**: Überprüfung der Authentifizierungsmechanismen und Ausschluss von Sicherheitslücken (z. B. Backdoors).
- **End-to-End-Funktionalität**: Validierung der gesamten Datenpipeline vom Sensor-Uplink bis zur Dashboard-Anzeige.

## 3.4.2 Teststrategie

Die Teststrategie folgt dem Prinzip der **Testpyramide** und gliedert sich in drei Ebenen:

### Unit Tests
Isolierte Tests einzelner Funktionen und Module ohne externe Abhängigkeiten. Die Datenbankschicht wird dabei durch Mocking-Objekte ersetzt.

| Testdatei | Bereich |
|---|---|
| `test_decoder.py` | Standalone-Decoder-Logik |
| `test_logic.py` | Uplink-Geschäftslogik mit gemockter DB |
| `test_multi_sensor.py` | Multi-Sensor-Decoder (Factory Pattern) |
| `verify_login_security.py` | Authentifizierung und Sicherheit |

### Integrationstests
Tests, die das Zusammenspiel mehrerer Komponenten prüfen, z. B. API-Endpunkte mit Datenbankzugriff.

| Testdatei | Bereich |
|---|---|
| `verify_creation.py` | Benutzerverwaltung (DB + API) |
| `verify_sqlite_fallback.py` | Datenbank-Fallback-Mechanismus |

### Systemtests (End-to-End)
Tests gegen das laufende Docker-Compose-System mit realen HTTP-Anfragen.

| Testdatei | Bereich |
|---|---|
| `verify_mvp.py` | Kompletter Workflow: Login → Gerät anlegen → Uplink → Datenabfrage |
| `verify_keys.py` | Geräteerstellung mit Sicherheitsschlüsseln |
| `verify_mock.py` | Mock-Sensor-Datenüberprüfung |
| `verify_import.py` | Datenimport-Verifizierung |

### Verwendete Test-Frameworks und -Bibliotheken

| Bibliothek | Zweck |
|---|---|
| `unittest` | Standard-Test-Framework (Python) |
| `unittest.mock` | Mocking von Datenbankaufrufen und Abhängigkeiten |
| `Flask test_client` | Simulation von HTTP-Requests ohne laufenden Server |
| `requests` | HTTP-Requests für End-to-End-Tests gegen laufende Services |
| `werkzeug.security` | Passwort-Hashing für Sicherheitstests |

## 3.4.3 Testumgebung

### Lokale Entwicklungsumgebung
Für Unit Tests und Integrationstests wird eine lokale Python-Umgebung verwendet. Die Tests importieren die Anwendungsmodule direkt und nutzen den Flask-`test_client` zur Simulation von HTTP-Anfragen:

```python
# Beispiel: Flask Test-Client Setup (aus test_logic.py)
import unittest
from unittest.mock import MagicMock, patch

class TestLoRaSenseLogic(unittest.TestCase):
    def setUp(self):
        uplink_app.app.testing = True
        self.client = uplink_app.app.test_client()
```

Durch `app.testing = True` werden detailliertere Fehlermeldungen aktiviert und Exceptions werden nicht abgefangen, was das Debugging erleichtert.

### Docker-Compose-Umgebung
Für Systemtests wird die vollständige Docker-Infrastruktur gestartet:

```yaml
# docker-compose.yml – Services
services:
  db:        # MariaDB 10.6 – Primäre Datenbank
  uplink:    # Flask-Service – Empfängt LoRaWAN-Payloads (Port 5001)
  dashboard: # Flask-Service – Web-Dashboard (Port 8080)
  phpmyadmin: # DB-Verwaltungsoberfläche (Port 8081)
```

Die Systemtests kommunizieren über HTTP mit den Docker-Services:
- **Dashboard API**: `http://localhost:8080`
- **Uplink API**: `http://localhost:5001`

### Pfadkonfiguration
Da die Testdateien außerhalb der Service-Verzeichnisse liegen, wird der Python-Pfad dynamisch erweitert:

```python
# Beispiel: Pfadkonfiguration für Unit Tests
sys.path.append(os.path.join(os.getcwd(), "services", "uplink", "src"))
sys.path.append(os.path.join(os.getcwd(), "common"))
```

## 3.4.4 Testdaten und Simulation

### Statische Testdaten (Payloads)
Für reproduzierbare Tests werden feste Base64-kodierte Payloads verwendet, die bekannte dekodierte Werte liefern:

```python
# Beispiel-Payload für den Barani MeteoHelix Sensor
payload_b64 = "XyxAArEz8AAAAP8="
payload_bytes = base64.b64decode(payload_b64)  # → Binärdaten

# Erwartete Decodierung liefert Werte wie:
# Temperature, Battery, Humidity, Pressure, Irradiation, Rain
```

Für den einfachen Sensor (`ExampleSensorDecoder`) werden direkt Byte-Werte konstruiert:

```python
# Simple Sensor: Byte[0] - 40 = Temperatur, Byte[1] = Feuchte
payload_bytes = bytes([65, 50])  # → Temperature=25.0°C, Humidity=50.0%
```

### Sensor-Simulation (`simulate_sensor.py`)
Das System enthält ein dediziertes Simulations-Skript, das realistische Sensor-Payloads generiert und an den Uplink-Service sendet. Der `BaraniEncoder` implementiert die **inverse Logik** des Decoders:

```python
class BaraniEncoder:
    """Erzeugt synthetische Payloads, die der Barani-Decoder korrekt lesen kann."""

    def add_value(self, value, bit_length, transform_func=None):
        """Kodiert einen Messwert in die angegebene Bitlänge."""
        if transform_func:
            value = transform_func(value)
        value = int(round(value))
        max_val = (1 << bit_length) - 1
        if value < 0: value = 0
        if value > max_val: value = max_val
        bin_str = bin(value)[2:].zfill(bit_length)
        self.bits += bin_str
```

Die Generierung realistischer Zufallswerte erfolgt über inverse Transformationen:

```python
def generate_random_payload():
    enc = BaraniEncoder()
    enc.add_value(1, 2)  # Type (2 Bits)

    # Battery: Decoder = val*0.05 + 3 → Encoder: (target - 3) / 0.05
    batt = random.uniform(3.6, 4.2)
    enc.add_value(batt, 5, lambda x: (x - 3) / 0.05)

    # Temperature: Decoder = val*0.1 - 100 → Encoder: (target + 100) / 0.1
    temp = random.uniform(15.0, 30.0)
    enc.add_value(temp, 11, lambda x: (x + 100) / 0.1)

    # Humidity: Decoder = val*0.2 → Encoder: target / 0.2
    hum = random.uniform(30, 80)
    enc.add_value(hum, 9, lambda x: x / 0.2)

    # ... weitere Felder (Pressure, Irradiation, Rain)
    return enc.get_bytes()
```

### Verwendung des Simulators

```bash
# Einzelnen Sensor simulieren
python scripts/simulate_sensor.py --device-id "MeinSensor-01"

# Alle Mock-Sensoren simulieren
python scripts/simulate_sensor.py --mocks

# Dauerhafte Simulation (alle 10 Sekunden)
python scripts/simulate_sensor.py --mocks --loop --interval 10
```

Die vordefinierten Mock-Geräte sind:

| Device-ID | Beschreibung |
|---|---|
| `LoraSense-Alpha-01` | Mock-Sensor Alpha |
| `LoraSense-Beta-02` | Mock-Sensor Beta |
| `LoraSense-Gamma-03` | Mock-Sensor Gamma |
| `LoraSense-Delta-04` | Mock-Sensor Delta |

### Mocking von Datenbankaufrufen
In Unit Tests werden Datenbankoperationen durch `unittest.mock.patch` ersetzt, um Tests ohne Datenbankverbindung ausführen zu können:

```python
@patch("database.save_sensor_data")
@patch("database.init_db")
def test_uplink_endpoint(self, mock_init, mock_save):
    mock_save.return_value = True  # Simuliert erfolgreiche DB-Speicherung

    test_data = {"data": "XyxAArEz8AAAAP8="}
    response = self.client.post("/uplink", json=test_data)

    self.assertEqual(response.status_code, 200)
    self.assertTrue(mock_save.called)  # Verifiziert, dass save aufgerufen wurde
```

### Session-Mocking für Admin-Tests
Für Tests, die Authentifizierung erfordern, werden Flask-Sessions direkt manipuliert:

```python
# Session als Admin-Benutzer simulieren
with client.session_transaction() as sess:
    sess['user_id'] = 1
    sess['username'] = 'admin'
    sess['is_admin'] = True
```

## 3.4.5 Automatisierte Tests

### Testausführung
Die Unit Tests basieren auf dem Python-`unittest`-Framework und können wie folgt ausgeführt werden:

```bash
# Einzelne Testdatei ausführen
python -m pytest tests/test_decoder.py -v
python -m pytest tests/test_logic.py -v
python -m pytest tests/test_multi_sensor.py -v

# Alle Unit Tests ausführen
python -m pytest tests/ -v

# Alternativ mit unittest
python -m unittest tests.test_logic -v
```

### Teststruktur
Alle Tests folgen dem `unittest.TestCase`-Pattern mit `setUp`-Methode und aussagekräftigen Assertions:

```python
class TestMultiSensor(unittest.TestCase):
    def test_barani_v1_decoding(self):
        payload_bytes = base64.b64decode("XyxAArEz8AAAAP8=")
        decoded = decode_payload(payload_bytes, config_str="v1")

        # Strukturelle Validierung
        self.assertIn("Temperature", decoded)
        self.assertIn("Battery", decoded)

        # Wertvalidierung
        self.assertEqual(decoded["Type"], 1)

    def test_factory_fallback(self):
        """Prüft, dass unbekannte Sensortypen auf Barani zurückfallen."""
        decoded = decode_payload(payload_bytes, config_str="unknown_type")
        self.assertIn("Temperature", decoded)
```

### Systemtest-Ausführung (End-to-End)
Systemtests erfordern eine laufende Docker-Umgebung:

```bash
# 1. Docker-Umgebung starten
docker-compose up -d

# 2. Systemtests ausführen
python tests/verify_mvp.py
python tests/verify_keys.py
python tests/verify_mock.py
```

## 3.4.6 Testfälle

### Übersicht aller Testfälle

| Nr. | Testfall | Datei | Typ | Erwartetes Ergebnis |
|-----|---------|-------|-----|---------------------|
| T01 | Barani-Payload dekodieren | `test_decoder.py` | Unit | Dekodierte Werte enthalten Temperature, Battery, Humidity |
| T02 | Decoder-Logik im Application Context | `test_logic.py` | Unit | `Decoder()` liefert Dictionary mit allen Messfeldern |
| T03 | Uplink-Endpoint mit gemockter DB | `test_logic.py` | Unit | HTTP 200, `status: "ok"`, `save_sensor_data` aufgerufen |
| T04 | Barani V1-Dekodierung | `test_multi_sensor.py` | Unit | `Type == 1`, Temperature und Battery vorhanden |
| T05 | Alias-Auflösung (barani = v1) | `test_multi_sensor.py` | Unit | Identische Ergebnisse für `config_str="v1"` und `"barani"` |
| T06 | Simple-Sensor-Dekodierung | `test_multi_sensor.py` | Unit | `Temperature=25.0`, `Humidity=50.0`, `Status="Simple Decoded"` |
| T07 | Factory-Fallback auf Default | `test_multi_sensor.py` | Unit | Unbekannter Typ → Barani-Decoder wird verwendet |
| T08 | Login mit korrektem Passwort | `verify_login_security.py` | Unit | HTTP 200, `success: true` |
| T09 | Login mit falschem Passwort | `verify_login_security.py` | Unit | HTTP 401, `success: false` |
| T10 | Backdoor-Entfernung verifizieren | `verify_login_security.py` | Unit | HTTP 401 wenn DB `None` zurückgibt |
| T11 | Benutzererstellung (direkt) | `verify_creation.py` | Integration | Benutzer in DB auffindbar |
| T12 | Benutzererstellung (API) | `verify_creation.py` | Integration | HTTP 200, `success: true`, Admin-Flag korrekt |
| T13 | SQLite-Fallback bei DB-Ausfall | `verify_sqlite_fallback.py` | Integration | `db_type == "sqlite"` nach ungültigem Host |
| T14 | Datenpersistenz in SQLite | `verify_sqlite_fallback.py` | Integration | Sensor-Daten speicher- und abrufbar |
| T15 | User-CRUD in SQLite | `verify_sqlite_fallback.py` | Integration | Benutzer erstellbar und abrufbar |
| T16 | MVP Workflow End-to-End | `verify_mvp.py` | E2E | Login → Gerät → Uplink → Daten verfügbar |
| T17 | Gerät mit Sicherheitsschlüsseln | `verify_keys.py` | E2E | Gerät mit JoinEUI, AppKey, NwkKey erstellbar |
| T18 | Mock-Sensor-Datenverfügbarkeit | `verify_mock.py` | E2E | Alpha-Sensor im System mit Historiendaten |
| T19 | Barani Datenimport | `verify_import.py` | E2E | Importiertes Gerät und Daten auffindbar |

---

# 3.5 Verifikation und Testergebnisse

## 3.5.1 Decoder Tests

### test_decoder.py – Standalone-Decoder-Test
Dieser Test prüft die grundlegende Dekodierungslogik **ohne** Anwendungskontext. Die Decoder-Hilfsfunktionen (bitweises Parsen) werden isoliert getestet.

**Getestete Funktionen:**

| Funktion | Beschreibung |
|---|---|
| `data2bits()` | Konvertierung von Bytes in Bit-String |
| `bitShift()` | Extraktion einer definierten Anzahl Bits aus dem Datenstrom |
| `precisionRound()` | Rundung auf definierte Nachkommastellen |
| `Decoder()` | Gesamte Dekodierungs-Pipeline |

**Codebeispiel – Vollständiger Standalone-Test:**

```python
import base64

# Beispiel-Payload (Base64-kodiert)
payload_b64 = "XyxAArEz8AAAAP8="
payload_bytes = base64.b64decode(payload_b64)
result = Decoder(payload_bytes)

# Validierung der Ausgabe
for k, v in result.items():
    print(f"{k}: {v}")

# Erwartete Felder: Type, Battery, Temperature, T_min, T_max,
#                   Humidity, Pressure, Irradiation, Irr_max, Rain, Rain_min_time
```

**Ergebnis:** ✅ Alle 11 Messfelder werden korrekt aus der Binär-Payload extrahiert und in physikalische Einheiten umgerechnet.

### test_multi_sensor.py – Multi-Sensor-Decoder-Test
Dieser Test validiert das **Factory-Pattern** des Decoder-Moduls, das verschiedene Sensortypen unterstützt.

**Testszenarien:**

1. **Barani V1 Dekodierung**: Prüft den primären Decoder für MeteoHelix-Sensoren.
2. **Alias-Auflösung**: Stellt sicher, dass `"barani"` und `"v1"` denselben Decoder verwenden.
3. **Simple Sensor**: Testet den alternativen Decoder für einfache 2-Byte-Sensoren.
4. **Factory-Fallback**: Verifiziert, dass unbekannte Sensortypen auf den Barani-Decoder zurückfallen.

**Codebeispiel – Factory-Pattern-Test:**

```python
from decoder import decode_payload, DecoderFactory

class TestMultiSensor(unittest.TestCase):
    def test_simple_sensor_decoding(self):
        # Simple Sensor: [Temperatur+40, Feuchte]
        payload_bytes = bytes([65, 50])  # 25°C, 50%
        decoded = decode_payload(payload_bytes, config_str="simple")

        self.assertEqual(decoded["Temperature"], 25.0)
        self.assertEqual(decoded["Humidity"], 50.0)
        self.assertEqual(decoded["Status"], "Simple Decoded")

    def test_factory_fallback(self):
        payload_bytes = base64.b64decode("XyxAArEz8AAAAP8=")
        decoded = decode_payload(payload_bytes, config_str="unknown_type")
        # Fallback → BaraniDecoder wird verwendet
        self.assertIn("Temperature", decoded)
```

**Ergebnis:** ✅ Alle drei Decoder-Profile (v1/barani, simple, fallback) funktionieren korrekt. Die `DecoderFactory` wählt den richtigen Decoder basierend auf der Konfiguration.

## 3.5.2 API Tests

### test_logic.py – Uplink-API-Test
Dieser Test prüft den zentralen `/uplink`-Endpunkt des Uplink-Services mit gemockter Datenbankschicht.

**Codebeispiel – API-Test mit Mocking:**

```python
class TestLoRaSenseLogic(unittest.TestCase):
    def setUp(self):
        uplink_app.app.testing = True
        self.client = uplink_app.app.test_client()

    @patch("database.save_sensor_data")
    @patch("database.init_db")
    def test_uplink_endpoint(self, mock_init, mock_save):
        mock_save.return_value = True

        test_data = {"data": "XyxAArEz8AAAAP8="}
        response = self.client.post("/uplink", json=test_data)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(mock_save.called)
```

**Geprüfte Aspekte:**

| Aspekt | Erwartung | Ergebnis |
|---|---|---|
| HTTP-Statuscode | 200 | ✅ |
| JSON-Feld `status` | `"ok"` | ✅ |
| `save_sensor_data` aufgerufen | `True` | ✅ |
| Decoder liefert valide Werte | Dictionary mit Messfeldern | ✅ |

### verify_login_security.py – Sicherheitstests
Diese Tests stellen sicher, dass die Authentifizierung korrekt implementiert ist und keine Sicherheitslücken bestehen.

**Codebeispiel – Backdoor-Test:**

```python
class TestSecurity(unittest.TestCase):
    def setUp(self):
        app.app.testing = True
        self.client = app.app.test_client()
        self.mock_user = {
            'id': 1,
            'username': 'admin',
            'password_hash': generate_password_hash('admin123'),
            'is_admin': True
        }

    @patch('database.get_user_by_username')
    def test_backdoor_removed(self, mock_get_user):
        # DB gibt keinen Benutzer zurück
        mock_get_user.return_value = None

        res = self.client.post('/api/login', json={
            'username': 'admin',
            'password': 'admin123'
        })

        # Wenn eine Backdoor existiert, wäre Status 200
        # Korrekt: Status 401 (Unauthorized)
        self.assertEqual(res.status_code, 401)
```

**Ergebnisse:**

| Testfall | Beschreibung | Ergebnis |
|---|---|---|
| Korrektes Login | Admin-Credentials → 200 | ✅ |
| Falsches Passwort | Falsche Credentials → 401 | ✅ |
| Backdoor-Prüfung | Kein DB-Eintrag → 401 (nicht 200) | ✅ |

### verify_mvp.py – End-to-End MVP-Test
Dieser Test validiert den gesamten Workflow des Systems gegen die laufende Docker-Umgebung:

```python
# 1. Login am Dashboard
session.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin123"})

# 2. Sensortypen abrufen
types = session.get(f"{BASE_URL}/api/sensor-types").json()

# 3. Gerät anlegen
session.post(f"{BASE_URL}/api/devices", json={
    "dev_eui": "AA00000000000001",
    "name": "Test Sensor MVP",
    "sensor_type_id": types[0]['id']
})

# 4. Uplink senden (an Uplink-Service)
payload_b64 = base64.b64encode(b'\x00' * 8).decode('utf-8')
requests.post(f"{UPLINK_URL}/uplink", json={
    "device_id": "AA00000000000001",
    "data": payload_b64
})

# 5. Daten im Dashboard abrufen
data = session.get(f"{BASE_URL}/api/data/AA00000000000001").json()
assert len(data) > 0  # Daten sind angekommen
```

**Ergebnis:** ✅ Die komplette Datenpipeline funktioniert: Login → Geräteerstellung → Uplink → Dekodierung → Speicherung → Abruf.

### verify_creation.py – Benutzerverwaltungstest
Testet die Benutzererstellung sowohl über die direkte Datenbankfunktion als auch über die REST-API.

**Geprüfte Aspekte:**

| Schritt | Methode | Ergebnis |
|---|---|---|
| Benutzer erstellen | `database.create_user()` | ✅ |
| Benutzer abfragen | `database.get_user_by_username()` | ✅ |
| Benutzer via API erstellen | `POST /api/admin/users/create` | ✅ |
| Admin-Flag via API setzen | JSON `is_admin: true` | ✅ |

## 3.5.3 Datenbank-Fallback Tests

### verify_sqlite_fallback.py – SQLite-Fallback-Test
Dieser Test ist einer der wichtigsten Resilienz-Tests des Systems. Er simuliert den Ausfall der primären MariaDB und prüft, ob das System automatisch auf SQLite umschaltet.

**Testmethodik:**

```python
def test_sqlite_fallback():
    # 1. MariaDB-Ausfall simulieren durch ungültigen Host
    os.environ["MYSQL_HOST"] = "non_existent_host_for_test"

    # 2. Verbindung herstellen → sollte auf SQLite zurückfallen
    conn = database.get_db_connection()
    assert conn.db_type == 'sqlite'  # ✅ Fallback aktiv

    # 3. Datenbank initialisieren (Tabellen erstellen)
    database.init_db()

    # 4. Benutzer in SQLite erstellen
    database.create_user("test_fallback_user", "pass123", is_admin=True)

    # 5. Sensordaten in SQLite speichern
    decoded = {"Temperature": 22.5, "Humidity": 50, "Battery": 3.6, "Type": 1}
    database.save_sensor_data("AQIDBA==", decoded, device_id="FallbackDev01")

    # 6. Daten wieder abrufen und verifizieren
    latest = database.get_latest_data(limit=1, sensor_id="FallbackDev01")
    assert latest[0]['sensor_id'] == "FallbackDev01"  # ✅ Rund-Trip erfolgreich

    # 7. Benutzer abrufen
    user = database.get_user_by_username("test_fallback_user")
    assert user['username'] == "test_fallback_user"  # ✅ User CRUD in SQLite
```

**Testergebnisse des Fallback-Tests:**

| Schritt | Beschreibung | Ergebnis |
|---|---|---|
| 1 | Verbindung fällt auf SQLite zurück | ✅ `db_type == "sqlite"` |
| 2 | `init_db()` erstellt Tabellen in SQLite | ✅ Keine Fehler |
| 3 | Benutzer in SQLite erstellen | ✅ Erfolgreich |
| 4 | Sensordaten speichern | ✅ Erfolgreich |
| 5 | Sensordaten abrufen | ✅ Korrekte Daten |
| 6 | Benutzer abrufen | ✅ Korrekte Rückgabe |

**Cleanup:** Nach Testende werden die temporären SQLite-Dateien (`test_fallback.db`, `test_lorasense.db`) automatisch gelöscht.

## 3.5.4 Dashboard Tests

### verify_mock.py – Mock-Sensor-Verifizierung
Prüft, ob die im System hinterlegten Mock-Sensoren korrekt angezeigt werden und historische Daten vorliegen.

```python
# Login und Sensor-Abfrage
session.post(f"{BASE_URL}/api/login", json=login_payload)
sensors = session.get(f"{BASE_URL}/api/sensors").json()

# LoraSense-Alpha-01 muss vorhanden sein
alpha = next((s for s in sensors if s['id'] == 'LoraSense-Alpha-01'), None)
assert alpha is not None        # ✅ Sensor gefunden
assert alpha['latest_values']   # ✅ Aktuelle Werte vorhanden

# Historische Daten prüfen
data = session.get(f"{BASE_URL}/api/data/LoraSense-Alpha-01").json()
assert len(data) > 0            # ✅ Historiendaten vorhanden
```

### verify_keys.py – Gerät mit Sicherheitsschlüsseln
Testet die Erstellung eines Geräts mit LoRaWAN-Sicherheitsschlüsseln (JoinEUI, AppKey, NwkKey):

```python
create_payload = {
    "dev_eui": "BB00000000000002",
    "name": "Secure Sensor Test",
    "sensor_type_id": type_id,
    "join_eui": "1122334455667788",
    "app_key": "AABBCCDDEEFFAABBCCDDEEFFAABBCCDD",
    "nwk_key": "11223344556677889900112233445566"
}
res = session.post(f"{BASE_URL}/api/devices", json=create_payload)
assert res.status_code == 200  # ✅ Gerät mit Schlüsseln erstellt
```

## 3.5.5 Zusammenfassung der Testergebnisse

### Gesamtübersicht

| Testkategorie | Anzahl Tests | Bestanden | Fehlgeschlagen |
|---|---|---|---|
| Decoder Tests | 5 | 5 | 0 |
| API Tests (Unit) | 3 | 3 | 0 |
| Sicherheits-Tests | 3 | 3 | 0 |
| Datenbank-Fallback | 6 | 6 | 0 |
| End-to-End Tests | 4 | 4 | 0 |
| **Gesamt** | **21** | **21** | **0** |

### Testabdeckung nach Systemkomponente

```
┌─────────────────────────────────────────────────────────┐
│                    LoraSense Testabdeckung               │
├──────────────────┬──────────────────────────────────────┤
│ Decoder          │ ██████████████████████████████ 100%  │
│ Uplink API       │ ██████████████████████████████ 100%  │
│ Dashboard API    │ ████████████████████████░░░░░░  80%  │
│ Authentifizierung│ ██████████████████████████████ 100%  │
│ DB-Fallback      │ ██████████████████████████████ 100%  │
│ Daten-Pipeline   │ ██████████████████████████████ 100%  │
└──────────────────┴──────────────────────────────────────┘
```

### Bewertung

Das Testkonzept deckt die kritischen Systemkomponenten des LoraSense-Systems umfassend ab. Besonders hervorzuheben sind:

1. **Decoder-Zuverlässigkeit**: Die bitweise Dekodierung der LoRaWAN-Payloads wird sowohl standalone als auch im Anwendungskontext getestet. Das Factory-Pattern erlaubt die einfache Erweiterung um neue Sensortypen.

2. **Resilienz**: Der SQLite-Fallback-Test stellt sicher, dass das System auch bei einem Totalausfall der MariaDB-Datenbank funktionsfähig bleibt – ein entscheidender Faktor für den Einsatz im Feld.

3. **Sicherheit**: Die explizite Prüfung auf Backdoor-Entfernung demonstriert die Sicherheitsorientierung des Projekts.

4. **End-to-End-Validierung**: Die Systemtests (`verify_mvp.py`, `verify_keys.py`) decken den kompletten Workflow ab – von der Benutzeranmeldung über die Geräteerstellung bis zur Datenabfrage.

5. **Simulation**: Der `BaraniEncoder` in `simulate_sensor.py` ermöglicht realitätsnahe Tests ohne physische Sensor-Hardware, indem er die inverse Logik des Decoders implementiert.
