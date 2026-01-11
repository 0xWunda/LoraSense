const { createApp, ref, onMounted, computed, watch, nextTick, reactive } = Vue;
const app = createApp({
    delimiters: ['[[', ']]'],
    setup() {
        // STATE
        // Initial state logic injected via global window.INITIAL_STATE
        const isLoggedIn = ref(window.INITIAL_STATE ? window.INITIAL_STATE.isLoggedIn : false);
        const username = ref('User');
        const isAdmin = ref(false);
        const currentView = ref('dashboard'); // dashboard, detail, history, admin
        const sensors = ref([]);
        const selectedSensor = ref(null);
        const sensorData = ref([]);
        const isConnected = ref(true);
        const loginForm = ref({ username: '', password: '' });
        const loginError = ref('');
        const selectedSensorIds = ref([]); // For CSV export station selection

        // Admin State
        const userList = ref([]);
        const showAdminModal = ref(false);
        const showCreateUserModal = ref(false);
        const createUserForm = reactive({ username: '', password: '', is_admin: false });
        const selectedUser = ref(null);
        const tempPermissions = ref([]);
        const allAvailableSensors = ref([]);

        let charts = {};
        let updateTimer = null;

        // COMPUTED
        const allData = ref([]); // For history view

        const viewTitle = computed(() => {
            if (currentView.value === 'dashboard') return 'Übersicht';
            if (currentView.value === 'detail') return selectedSensor.value ? selectedSensor.value : 'Details';
            if (currentView.value === 'history') return 'Historie';
            if (currentView.value === 'admin') return 'Verwaltung';
            return '';
        });

        const viewSubtitle = computed(() => {
            if (currentView.value === 'dashboard') return 'Echtzeit-Daten aller Sensoren';
            if (currentView.value === 'detail') return 'Detaillierte Analyse & Graphen';
            if (currentView.value === 'history') return 'Langzeitarchiv & Export';
            if (currentView.value === 'admin') return 'Benutzerzugriffe steuern';
            return '';
        });

        // METHODS
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
                    // Force refresh sensors
                    fetchSensors();
                } else {
                    loginError.value = data.message || 'Login fehlgeschlagen';
                }
            } catch (e) {
                loginError.value = 'Serverfehler';
            }
        };

        const logout = async () => {
            await fetch('/api/logout');
            isLoggedIn.value = false;
            currentView.value = 'dashboard';
            selectedSensor.value = null;
        };

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

        const fetchSensors = async () => {
            if (!isLoggedIn.value) return;
            try {
                const res = await fetch('/api/sensors');
                if (res.ok) {
                    sensors.value = await res.json();
                    // Fetch history for all sensors for the table
                    const promises = sensors.value.map(s => fetch('/api/data/' + s.id).then(r => r.json()));
                    const results = await Promise.all(promises);
                    allData.value = results.flat().sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

                    // Collect unique sensor IDs for admin selection (from history + current)
                    const ids = new Set(sensors.value.map(s => s.id));
                    // Also add mock sensors if not present (hack for demo)
                    ["LoraSense-Alpha-01", "LoraSense-Beta-02", "LoraSense-Gamma-03", "LoraSense-Delta-04"].forEach(id => ids.add(id));
                    allAvailableSensors.value = Array.from(ids).sort();
                }
            } catch (e) {
                console.error("Error fetching sensors", e);
                isConnected.value = false;
            }
        };

        const fetchUsers = async () => {
            console.log("Fetching users...");
            if (!isAdmin.value) {
                console.warn("fetchUsers called but not admin");
                return;
            }
            try {
                const res = await fetch('/api/admin/users');
                if (!res.ok) {
                    console.error("fetchUsers failed", res.status);
                    return;
                }
                const data = await res.json();
                console.log("Users fetched:", data);
                if (Array.isArray(data)) {
                    userList.value = data;
                } else {
                    console.error("Data is not array:", data);
                }
            } catch (e) {
                console.error("fetchUsers error:", e);
            }
        };

        const openCreateUserModal = () => {
            createUserForm.username = '';
            createUserForm.password = '';
            createUserForm.is_admin = false;
            showCreateUserModal.value = true;
        };

        const closeCreateUserModal = () => {
            showCreateUserModal.value = false;
        };

        const createUser = async () => {
            if (!createUserForm.username || !createUserForm.password) return;
            try {
                const res = await fetch('/api/admin/users/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(createUserForm)
                });

                if (!res.ok) {
                    // Try to parse error message if possible
                    try {
                        const data = await res.json();
                        alert('Fehler: ' + (data.message || 'Serverfehler (' + res.status + ')'));
                    } catch (e) {
                        // If not JSON, it might be a 404 HTML page if the server code isn't updated
                        if (res.status === 404) {
                            alert('Fehler (404): API nicht gefunden. Bitte Server neu starten!');
                        } else {
                            alert('Server Fehler (' + res.status + ')');
                        }
                    }
                    return;
                }

                const data = await res.json();
                if (data.success) {
                    closeCreateUserModal();
                    fetchUsers(); // Refresh list
                } else {
                    alert('Fehler: ' + (data.message || 'Konnte Benutzer nicht erstellen'));
                }
            } catch (e) {
                console.error(e);
                alert('Netzwerkfehler: ' + e.message);
            }
        };

        const deleteUser = async (user) => {
            if (!confirm(`Möchten Sie den Benutzer "${user.username}" wirklich löschen?`)) return;

            try {
                const res = await fetch(`/api/admin/users/${user.id}`, {
                    method: 'DELETE'
                });

                if (!res.ok) {
                    const text = await res.text();
                    let errorMessage = `Fehler: ${res.status} ${res.statusText}`;

                    try {
                        const data = JSON.parse(text);
                        errorMessage = 'Fehler: ' + (data.message || errorMessage);
                    } catch (e) {
                        // Not JSON (likely HTML 404/500), stick to status text
                    }
                    alert(errorMessage);
                    return;
                }

                // Success
                fetchUsers();
                alert("Benutzer gelöscht!");
            } catch (e) {
                console.error(e);
                alert('Fehler beim Löschen: ' + e.message);
            }
        };

        const openPermissionsModal = async (user) => {
            selectedUser.value = user;
            // Fetch permissions
            const res = await fetch(`/api/admin/users/${user.id}/sensors`);
            const sensors = await res.json();
            tempPermissions.value = sensors;
            showAdminModal.value = true;
        };

        const closeAdminModal = () => {
            showAdminModal.value = false;
            selectedUser.value = null;
            tempPermissions.value = [];
        };

        const toggleSensorPermission = (sensorId) => {
            const index = tempPermissions.value.indexOf(sensorId);
            if (index === -1) {
                tempPermissions.value.push(sensorId);
            } else {
                tempPermissions.value.splice(index, 1);
            }
        };

        const savePermissions = async () => {
            if (!selectedUser.value) return;
            await fetch(`/api/admin/users/${selectedUser.value.id}/sensors`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sensors: tempPermissions.value })
            });
            closeAdminModal();
        };

        const selectSensor = async (id) => {
            selectedSensor.value = id;
            currentView.value = 'detail';
            await fetchSensorData(id);
            nextTick(() => {
                renderCharts();
                lucide.createIcons();
            });
        };

        const fetchSensorData = async (id) => {
            const res = await fetch(`/api/data/${id}`);
            sensorData.value = await res.json();
        };

        const renderCharts = () => {
            if (currentView.value !== 'detail') return;

            const ctxIds = ['tempChart', 'humChart', 'pressureChart', 'batteryChart', 'rainChart', 'solarChart'];
            const labels = sensorData.value.map(d => new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })).reverse();
            const dataPoints = sensorData.value.slice().reverse(); // Show oldest to newest left to right? usually chart shows time axis ->

            const createLineChart = (id, label, data, color) => {
                const ctx = document.getElementById(id);
                if (!ctx) return;
                if (charts[id]) charts[id].destroy();

                charts[id] = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: label,
                            data: data,
                            borderColor: color,
                            backgroundColor: color + '20',
                            borderWidth: 2,
                            tension: 0.4,
                            fill: true,
                            pointRadius: 0
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } }, // Minimal look
                        scales: {
                            x: { grid: { display: false }, ticks: { color: '#94a3b8' } },
                            y: { grid: { color: '#ffffff10' }, ticks: { color: '#94a3b8' } }
                        }
                    }
                });
            };

            createLineChart('tempChart', 'Temperatur (°C)', dataPoints.map(d => d.decoded.Temperature), '#00AEEF');
            createLineChart('humChart', 'Luftfeuchtigkeit (%)', dataPoints.map(d => d.decoded.Humidity), '#005696');
            createLineChart('pressureChart', 'Luftdruck (hPa)', dataPoints.map(d => d.decoded.Pressure), '#10b981');
            createLineChart('batteryChart', 'Batterie (V)', dataPoints.map(d => d.decoded.Battery), '#f59e0b');
            createLineChart('rainChart', 'Regen (mm)', dataPoints.map(d => d.decoded.Rain), '#06b6d4');
            createLineChart('solarChart', 'Einstrahlung (W/m²)', dataPoints.map(d => d.decoded.Irradiation), '#818cf8');
        };

        const formatDateTime = (iso) => {
            return new Date(iso).toLocaleString();
        };

        const exportSelectedSensors = () => {
            let url = '/api/export';
            if (selectedSensorIds.value.length > 0) {
                const params = selectedSensorIds.value.map(id => `sensor_ids=${encodeURIComponent(id)}`).join('&');
                url = `${url}?${params}`;
            }
            window.location.href = url;
        };

        const selectAllSensors = () => {
            selectedSensorIds.value = sensors.value.map(s => s.id);
        };

        const clearSensorSelection = () => {
            selectedSensorIds.value = [];
        };

        const avgTemp = computed(() => {
            const valid = sensors.value.filter(s => s.latest_values.Temperature !== undefined);
            if (valid.length === 0) return 0;
            const sum = valid.reduce((acc, s) => acc + s.latest_values.Temperature, 0);
            return (sum / valid.length).toFixed(1);
        });

        // LIFECYCLE
        onMounted(() => {
            lucide.createIcons();
            checkStatus();
            updateTimer = setInterval(fetchSensors, 5000);
        });

        watch(currentView, () => {
            nextTick(() => lucide.createIcons());
        });

        return {
            isLoggedIn, username, isAdmin, currentView, sensors, selectedSensor, sensorData,
            isConnected, loginForm, loginError, login, logout, selectSensor,
            viewTitle, viewSubtitle, avgTemp, allData, formatDateTime,
            // Export functionality
            selectedSensorIds, exportSelectedSensors, selectAllSensors, clearSensorSelection,
            // Admin exports
            userList, showAdminModal, selectedUser, tempPermissions, allAvailableSensors,
            fetchUsers, openPermissionsModal, closeAdminModal, toggleSensorPermission, savePermissions, deleteUser,
            // Create User exports
            showCreateUserModal, createUserForm, openCreateUserModal, closeCreateUserModal, createUser
        };
    }
});
app.mount('#app');
