let chartAmbiental;
let chartResiduos;
let chartSonido;
let ultimaImagenTs = null;

function valor(v, sufijo = "") {
    if (v === null || v === undefined || v === "") return "--";
    return `${v}${sufijo}`;
}

function numero(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
}

function limitarPorcentaje(v) {
    const n = numero(v);
    if (n === null) return 0;
    return Math.max(0, Math.min(100, n));
}

function colorClaseNivel(nivel, porcentaje) {
    const p = numero(porcentaje);
    const texto = String(nivel || "").toLowerCase();
    if (texto.includes("alto") || (p !== null && p >= 75)) return "level-high";
    if (texto.includes("medio") || (p !== null && p >= 40)) return "level-mid";
    if (texto.includes("bajo") || (p !== null && p >= 0)) return "level-low";
    return "";
}

function commonChartOptions(maxY = undefined) {
    const y = { ticks: { color: "#94a3b8" }, grid: { color: "rgba(148,163,184,.16)" } };
    if (maxY !== undefined) {
        y.min = 0;
        y.max = maxY;
    }
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { labels: { color: "#e5e7eb", boxWidth: 12 } } },
        scales: {
            x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(148,163,184,.12)" } },
            y
        }
    };
}

function crearGraficos() {
    chartAmbiental = new Chart(document.getElementById("chartAmbiental"), {
        type: "line",
        data: {
            labels: [],
            datasets: [
                { label: "Temperatura °C", data: [], tension: 0.3 },
                { label: "Humedad %", data: [], tension: 0.3 },
                { label: "Presión hPa", data: [], tension: 0.3 }
            ]
        },
        options: commonChartOptions()
    });

    chartResiduos = new Chart(document.getElementById("chartResiduos"), {
        type: "line",
        data: {
            labels: [],
            datasets: [
                { label: "Tacho 1 %", data: [], tension: 0.3 },
                { label: "Tacho 2 %", data: [], tension: 0.3 },
                { label: "Tacho 3 %", data: [], tension: 0.3 },
                { label: "Tacho 4 %", data: [], tension: 0.3 }
            ]
        },
        options: commonChartOptions(100)
    });

    chartSonido = new Chart(document.getElementById("chartSonido"), {
        type: "line",
        data: {
            labels: [],
            datasets: [{ label: "Sonido %", data: [], tension: 0.3 }]
        },
        options: commonChartOptions(100)
    });
}

function actualizarGraficos(historial) {
    const temp = historial.temperatura || [];
    const hum = historial.humedad || [];
    const pres = historial.presion || [];
    const labelsAmbiental = temp.length ? temp.map(p => p.t) : (hum.length ? hum.map(p => p.t) : pres.map(p => p.t));

    chartAmbiental.data.labels = labelsAmbiental;
    chartAmbiental.data.datasets[0].data = temp.map(p => p.v);
    chartAmbiental.data.datasets[1].data = hum.map(p => p.v);
    chartAmbiental.data.datasets[2].data = pres.map(p => p.v);
    chartAmbiental.update();

    const r1 = historial.residuos_1 || [];
    const r2 = historial.residuos_2 || [];
    const r3 = historial.residuos_3 || [];
    const r4 = historial.residuos_4 || [];
    const labelsResiduos = [r1, r2, r3, r4].reduce((a, b) => b.length > a.length ? b : a, []).map(p => p.t);

    chartResiduos.data.labels = labelsResiduos;
    chartResiduos.data.datasets[0].data = r1.map(p => p.v);
    chartResiduos.data.datasets[1].data = r2.map(p => p.v);
    chartResiduos.data.datasets[2].data = r3.map(p => p.v);
    chartResiduos.data.datasets[3].data = r4.map(p => p.v);
    chartResiduos.update();

    const sonido = historial.sonido || [];
    chartSonido.data.labels = sonido.map(p => p.t);
    chartSonido.data.datasets[0].data = sonido.map(p => p.v);
    chartSonido.update();
}

