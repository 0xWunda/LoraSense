# 3.3 Frontend-Realisierung

## 3.3.1 Architektur des Dashboards

Das LoraSense Dashboard ist als moderne **Single Page Application (SPA)** konzipiert. Dies ermöglicht eine flüssige Benutzererfahrung, da Inhalte dynamisch nachgeladen werden, ohne dass die gesamte Seite im Browser neu aufgebaut werden muss.

### Technologiestack
Die Realisierung basiert auf etablierten Web-Technologien:

*   **Vue.js 3 (Composition API):** Dient als reaktives Frontend-Framework zur Steuerung der UI-Logik und des Zustandsmanagements.
*   **Tailwind CSS:** Ein Utility-First CSS-Framework für das Styling. Es wird insbesondere für das "Glassmorphism"-Design (transparente, weichgezeichnete Oberflächen) verwendet.
*   **Chart.js:** Eine leistungsstarke Bibliothek zur Visualisierung der Sensordaten in Form von Liniendiagrammen.
*   **Lucide Icons:** Ein Set von konsistenten Open-Source-Icons für die Benutzeroberfläche.
*   **Flask (Backend-Integration):** Das Python-Backend liefert die statischen Dateien aus und stellt die Daten über eine REST-API bereit.

### Datei-Struktur
Die Frontend-Dateien sind im Verzeichnis `apps/dashboard/static/` organisiert:

*   `index.html`: Das Haupt-Template, das das Grundgerüst der Anwendung sowie die Navigation enthält.
*   `js/app.js`: Enthält die gesamte Vue-Logik, das Zustandsmanagement und die API-Kommunikation.
*   `css/styles.css`: Ergänzende CSS-Regeln für Animationen und spezielle Design-Effekte.
*   `partials/`: Enthält modulare HTML-Fragmente (z.B. `dashboard.html`, `detail.html`, `admin.html`), die via Jinja2 in die Hauptseite eingebunden werden.

## 3.3.2 Zustands- und Komponentenlogik

Die gesamte Logik des Frontends ist in einer zentralen Vue-Instanz in `app.js` gekapselt. Hierbei wird die **Composition API** genutzt, um den Zustand (State) und die Funktionen übersichtlich zu gruppieren.

### Zentraler State (Reaktive Variablen)
Wichtige Zustandsvariablen sind:

```javascript
const isLoggedIn = ref(false);      // Authentifizierungsstatus
const currentView = ref('dashboard'); // Aktuelle Ansicht (Routing-Ersatz)
const sensors = ref([]);             // Liste der verfügbaren Sensoren
const selectedSensor = ref(null);    // ID des aktiven Sensors in der Detailansicht
const isAdmin = ref(false);          // Berechtigungsstufe des Benutzers
```

### Lifecycle & Updates
Beim Laden der Anwendung (`onMounted`) werden folgende Schritte ausgeführt:
1.  **Status-Check:** Prüfung der bestehenden Session beim Backend.
2.  **Initialisierung:** Laden der Lucide-Icons.
3.  **Daten-Polling:** Start eines Intervall-Timers, der alle 5 Sekunden die aktuellsten Sensordaten vom Server abruft (`setInterval(fetchSensors, 5000)`).

### Ansichten-Steuerung (View Switcher)
Da es sich um eine SPA handelt, steuert die Variable `currentView` über `v-if` Direktiven in der `index.html`, welcher Bereich (Dashboard, Details, Historie oder Verwaltung) gerade sichtbar ist. Ein Wechsel der Ansicht löst automatisch eine Aktualisierung der Icons und ggf. ein Neuzeichnen der Graphen aus.

## 3.3.3 API-Kommunikation

Die Kommunikation zwischen Frontend und Backend erfolgt ausschließlich asynchron über die **Fetch API**.

### Kommunikations-Muster
Alle API-Zugriffe sind als `async/await` Funktionen implementiert. Beispiel für den Abruf der Sensordaten:

```javascript
const fetchSensors = async () => {
    if (!isLoggedIn.value) return;
    try {
        const res = await fetch('/api/sensors');
        if (res.ok) {
            sensors.value = await res.json();
        }
    } catch (e) {
        isConnected.value = false; // Visuelle Anzeige bei Verbindungsverlust
    }
};
```

### Wichtige Endpunkte
*   `POST /api/login`: Authentifizierung gegen das Backend.
*   `GET /api/sensors`: Liefert eine Liste aller für den Benutzer freigeschalteten Sensoren inklusive der letzten Messwerte.
*   `GET /api/data/<id>`: Liefert die historische Zeitreihe für einen spezifischen Sensor.
*   `POST /api/devices`: Registrierung eines neuen LoRaWAN-Geräts.
*   `GET /api/export`: Initiiert den Download der Sensordaten als CSV.

## 3.3.4 Visualisierung der Sensordaten

Die visuelle Aufbereitung der Messwerte ist ein Kernaspekt des Dashboards. Hierbei kommen zwei Ansätze zum Einsatz:

### 1. Echtzeit-Karten (Dashboard-Grid)
In der Hauptübersicht wird für jeden Sensor eine "Karte" angezeigt. Diese nutzt Vue-Bindings, um Werte wie Temperatur, Luftfeuchtigkeit und Batteriestand sofort zu aktualisieren, sobald neue Daten per Polling eintreffen.

### 2. Historische Analyse (Chart.js)
In der Detailansicht werden die Daten der letzten 100 Datenpunkte visualisiert. Die Funktion `renderCharts()` in `app.js` übernimmt die Initialisierung der Canvas-Elemente:

```javascript
const createLineChart = (id, label, data, color) => {
    const ctx = document.getElementById(id);
    if (charts[id]) charts[id].destroy(); // Alten Chart entfernen

    charts[id] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [{
                label: label,
                data: data,
                borderColor: color,
                tension: 0.4, // Erzeugt weiche Kurven
                fill: true    // Fläche unter der Kurve füllen
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            // ... weitere Design-Optionen
        }
    });
};
```
Es werden separate Diagramme für alle verfügbaren Messgrößen (Temperatur, Feuchtigkeit, Druck, Solar, Regen, Batterie) erzeugt.

## 3.3.5 Benutzer- und Rollenlogik

Das System verfügt über ein integriertes Rollen- und Rechtemanagement, das sowohl im Frontend als auch im Backend (validierend) implementiert ist.

### Rollentrennung
*   **Standard-User:** Kann Dashboard-Daten sehen, Exporte durchführen und Details ansehen. Er sieht jedoch nur die Sensoren, die ihm explizit zugewiesen wurden.
*   **Administrator:** Hat vollen Zugriff auf alle Sensoren, kann neue Geräte anlegen, Benutzer verwalten und Berechtigungen vergeben.

### Access Control List (ACL)
Die Sichtbarkeit der Sensoren wird über eine ACL gesteuert. Im Frontend wird dies durch die `isAdmin`-Variable und die vom Backend gefilterte Sensorliste umgesetzt:

```html
<!-- Beispiel aus der Sidebar: Verwaltung nur für Admins sichtbar -->
<a v-if="isAdmin" @click="currentView = 'admin'">
    <i data-lucide="users"></i> Verwaltung
</a>
```

### Verwaltungs-Interface
Admins können über die "Verwaltung"-Ansicht:
1.  **Benutzer-Management:** Neue Accounts anlegen oder bestehende löschen.
2.  **Rechte-Zuweisung:** Über ein Modal-Fenster pro Benutzer auswählen, welche Sensoren (DevEUIs) dieser in seinem Dashboard sehen darf. Diese Daten werden über den Endpunkt `/api/admin/users/<id>/sensors` synchronisiert.
