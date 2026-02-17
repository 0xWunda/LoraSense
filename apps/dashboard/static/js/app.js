/**
 * LoraSense Frontend Application Logic
 * Verwendet Vue 3 (Composition API), Chart.js und Lucide Icons.
 */
const { createApp, ref, onMounted, computed, watch, nextTick, reactive } = Vue;

const app = createApp({
    delimiters: ['[[', ']]'],
    setup() {
        // --- REACTIVE STATE ---

        /** @type {import('vue').Ref<boolean>} Authentifizierungsstatus */
        const isLoggedIn = ref(window.INITIAL_STATE ? window.INITIAL_STATE.isLoggedIn : false);

        /** @type {import('vue').Ref<string>} Aktueller Benutzername */
        const username = ref('User');

        /** @type {import('vue').Ref<boolean>} Gibt an, ob der Benutzer Admin-Rechte hat */
        const isAdmin = ref(false);

        /** @type {import('vue').Ref<string>} Aktive Ansicht (dashboard, detail, history, admin) */
        const currentView = ref('dashboard');

        /** @type {import('vue').Ref<Array>} Liste der verfügbaren Sensoren */
        const sensors = ref([]);

        /** @type {import('vue').Ref<string|null>} ID des aktuell ausgewählten Sensors */
        const selectedSensor = ref(null);

        /** @type {import('vue').Ref<Array>} Historische Daten des ausgewählten Sensors */
        const sensorData = ref([]);

        /** @type {import('vue').Ref<boolean>} Verbindungsstatus zum Backend */
        const isConnected = ref(true);

        /** Login-Formular-Daten */
        const loginForm = ref({ username: '', password: '' });

        /** Fehlermeldung für den Login-Dialog */
        const loginError = ref('');

        /** @type {import('vue').Ref<Array<string>>} Ausgewählte Sensor-IDs für den CSV-Export */
        const selectedSensorIds = ref([]);

        // --- ADMIN & MANAGEMENT STATE ---
        const userList = ref([]);
        const showAdminModal = ref(false);
        const showCreateUserModal = ref(false);
        const createUserForm = reactive({ username: '', password: '', is_admin: false });
        const selectedUser = ref(null);
        const tempPermissions = ref([]);
        const allAvailableSensors = ref([]);

        // --- GERÄTE-MODAL STATE ---
        const showAddDeviceModal = ref(false);
        const showAdvanced = ref(false);
        const sensorTypes = ref([]);
        const newDevice = reactive({
            name: '',
            dev_eui: '',
            sensor_type_id: '',
            join_eui: '',
            app_key: '',
            nwk_key: ''
        });

        /** @type {Object<string, Chart>} Chart.js Instanzen für die Graphen */
        let charts = {};

        /** @type {number|null} ID des Intervall-Timers für Daten-Updates */
        let updateTimer = null;

        // --- COMPUTED PROPERTIES ---
        const allData = ref([]); // Kombinierte Historie für die Tabellenansicht

        /** Titel der aktuellen Ansicht */
        const viewTitle = computed(() => {
            if (currentView.value === 'dashboard') return 'Übersicht';
            if (currentView.value === 'detail') return selectedSensor.value ? selectedSensor.value : 'Details';
            if (currentView.value === 'history') return 'Historie';
            if (currentView.value === 'admin') return 'Verwaltung';
            return '';
        });

        /** Untertitel der aktuellen Ansicht */
        const viewSubtitle = computed(() => {
            if (currentView.value === 'dashboard') return 'Echtzeit-Daten aller Sensoren';
            if (currentView.value === 'detail') return 'Detaillierte Analyse & Graphen';
            if (currentView.value === 'history') return 'Langzeitarchiv & Export';
            if (currentView.value === 'admin') return 'Benutzerzugriffe steuern';
            return '';
        });

        // --- AUTH METHODS ---

        /** 
         * Führt den Login durch. 
         * Sendet Anmeldedaten an das Backend und aktualisiert den App-Status.
         */
        const login = async () => {
            try {
                const res = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(loginForm.value)
                });
                const data = await res.json();
                if (data.success) {
                    checkStatus();
                    fetchSensors();
                } else {
                    loginError.value = data.message || 'Login fehlgeschlagen';
                }
            } catch (e) {
                loginError.value = 'Serverfehler';
            }
        };

        /** Meldet den Benutzer ab und setzt den State zurück. */
        const logout = async () => {
            await fetch('/api/logout');
            isLoggedIn.value = false;
            currentView.value = 'dashboard';
            selectedSensor.value = null;
        };

        /** 
         * Prüft beim Laden der Seite, ob eine aktive Session besteht. 
         * Lädt bei Erfolg die Benutzerdaten und Sensoren.
         */
        const checkStatus = async () => {
            const res = await fetch('/api/status');
            const data = await res.json();
            isLoggedIn.value = data.logged_in;
            if (data.logged_in) {
                username.value = data.username;
                isAdmin.value = data.is_admin;
                fetchSensors();
            }
        };

        /** 
         * Lädt die Liste der Sensoren und deren aktuellste Daten.
         * Berechnet zudem die kombinierte Historie für die Tabellenansicht.
         */
        const fetchSensors = async () => {
            if (!isLoggedIn.value) return;
            try {
                const res = await fetch('/api/sensors');
                if (res.ok) {
                    sensors.value = await res.json();

                    // Historie für alle Sensoren parallel laden (für die 'Historie' Tabelle)
                    const promises = sensors.value.map(s => fetch('/api/data/' + s.id).then(r => r.json()));
                    const results = await Promise.all(promises);

                    // Daten flachklopfen und nach Zeitstempel absteigend sortieren
                    allData.value = results.flat().sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

                    // Liste aller verfügbaren Sensor-IDs für die Admin-Rechteverwaltung sammeln
                    const ids = new Set(sensors.value.map(s => s.id));
                    allAvailableSensors.value = Array.from(ids).sort();
                }
            } catch (e) {
                console.error("Fehler beim Laden der Sensoren", e);
                isConnected.value = false;
            }
        };

        /** 
         * (Backend-Admin) Lädt alle registrierten Benutzer.
         * Nur für Administratoren zugänglich.
         */
        const fetchUsers = async () => {
            if (!isAdmin.value) return;
            try {
                const res = await fetch('/api/admin/users');
                if (!res.ok) return;
                const data = await res.json();
                if (Array.isArray(data)) {
                    userList.value = data;
                }
            } catch (e) {
                console.error("fetchUsers-Fehler:", e);
            }
        };

        /** Öffnet den Dialog zum Erstellen eines neuen Benutzers. */
        const openCreateUserModal = () => {
            createUserForm.username = '';
            createUserForm.password = '';
            createUserForm.is_admin = false;
            showCreateUserModal.value = true;
        };

        /** Schließt den Benutzer-Erstellungs-Dialog. */
        const closeCreateUserModal = () => {
            showCreateUserModal.value = false;
        };

        /** Sendet die Daten für einen neuen Benutzer an die API. */
        const createUser = async () => {
            if (!createUserForm.username || !createUserForm.password) return;
            try {
                const res = await fetch('/api/admin/users/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(createUserForm)
                });

                if (!res.ok) {
                    try {
                        const data = await res.json();
                        alert('Fehler: ' + (data.message || 'Serverfehler'));
                    } catch (e) {
                        alert('Server Fehler (' + res.status + ')');
                    }
                    return;
                }

                const data = await res.json();
                if (data.success) {
                    closeCreateUserModal();
                    fetchUsers(); // Liste aktualisieren
                } else {
                    alert('Fehler: ' + (data.message || 'Konnte Benutzer nicht erstellen'));
                }
            } catch (e) {
                alert('Netzwerkfehler: ' + e.message);
            }
        };

        /** Löscht einen Benutzer nach Bestätigung. */
        const deleteUser = async (user) => {
            if (!confirm(`Möchten Sie den Benutzer "${user.username}" wirklich löschen?`)) return;

            try {
                const res = await fetch(`/api/admin/users/${user.id}`, {
                    method: 'DELETE'
                });

                if (!res.ok) {
                    alert('Löschen fehlgeschlagen (' + res.status + ')');
                    return;
                }

                fetchUsers();
                alert("Benutzer gelöscht!");
            } catch (e) {
                alert('Fehler beim Löschen: ' + e.message);
            }
        };

        /** 
         * Öffnet den Rechte-Verwaltungs-Dialog für einen bestimmten Benutzer.
         * Lädt die aktuell zugewiesenen Sensoren.
         */
        const openPermissionsModal = async (user) => {
            selectedUser.value = user;
            const res = await fetch(`/api/admin/users/${user.id}/sensors`);
            const sensors = await res.json();
            tempPermissions.value = sensors;
            showAdminModal.value = true;
        };

        /** Schließt den Rechte-Dialog. */
        const closeAdminModal = () => {
            showAdminModal.value = false;
            selectedUser.value = null;
            tempPermissions.value = [];
        };

        /** Wechselt eine Sensor-Berechtigung in der temporären Liste (UI-Only). */
        const toggleSensorPermission = (sensorId) => {
            const index = tempPermissions.value.indexOf(sensorId);
            if (index === -1) {
                tempPermissions.value.push(sensorId);
            } else {
                tempPermissions.value.splice(index, 1);
            }
        };

        /** Speichert die geänderten Sensor-Berechtigungen dauerhaft in der DB. */
        const savePermissions = async () => {
            if (!selectedUser.value) return;
            await fetch(`/api/admin/users/${selectedUser.value.id}/sensors`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sensors: tempPermissions.value })
            });
            closeAdminModal();
        };

        /** Lädt die verfügbaren Sensortypen für das Neu-Gerät-Formular. */
        const fetchSensorTypes = async () => {
            try {
                const res = await fetch('/api/sensor-types');
                if (res.ok) {
                    sensorTypes.value = await res.json();
                }
            } catch (e) {
                console.error("Fehler beim Laden der Sensortypen", e);
            }
        };

        /** Öffnet den Dialog zum Hinzufügen eines neuen Sensors. */
        const openAddDeviceModal = async () => {
            await fetchSensorTypes();
            newDevice.name = '';
            newDevice.dev_eui = '';
            newDevice.sensor_type_id = '';
            newDevice.join_eui = '';
            newDevice.app_key = '';
            newDevice.nwk_key = '';
            showAdvanced.value = false;
            // Ersten verfügbaren Typ als Standard wählen
            if (sensorTypes.value.length > 0) newDevice.sensor_type_id = sensorTypes.value[0].id;
            showAddDeviceModal.value = true;
            nextTick(() => lucide.createIcons());
        };

        /** Sendet die neuen Gerätedaten an das Backend. */
        const createDevice = async () => {
            if (!newDevice.name || !newDevice.dev_eui || !newDevice.sensor_type_id) return;
            try {
                const res = await fetch('/api/devices', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(newDevice)
                });

                if (res.ok) {
                    alert("Sensor erfolgreich hinzugefügt!");
                    showAddDeviceModal.value = false;
                    fetchSensors(); // Liste aktualisieren
                } else {
                    const data = await res.json();
                    alert("Fehler: " + (data.message || "Konnte Sensor nicht erstellen"));
                }
            } catch (e) {
                alert("Netzwerkfehler");
            }
        };

        /** 
         * Wählt einen Sensor für die Detailansicht aus und lädt dessen Daten. 
         * @param {string} id - Die DevEUI des Sensors.
         */
        const selectSensor = async (id) => {
            selectedSensor.value = id;
            currentView.value = 'detail';
            await fetchSensorData(id);
            // Warten bis DOM updated, dann Graphen zeichnen
            nextTick(() => {
                renderCharts();
                lucide.createIcons();
            });
        };

        /** 
         * Lädt die historischen Daten für einen bestimmten Sensor.
         * @param {string} id - Die DevEUI des Sensors.
         */
        const fetchSensorData = async (id) => {
            const res = await fetch(`/api/data/${id}`);
            sensorData.value = await res.json();
        };

        /** 
         * Erstellt oder aktualisiert die Chart.js Instanzen für die Detailseite.
         * Nutzt die geladenen Daten aus `sensorData`.
         */
        const renderCharts = () => {
            if (currentView.value !== 'detail') return;

            // Labels für die Zeitachse (HH:mm) extrahieren
            const labels = sensorData.value.map(d => new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })).reverse();
            const dataPoints = sensorData.value.slice().reverse();

            /** 
             * Hilfsfunktion zum Erstellen eines Linien-Diagramms.
             * @param {string} id - Die Canvas-ID.
             * @param {string} label - Name der Datenreihe.
             * @param {Array} data - Die Messwerte.
             * @param {string} color - Die Linienfarbe (Hex).
             */
            const createLineChart = (id, label, data, color) => {
                const ctx = document.getElementById(id);
                if (!ctx) return;

                // Bestehenden Chart zerstören, um Overlays zu vermeiden
                if (charts[id]) charts[id].destroy();

                charts[id] = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: label,
                            data: data,
                            borderColor: color,
                            backgroundColor: color + '20', // Transparente Fläche
                            borderWidth: 2,
                            tension: 0.4, // Smooth Curves
                            fill: true,
                            pointRadius: 0 // Keine Punkte für sauberen Look
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: { grid: { display: false }, ticks: { color: '#94a3b8' } },
                            y: { grid: { color: '#ffffff10' }, ticks: { color: '#94a3b8' } }
                        }
                    }
                });
            };

            // Einzelne Diagramme initialisieren
            createLineChart('tempChart', 'Temperatur (°C)', dataPoints.map(d => d.decoded.Temperature), '#00AEEF');
            createLineChart('humChart', 'Luftfeuchtigkeit (%)', dataPoints.map(d => d.decoded.Humidity), '#005696');
            createLineChart('pressureChart', 'Luftdruck (hPa)', dataPoints.map(d => d.decoded.Pressure), '#10b981');
            createLineChart('batteryChart', 'Batterie (V)', dataPoints.map(d => d.decoded.Battery), '#f59e0b');
            createLineChart('rainChart', 'Regen (mm)', dataPoints.map(d => d.decoded.Rain), '#06b6d4');
            createLineChart('solarChart', 'Einstrahlung (W/m²)', dataPoints.map(d => d.decoded.Irradiation), '#818cf8');
        };

        /** Formatiert einen ISO-Zeitstempel in eine lesbare lokale Darstellung. */
        const formatDateTime = (iso) => {
            return new Date(iso).toLocaleString();
        };

        /** 
         * Startet den CSV-Export für die aktuell ausgewählten Sensoren.
         * Öffnet den generierten Link im Browser.
         */
        const exportSelectedSensors = () => {
            let url = '/api/export';
            if (selectedSensorIds.value.length > 0) {
                const params = selectedSensorIds.value.map(id => `sensor_ids=${encodeURIComponent(id)}`).join('&');
                url = `${url}?${params}`;
            }
            window.location.href = url;
        };

        /** Wählt alle Sensoren für den Export aus. */
        const selectAllSensors = () => {
            selectedSensorIds.value = sensors.value.map(s => s.id);
        };

        /** Hebt die Auswahl aller Sensoren für den Export auf. */
        const clearSensorSelection = () => {
            selectedSensorIds.value = [];
        };

        /** Löscht einen Sensor dauerhaft aus dem System. */
        const deleteSensor = async (sensorId) => {
            if (!confirm(`Möchten Sie den Sensor "${sensorId}" wirklich unwiderruflich löschen? Alle Daten gehen verloren.`)) return;

            try {
                const res = await fetch(`/api/sensors/${sensorId}`, {
                    method: 'DELETE'
                });

                if (!res.ok) {
                    const data = await res.json();
                    alert('Fehler: ' + (data.message || 'Konnte Sensor nicht löschen'));
                    return;
                }

                alert('Sensor gelöscht');
                fetchSensors();
            } catch (e) {
                alert('Netzwerkfehler beim Löschen');
            }
        };

        /** Berechnet die durchschnittliche Temperatur über alle aktiven Sensoren. */
        const avgTemp = computed(() => {
            const valid = sensors.value.filter(s => s.latest_values.Temperature !== undefined);
            if (valid.length === 0) return 0;
            const sum = valid.reduce((acc, s) => acc + s.latest_values.Temperature, 0);
            return (sum / valid.length).toFixed(1);
        });

        // --- LIFECYCLE HOOKS ---
        onMounted(() => {
            // Lucide Icons initialisieren
            lucide.createIcons();
            // Auth-Status prüfen
            checkStatus();
            // Polling für Live-Updates (alle 5 Sekunden)
            updateTimer = setInterval(fetchSensors, 5000);
        });

        // Icons bei Ansichtswechsel neu rendern
        watch(currentView, () => {
            nextTick(() => lucide.createIcons());
        });

        return {
            isLoggedIn, username, isAdmin, currentView, sensors, selectedSensor, sensorData,
            isConnected, loginForm, loginError, login, logout, selectSensor, deleteSensor,
            viewTitle, viewSubtitle, avgTemp, allData, formatDateTime,
            selectedSensorIds, exportSelectedSensors, selectAllSensors, clearSensorSelection,
            userList, showAdminModal, selectedUser, tempPermissions, allAvailableSensors,
            fetchUsers, openPermissionsModal, closeAdminModal, toggleSensorPermission, savePermissions, deleteUser,
            showCreateUserModal, createUserForm, openCreateUserModal, closeCreateUserModal, createUser,
            showAddDeviceModal, sensorTypes, newDevice, openAddDeviceModal, createDevice, showAdvanced
        };
    }
});
app.mount('#app');
