let chartAmbiental;
let chartResiduos;
let chartSonido;
let camStreamUrlActual = "http://10.101.53.9/stream";

/* â”€â”€ Estado de nodo por tiempo â”€â”€ */
// Devuelve true si el dispositivo enviÃ³ un mensaje hace menos de maxSeg segundos
function nodoOnline(ultima_vez, deviceId, maxSeg) {
    const ts = ultima_vez?.[deviceId];
    if (!ts) return false;
    return (Date.now() / 1000 - ts) < maxSeg;
}

/* â”€â”€ Utilidades â”€â”€ */
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
    const p   = numero(porcentaje);
    const txt = String(nivel || "").toLowerCase();
    if (txt.includes("alto")  || (p !== null && p >= 75)) return "level-high";
    if (txt.includes("medio") || (p !== null && p >= 40)) return "level-mid";
    if (txt.includes("bajo")  || (p !== null && p >= 0))  return "level-low";
    return "";
}

function flashUpdate(el) {
    if (!el) return;
    el.classList.add("updating");
    setTimeout(() => el.classList.remove("updating"), 600);
}

/* â”€â”€ GrÃ¡ficos â”€â”€ */
function commonChartOptions(maxY) {
    const y = {
        ticks: { color: "#64748b" },
        grid:  { color: "rgba(148,163,184,.14)" }
    };
    if (maxY !== undefined) { y.min = 0; y.max = maxY; }
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 400 },
        plugins: { legend: { labels: { color: "#94a3b8", boxWidth: 12 } } },
        scales: {
            x: { ticks: { color: "#64748b" }, grid: { color: "rgba(148,163,184,.10)" } },
            y
        }
    };
}

function crearGraficos() {
    if (typeof Chart === "undefined") return;

    const canvasAmbiental = document.getElementById("chartAmbiental");
    if (canvasAmbiental) chartAmbiental = new Chart(canvasAmbiental, {
        type: "line",
        data: {
            labels: [],
            datasets: [
                { label: "Temperatura Â°C", data: [], tension: 0.4, borderWidth: 2, pointRadius: 2 },
                { label: "Humedad %",      data: [], tension: 0.4, borderWidth: 2, pointRadius: 2 },
                { label: "PresiÃ³n hPa",    data: [], tension: 0.4, borderWidth: 2, pointRadius: 2 }
            ]
        },
        options: commonChartOptions()
    });

    const canvasResiduos = document.getElementById("chartResiduos");
    if (canvasResiduos) chartResiduos = new Chart(canvasResiduos, {
        type: "line",
        data: {
            labels: [],
            datasets: [
                { label: "Tacho A %", data: [], tension: 0.4, borderWidth: 2, pointRadius: 2 },
                { label: "Tacho B %", data: [], tension: 0.4, borderWidth: 2, pointRadius: 2 },
                { label: "Tacho C %", data: [], tension: 0.4, borderWidth: 2, pointRadius: 2 },
                { label: "Tacho D %", data: [], tension: 0.4, borderWidth: 2, pointRadius: 2 }
            ]
        },
        options: commonChartOptions(100)
    });

    const canvasSonido = document.getElementById("chartSonido");
    if (canvasSonido) chartSonido = new Chart(canvasSonido, {
        type: "line",
        data: {
            labels: [],
            datasets: [{ label: "Sonido %", data: [], tension: 0.4, borderWidth: 2, pointRadius: 2 }]
        },
        options: commonChartOptions(100)
    });
}

function actualizarGraficos(historial) {
    const temp = historial.temperatura || [];
    const hum  = historial.humedad    || [];
    const pres = historial.presion    || [];
    const labels = temp.length ? temp.map(p => p.t)
                 : hum.length  ? hum.map(p => p.t)
                 : pres.map(p => p.t);

    if (chartAmbiental) {
        chartAmbiental.data.labels = labels;
        chartAmbiental.data.datasets[0].data = temp.map(p => p.v);
        chartAmbiental.data.datasets[1].data = hum.map(p => p.v);
        chartAmbiental.data.datasets[2].data = pres.map(p => p.v);
        chartAmbiental.update();
    }

    const r = [1,2,3,4].map(i => historial[`residuos_${i}`] || []);
    const rLabels = r.reduce((a,b) => b.length > a.length ? b : a, []).map(p => p.t);
    if (chartResiduos) {
        chartResiduos.data.labels = rLabels;
        r.forEach((arr, i) => { chartResiduos.data.datasets[i].data = arr.map(p => p.v); });
        chartResiduos.update();
    }

    const s = historial.sonido || [];
    if (chartSonido) {
        chartSonido.data.labels = s.map(p => p.t);
        chartSonido.data.datasets[0].data = s.map(p => p.v);
        chartSonido.update();
    }
}