function actualizarTacho(id, tacho) {
    const porcentaje = tacho?.porcentaje_llenado ?? tacho?.nivel_llenado;
    const p = numero(porcentaje);
    const nivel = tacho?.nivel || tacho?.estado || "--";

    document.getElementById(`tacho${id}Porcentaje`).textContent = p === null ? "--" : `${p}%`;
    document.getElementById(`tacho${id}Detalle`).textContent =
        `Distancia: ${tacho?.distancia_cm ?? "--"} cm | Última: ${tacho?.ultima_actualizacion ?? "--"}`;

    const pill = document.getElementById(`tacho${id}NivelTxt`);
    pill.textContent = nivel;
    pill.className = `mini-pill ${colorClaseNivel(nivel, p)}`;

    const bar = document.getElementById(`tacho${id}Bar`);
    bar.style.width = `${limitarPorcentaje(p)}%`;
    bar.className = colorClaseNivel(nivel, p);
}

function actualizarSonido(sonido) {
    const raw = sonido?.value;
    const porcentaje = sonido?.porcentaje;
    const voltaje = sonido?.voltage;
    const nivel = sonido?.nivel;
    const evento = sonido?.evento;

    document.getElementById("sonidoPorcentaje").textContent = porcentaje === undefined || porcentaje === null ? "--" : `${porcentaje}%`;
    document.getElementById("sonidoRaw").textContent = valor(raw);
    document.getElementById("sonidoVoltaje").textContent = voltaje === undefined || voltaje === null ? "--" : `${voltaje} V`;
    document.getElementById("sonidoNivel").textContent = nivel || "--";
    document.getElementById("sonidoEstado").textContent = `Evento: ${evento || "--"}`;

    const bar = document.getElementById("sonidoBar");
    bar.style.width = `${limitarPorcentaje(porcentaje)}%`;
    bar.className = colorClaseNivel(nivel, porcentaje);
}

async function cargarDatos() {
    try {
        const r = await fetch("/api/data");
        if (r.status === 401) {
            const dataError = await r.json();
            window.location.href = dataError.redirect || "/login";
            return;
        }
        const data = await r.json();

        const mqttStatus = document.getElementById("mqttStatus");
        mqttStatus.textContent = `MQTT: ${data.conexion_mqtt}`;
        mqttStatus.className = data.conexion_mqtt === "conectado" ? "pill ok" : "pill fail";

        document.getElementById("lastUpdate").textContent =
            data.ultima_actualizacion ? `Última actualización: ${data.ultima_actualizacion}` : "Esperando datos";

        document.getElementById("deviceId").textContent = data.device_id || "--";
        document.getElementById("ultimoTopico").textContent = data.ultimo_mensaje || "--";

        const status = data.sistema?.status;
        document.getElementById("estadoSistema").textContent =
            typeof status === "object" ? JSON.stringify(status) : (status || "--");

        document.getElementById("temperatura").textContent = valor(data.ambiental.temperatura, "°");
        document.getElementById("humedad").textContent = valor(data.ambiental.humedad, "%");
        document.getElementById("presion").textContent = valor(data.ambiental.presion);

        const gas = data.ambiental.gas;
        if (gas) {
            document.getElementById("gasNivel").textContent = gas.nivel || "--";
            document.getElementById("gasDetalle").textContent =
                `ADC: ${gas.value_raw ?? "--"} | V: ${gas.voltage ?? "--"}`;
        }

        const tachos = data.residuos?.tachos || {};
        [1, 2, 3, 4].forEach(id => actualizarTacho(id, tachos[String(id)]));

        actualizarSonido(data.vigilancia?.sonido);

        const meta = data.vigilancia?.imagen_meta;
        if (meta) {
            document.getElementById("imgMeta").textContent =
                `${meta.width || "--"}x${meta.height || "--"} | ${meta.size_bytes || "--"} bytes | ${meta.trigger || "--"}`;
        }

        if (data.vigilancia?.imagen_timestamp && data.vigilancia.imagen_timestamp !== ultimaImagenTs) {
            ultimaImagenTs = data.vigilancia.imagen_timestamp;
            document.getElementById("cameraImage").src = `/imagen?t=${Date.now()}`;
        }

        const logList = document.getElementById("logList");
        logList.innerHTML = "";
        (data.log || []).forEach(item => {
            const li = document.createElement("li");
            li.textContent = item;
            logList.appendChild(li);
        });

        actualizarGraficos(data.historial || {});

    } catch (e) {
        console.error(e);
    }
}

crearGraficos();
cargarDatos();
setInterval(cargarDatos, 1000);