/* â”€â”€ Nodo ambiental â”€â”€ */
function actualizarNodoAmbiental(data) {
    const temp = data.ambiental?.temperatura;
    const hum  = data.ambiental?.humedad;
    const pres = data.ambiental?.presion;
    const gas  = data.ambiental?.gas;

    // Online = mensajes recibidos en los Ãºltimos 60 s
    const online = nodoOnline(data.ultima_vez_modulos, "ESP32_AIRE_01", 60);

    const dht22  = online && temp !== null && temp !== undefined && temp !== -1;
    const bmp280 = online && pres !== null && pres !== undefined && pres !== -1;
    const mq2    = online && gas  !== null && gas  !== undefined;
    const activos = online ? [dht22, bmp280, mq2].filter(Boolean).length : 0;

    const setChip = (id, ok) => {
        const el = document.getElementById(id);
        if (el) el.className = `sensor-chip ${ok ? "online" : "offline"}`;
    };
    setChip("chipDHT22",  dht22);
    setChip("chipBMP280", bmp280);
    setChip("chipMQ2",    mq2);

    const sensEl = document.getElementById("ambSensoresActivos");
    if (sensEl) sensEl.textContent = `${activos} / 3`;

    const dot = document.getElementById("ambientalNodeDot");
    if (dot) dot.className = `node-dot ${online ? "online" : "offline"}`;

    // Hora de la ÃšLTIMA LECTURA del nodo ambiental (no del sistema global)
    const lastEl = document.getElementById("ambLastSeen");
    if (lastEl) {
        const ts = data.ultima_vez_modulos?.["ESP32_AIRE_01"];
        lastEl.textContent = ts ? new Date(ts * 1000).toLocaleTimeString("es-PE") : "--";
    }

    // Badge de calidad
    const nivel = (online && gas?.nivel) || "";
    const badge = document.getElementById("airQualityBadge");
    if (badge) {
        if (!online)                     { badge.textContent = "Sin conexiÃ³n";     badge.className = "quality-badge"; }
        else if (nivel === "elevado")    { badge.textContent = "Calidad crÃ­tica";  badge.className = "quality-badge bad"; }
        else if (nivel === "preventivo") { badge.textContent = "Calidad moderada"; badge.className = "quality-badge warn"; }
        else if (mq2)                   { badge.textContent = "Calidad buena";    badge.className = "quality-badge good"; }
        else                            { badge.textContent = "--";               badge.className = "quality-badge"; }
    }

    // Barras de las mÃ©tricas
    const setBar = (id, pct, cls) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.style.width = `${pct}%`;
        if (cls) el.className = `bar-fill ${cls}`;
    };

    if (!online) {
        // Offline â†’ limpiar barras
        ["temperaturaBar","humedadBar","presionBar","gasBar"].forEach(id => setBar(id, 0, "bar-ok"));
        return;
    }

    const tempVal  = numero(temp);
    const tempPct  = tempVal !== null ? limitarPorcentaje((tempVal / 50) * 100) : 0;
    const tempCls  = tempPct > 80 ? "bar-danger" : tempPct > 55 ? "bar-warn" : "bar-ok";
    setBar("temperaturaBar", tempPct, tempCls);

    const humPct = limitarPorcentaje(numero(hum));
    setBar("humedadBar", humPct, humPct > 80 ? "bar-warn" : "bar-ok");

    // PresiÃ³n: normalizar entre 900-1100 hPa â†’ 0-100%
    const presVal = numero(pres);
    const presPct = presVal !== null ? limitarPorcentaje(((presVal - 900) / 200) * 100) : 0;
    setBar("presionBar", presPct, "bar-neutral");

    const gasVolt = numero(gas?.voltage);
    const gasPct  = gasVolt !== null ? limitarPorcentaje((gasVolt / 3.3) * 100) : 0;
    const gasCls  = nivel === "elevado" ? "bar-danger" : nivel === "preventivo" ? "bar-warn" : "bar-ok";
    setBar("gasBar", gasPct, gasCls);
}

/* â”€â”€ Resumen de residuos â”€â”€ */
function actualizarResumenResiduos(data) {
    const tachos = data.residuos?.tachos || {};
    const online = nodoOnline(data.ultima_vez_modulos, "ESP32_RESIDUOS_01", 60);
    let activos = 0, sumaFill = 0, alerta = 0, count = 0;
    // Sensores 1-4 del módulo de residuos
    if (online) {
        [1,2,3,4].forEach(id => {
            const t = tachos[String(id)];
            if (t && t.porcentaje_llenado !== null && t.porcentaje_llenado !== undefined) {
                activos++;
                sumaFill += t.porcentaje_llenado;
                count++;
                if (t.porcentaje_llenado >= 80) alerta++;
            }
        });
    }

    const dot = document.getElementById("residuosNodeDot");
    if (dot) dot.className = `node-dot ${online ? "online" : "offline"}`;

    const sensEl = document.getElementById("resSensoresActivos");
    if (sensEl) sensEl.textContent = `${activos} / 4`;

    const promedio = count > 0 ? Math.round(sumaFill / count) : null;
    const promEl = document.getElementById("resPromedio");
    if (promEl) {
        promEl.textContent = promedio !== null ? `${promedio}%` : "--%";
        promEl.className   = `ro-value ${promedio >= 80 ? "ro-danger" : promedio >= 50 ? "ro-warn" : "ro-ok"}`;
    }

    const alertEl = document.getElementById("resAlerta");
    if (alertEl) {
        alertEl.textContent = alerta;
        alertEl.className   = `ro-value ${alerta > 0 ? "ro-danger" : "ro-ok"}`;
    }
}

/* â”€â”€ Nodo sonido â”€â”€ */
function actualizarNodoSonido(data) {
    // KY037 envÃ­a cada 3 s â€” si no hay mensajes en 30 s, estÃ¡ offline
    const online = nodoOnline(data.ultima_vez_modulos, "ESP32_KY037_01", 30);
    const dot = document.getElementById("sonidoNodeDot");
    if (dot) dot.className = `node-dot ${online ? "online" : "offline"}`;
}

/* â”€â”€ Tacho â”€â”€ */
function actualizarTacho(id, tacho) {
    const porcentaje = tacho?.porcentaje_llenado ?? tacho?.nivel_llenado;
    const p     = numero(porcentaje);
    const nivel = tacho?.nivel || tacho?.estado || "--";
    const cls   = colorClaseNivel(nivel, p);

    const pctEl = document.getElementById(`tacho${id}Porcentaje`);
    if (pctEl) { flashUpdate(pctEl); pctEl.textContent = p === null ? "--" : `${p}%`; }

    const detEl = document.getElementById(`tacho${id}Detalle`);
    if (detEl) detEl.textContent =
        `Distancia: ${tacho?.distancia_cm ?? "--"} cm Â· Ãšltima: ${tacho?.ultima_actualizacion ?? "--"}`;

    const pill = document.getElementById(`tacho${id}NivelTxt`);
    if (pill) { pill.textContent = nivel; pill.className = `mini-pill ${cls}`; }

    // Barra horizontal
    const bar = document.getElementById(`tacho${id}Bar`);
    if (bar) { bar.style.width = `${limitarPorcentaje(p)}%`; bar.className = cls; }

    // Barra vertical (visual de llenado)
    const fill = document.getElementById(`tacho${id}Fill`);
    if (fill) { fill.style.height = `${limitarPorcentaje(p)}%`; fill.className = `tc-fill-bar ${cls}`; }

    // Card borde de alerta
    const card = document.getElementById(`tachoCard${id}`);
    if (card) card.className = `trash-card ${cls}`;
}

/* â”€â”€ Sonido â”€â”€ */
function actualizarSonido(sonido) {
    const raw       = sonido?.value;
    const porcentaje= sonido?.porcentaje;
    const voltaje   = sonido?.voltage;
    const nivel     = sonido?.nivel;
    const evento    = sonido?.evento;

    const pctEl = document.getElementById("sonidoPorcentaje");
    if (pctEl) { flashUpdate(pctEl); pctEl.textContent = porcentaje == null ? "--" : `${porcentaje}%`; }

    const rawEl = document.getElementById("sonidoRaw");
    if (rawEl) rawEl.textContent = valor(raw);

    const vEl = document.getElementById("sonidoVoltaje");
    if (vEl) vEl.textContent = voltaje == null ? "--" : `${voltaje} V`;

    const nEl = document.getElementById("sonidoNivel");
    if (nEl) nEl.textContent = nivel || "--";

    const eEl = document.getElementById("sonidoEstado");
    if (eEl) eEl.textContent = `Evento: ${evento || "--"}`;

    const bar = document.getElementById("sonidoBar");
    if (bar) {
        bar.style.width = `${limitarPorcentaje(porcentaje)}%`;
        bar.className   = `bar-fill ${colorClaseNivel(nivel, porcentaje)}`;
    }
}

/* â”€â”€ Fetch principal â”€â”€ */
async function cargarDatos() {
    try {
        const r = await fetch("/api/data");
        if (r.status === 401) {
            const e = await r.json();
            window.location.href = e.redirect || "/login";
            return;
        }
        const data = await r.json();

        // MQTT status
        const mqttEl = document.getElementById("mqttStatus");
        if (mqttEl) {
            mqttEl.textContent = `MQTT: ${data.conexion_mqtt}`;
            mqttEl.className   = data.conexion_mqtt === "conectado" ? "pill ok" : "pill bad";
        }
        const luEl = document.getElementById("lastUpdate");
        if (luEl) luEl.textContent = data.ultima_actualizacion
            ? `Actualizado: ${data.ultima_actualizacion}` : "Esperando datos";

        // MÃ©tricas ambientales â€” solo mostrar si el nodo estÃ¡ activo
        const ambOnline = nodoOnline(data.ultima_vez_modulos, "ESP32_AIRE_01", 60);

        const tempEl = document.getElementById("temperatura");
        if (tempEl) { flashUpdate(tempEl); tempEl.textContent = ambOnline ? valor(data.ambiental.temperatura, "Â°") : "--"; }

        const humEl = document.getElementById("humedad");
        if (humEl) { flashUpdate(humEl); humEl.textContent = ambOnline ? valor(data.ambiental.humedad, "%") : "--"; }

        const presEl = document.getElementById("presion");
        if (presEl) { flashUpdate(presEl); presEl.textContent = ambOnline ? valor(data.ambiental.presion) : "--"; }

        const gas = data.ambiental.gas;
        const gNivelEl = document.getElementById("gasNivel");
        const gDetEl   = document.getElementById("gasDetalle");
        if (ambOnline && gas) {
            if (gNivelEl) { flashUpdate(gNivelEl); gNivelEl.textContent = gas.nivel || "--"; }
            if (gDetEl)   gDetEl.textContent = `ADC: ${gas.value_raw ?? "--"} Â· V: ${gas.voltage ?? "--"}`;
        } else {
            if (gNivelEl) gNivelEl.textContent = "--";
            if (gDetEl)   gDetEl.textContent   = "ADC: -- Â· V: --";
        }

        // Nodo ambiental + barras
        actualizarNodoAmbiental(data);
        // Tachos 1-4; si el nodo está offline se muestra sin datos
        const tachos = data.residuos?.tachos || {};
        const resOnline = nodoOnline(data.ultima_vez_modulos, "ESP32_RESIDUOS_01", 60);
        [1,2,3,4].forEach(id => actualizarTacho(id, resOnline ? tachos[String(id)] : null));
        actualizarResumenResiduos(data);

        // Sonido
        actualizarSonido(data.vigilancia?.sonido);
        actualizarNodoSonido(data);

        // CÃ¡mara stream
        // Online = la cÃ¡mara enviÃ³ heartbeat en los Ãºltimos 120 s (heartbeat cada 30 s)
        const camOnline = nodoOnline(data.ultima_vez_modulos, "ESP32_CAM_01", 120);
        const livePill  = document.getElementById("camLivePill");
        const camImg    = document.getElementById("cameraImage");
        const streamUrl = data.vigilancia?.cam_stream_url;

        if (streamUrl && streamUrl !== camStreamUrlActual) {
            camStreamUrlActual = streamUrl;
            if (camImg) camImg.src = streamUrl;
        }

        const metaEl = document.getElementById("imgMeta");
        if (camOnline) {
            if (metaEl) metaEl.textContent = `Stream: ${camStreamUrlActual}`;
            if (livePill) { livePill.textContent = "â— En vivo"; livePill.className = "pill ok"; }
        } else {
            if (metaEl) metaEl.textContent = "CÃ¡mara desconectada";
            if (livePill) { livePill.textContent = "Sin seÃ±al"; livePill.className = "pill bad"; }
        }

        // Log
        const logList = document.getElementById("logList");
        if (logList) {
            logList.innerHTML = "";
            (data.log || []).forEach(item => {
                const li = document.createElement("li");
                li.textContent = item;
                logList.appendChild(li);
            });
        }

        actualizarGraficos(data.historial || {});

    } catch (e) {
        console.error("Error cargando datos:", e);
    }
}

crearGraficos();
cargarDatos();
setInterval(cargarDatos, 500);
