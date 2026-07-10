let chartAmbiental;
let chartResiduos;
let chartSonido;
let camStreamUrlActual = "http://192.168.1.20:81/stream";

/* ── Estado de nodo por tiempo ── */
// Devuelve true si el dispositivo envió un mensaje hace menos de maxSeg segundos
function nodoOnline(ultima_vez, deviceId, maxSeg) {
    const ts = ultima_vez?.[deviceId];
    if (!ts) return false;
    return (Date.now() / 1000 - ts) < maxSeg;
}

/* ── Utilidades ── */
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

/* ── Gráficos ── */
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
                { label: "Temperatura °C", data: [], tension: 0.4, borderWidth: 2, pointRadius: 2 },
                { label: "Humedad %",      data: [], tension: 0.4, borderWidth: 2, pointRadius: 2 },
                { label: "Presión hPa",    data: [], tension: 0.4, borderWidth: 2, pointRadius: 2 }
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

/* ── Nodo ambiental ── */
function actualizarNodoAmbiental(data) {
    const temp = data.ambiental?.temperatura;
    const hum  = data.ambiental?.humedad;
    const pres = data.ambiental?.presion;
    const gas  = data.ambiental?.gas;

    // Online = mensajes recibidos en los últimos 60 s
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

    // Hora de la ÚLTIMA LECTURA del nodo ambiental (no del sistema global)
    const lastEl = document.getElementById("ambLastSeen");
    if (lastEl) {
        const ts = data.ultima_vez_modulos?.["ESP32_AIRE_01"];
        lastEl.textContent = ts ? new Date(ts * 1000).toLocaleTimeString("es-PE") : "--";
    }

    // Badge de calidad
    const nivel = (online && gas?.nivel) || "";
    const badge = document.getElementById("airQualityBadge");
    if (badge) {
        if (!online)                     { badge.textContent = "Sin conexión";     badge.className = "quality-badge"; }
        else if (nivel === "elevado")    { badge.textContent = "Calidad crítica";  badge.className = "quality-badge bad"; }
        else if (nivel === "preventivo") { badge.textContent = "Calidad moderada"; badge.className = "quality-badge warn"; }
        else if (mq2)                   { badge.textContent = "Calidad buena";    badge.className = "quality-badge good"; }
        else                            { badge.textContent = "--";               badge.className = "quality-badge"; }
    }

    // Barras de las métricas
    const setBar = (id, pct, cls) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.style.width = `${pct}%`;
        if (cls) el.className = `bar-fill ${cls}`;
    };

    if (!online) {
        // Offline → limpiar barras
        ["temperaturaBar","humedadBar","presionBar","gasBar"].forEach(id => setBar(id, 0, "bar-ok"));
        return;
    }

    const tempVal  = numero(temp);
    const tempPct  = tempVal !== null ? limitarPorcentaje((tempVal / 50) * 100) : 0;
    const tempCls  = tempPct > 80 ? "bar-danger" : tempPct > 55 ? "bar-warn" : "bar-ok";
    setBar("temperaturaBar", tempPct, tempCls);

    const humPct = limitarPorcentaje(numero(hum));
    setBar("humedadBar", humPct, humPct > 80 ? "bar-warn" : "bar-ok");

    // Presión: normalizar entre 900-1100 hPa → 0-100%
    const presVal = numero(pres);
    const presPct = presVal !== null ? limitarPorcentaje(((presVal - 900) / 200) * 100) : 0;
    setBar("presionBar", presPct, "bar-neutral");

    const gasVolt = numero(gas?.voltage);
    const gasPct  = gasVolt !== null ? limitarPorcentaje((gasVolt / 3.3) * 100) : 0;
    const gasCls  = nivel === "elevado" ? "bar-danger" : nivel === "preventivo" ? "bar-warn" : "bar-ok";
    setBar("gasBar", gasPct, gasCls);
}

/* ── Resumen de residuos ── */
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

/* ── Nodo sonido ── */
function actualizarNodoSonido(data) {
    // KY037 envía cada 3 s — si no hay mensajes en 30 s, está offline
    const online = nodoOnline(data.ultima_vez_modulos, "ESP32_KY037_01", 30);
    const dot = document.getElementById("sonidoNodeDot");
    if (dot) dot.className = `node-dot ${online ? "online" : "offline"}`;
}

/* ── Tacho ── */
function actualizarTacho(id, tacho) {
    const porcentaje = tacho?.porcentaje_llenado ?? tacho?.nivel_llenado;
    const p     = numero(porcentaje);
    const nivel = tacho?.nivel || tacho?.estado || "--";
    const cls   = colorClaseNivel(nivel, p);

    const pctEl = document.getElementById(`tacho${id}Porcentaje`);
    if (pctEl) { flashUpdate(pctEl); pctEl.textContent = p === null ? "--" : `${p}%`; }

    const detEl = document.getElementById(`tacho${id}Detalle`);
    if (detEl) detEl.textContent =
        `Distancia: ${tacho?.distancia_cm ?? "--"} cm · Última: ${tacho?.ultima_actualizacion ?? "--"}`;

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

/* ── Sonido ── */
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

/* ── Fetch principal ── */
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

        // Métricas ambientales — solo mostrar si el nodo está activo
        const ambOnline = nodoOnline(data.ultima_vez_modulos, "ESP32_AIRE_01", 60);

        const tempEl = document.getElementById("temperatura");
        if (tempEl) { flashUpdate(tempEl); tempEl.textContent = ambOnline ? valor(data.ambiental.temperatura, "°") : "--"; }

        const humEl = document.getElementById("humedad");
        if (humEl) { flashUpdate(humEl); humEl.textContent = ambOnline ? valor(data.ambiental.humedad, "%") : "--"; }

        const presEl = document.getElementById("presion");
        if (presEl) { flashUpdate(presEl); presEl.textContent = ambOnline ? valor(data.ambiental.presion) : "--"; }

        const gas = data.ambiental.gas;
        const gNivelEl = document.getElementById("gasNivel");
        const gDetEl   = document.getElementById("gasDetalle");
        if (ambOnline && gas) {
            if (gNivelEl) { flashUpdate(gNivelEl); gNivelEl.textContent = gas.nivel || "--"; }
            if (gDetEl)   gDetEl.textContent = `ADC: ${gas.value_raw ?? "--"} · V: ${gas.voltage ?? "--"}`;
        } else {
            if (gNivelEl) gNivelEl.textContent = "--";
            if (gDetEl)   gDetEl.textContent   = "ADC: -- · V: --";
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

        // Cámara stream
        // Online = la cámara envió heartbeat en los últimos 120 s (heartbeat cada 30 s)
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
            if (livePill) { livePill.textContent = "● En vivo"; livePill.className = "pill ok"; }
        } else {
            if (metaEl) metaEl.textContent = "Cámara desconectada";
            if (livePill) { livePill.textContent = "Sin señal"; livePill.className = "pill bad"; }
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
const usbCameraImage = document.getElementById("usbCameraImage");
const usbCameraStatus = document.getElementById("usbCameraStatus");
if (usbCameraImage && usbCameraStatus) {
    usbCameraImage.addEventListener("load", () => {
        const placeholder = usbCameraImage.previousElementSibling;
        if (placeholder) placeholder.hidden = true;
        usbCameraStatus.textContent = "Conectada";
        usbCameraStatus.className = "pill ok";
    });
    usbCameraImage.addEventListener("error", () => {
        usbCameraImage.hidden = true;
        usbCameraStatus.textContent = "No disponible";
        usbCameraStatus.className = "pill bad";
    });
}

function rutaCapturaVigilancia(ruta) {
    return ruta ? `/static/${ruta.split("/").map(encodeURIComponent).join("/")}` : "";
}

function abrirCapturaVigilancia(ruta, titulo, fechaHora) {
    const modal = document.getElementById("surveillanceCaptureModal");
    const imagen = document.getElementById("captureModalImage");
    if (!modal || !imagen || !ruta) return;
    imagen.src = ruta;
    imagen.alt = `Captura ampliada: ${titulo || "evento de vigilancia"}`;
    const tituloEl = document.getElementById("captureModalTitle");
    const metaEl = document.getElementById("captureModalMeta");
    if (tituloEl) tituloEl.textContent = titulo || "Captura de evento";
    if (metaEl) metaEl.textContent = fechaHora || "";
    if (!modal.open) modal.showModal();
}

let surveillanceLevelFilter = "todos";
let surveillanceTypeFilter = "todos";

function mostrarResumenVigilancia(resumen) {
    const contenedor = document.getElementById("surveillanceSummaryCards");
    if (!contenedor) return;
    contenedor.innerHTML = "";
    (resumen.tarjetas || []).forEach(tarjeta => {
        const articulo = document.createElement("article");
        articulo.className = `event-summary-card level-${tarjeta.nivel}`;
        const nombre = document.createElement("span");
        nombre.textContent = tarjeta.tipo_evento;
        const cantidad = document.createElement("strong");
        cantidad.textContent = tarjeta.cantidad;
        const hora = document.createElement("small");
        hora.textContent = tarjeta.ultima_hora ? `Último: ${tarjeta.ultima_hora}` : "Sin registros recientes";
        articulo.append(nombre, cantidad, hora);
        contenedor.appendChild(articulo);
    });

    const selector = document.getElementById("eventTypeFilter");
    if (selector) {
        const actual = selector.value;
        selector.innerHTML = '<option value="todos">Todos los tipos</option>';
        (resumen.tipos_disponibles || []).forEach(tipo => {
            const opcion = document.createElement("option");
            opcion.value = tipo;
            opcion.textContent = tipo;
            selector.appendChild(opcion);
        });
        selector.value = [...selector.options].some(opcion => opcion.value === actual) ? actual : "todos";
        surveillanceTypeFilter = selector.value;
    }

    const alerta = resumen.ultima_importante;
    const tarjetaAlerta = document.getElementById("latestSurveillanceAlert");
    const tipo = document.getElementById("latestAlertType");
    const hora = document.getElementById("latestAlertTime");
    const imagen = document.getElementById("latestAlertImage");
    if (alerta) {
        tarjetaAlerta?.classList.remove("empty");
        if (tipo) tipo.textContent = alerta.tipo_evento;
        if (hora) hora.textContent = `${alerta.fecha_hora} · ${alerta.descripcion}`;
        if (imagen && alerta.imagen_path) {
            imagen.src = rutaCapturaVigilancia(alerta.imagen_path);
            imagen.dataset.captureTitle = alerta.tipo_evento;
            imagen.dataset.captureMeta = alerta.fecha_hora;
            imagen.hidden = false;
        }
    } else {
        tarjetaAlerta?.classList.add("empty");
        if (tipo) tipo.textContent = "Sin alertas importantes recientes";
        if (hora) hora.textContent = "Se priorizan eventos de revisión y nivel alto.";
        if (imagen) imagen.hidden = true;
    }
}

async function marcarEventoVigilanciaRevisado(eventoId) {
    const token = document.getElementById("surveillanceCsrfToken")?.value;
    const respuesta = await fetch(`/api/vigilancia/eventos/${eventoId}/revisar`, {
        method: "POST",
        headers: { "X-CSRF-Token": token || "" }
    });
    if (!respuesta.ok) throw new Error("No se pudo actualizar el evento");
    await cargarVigilanciaInteligente();
}

function mostrarEventosVigilancia(eventos) {
    const cuerpo = document.getElementById("surveillanceEventsBody");
    if (!cuerpo) return;
    cuerpo.innerHTML = "";
    if (!eventos.length) {
        const fila = cuerpo.insertRow();
        const celda = fila.insertCell();
        celda.colSpan = 7;
        celda.className = "muted";
        celda.textContent = "Sin eventos recientes";
        return;
    }
    eventos.forEach(evento => {
        const fila = cuerpo.insertRow();
        [evento.fecha_hora, evento.tipo_evento, evento.camara].forEach(valor => {
            fila.insertCell().textContent = valor || "--";
        });
        const nivel = fila.insertCell();
        const nivelBadge = document.createElement("span");
        nivelBadge.className = `event-level ${evento.nivel}`;
        nivelBadge.textContent = evento.nivel;
        nivel.appendChild(nivelBadge);
        fila.insertCell().textContent = evento.estado || "--";
        const captura = fila.insertCell();
        if (evento.imagen_path) {
            const botonCaptura = document.createElement("button");
            botonCaptura.type = "button";
            botonCaptura.className = "capture-view-btn";
            botonCaptura.textContent = "Ver captura";
            botonCaptura.addEventListener("click", () => {
                abrirCapturaVigilancia(
                    rutaCapturaVigilancia(evento.imagen_path),
                    evento.tipo_evento,
                    evento.fecha_hora
                );
            });
            captura.appendChild(botonCaptura);
        } else {
            captura.textContent = "--";
        }
        const accion = fila.insertCell();
        if (evento.estado === "pendiente") {
            const boton = document.createElement("button");
            boton.type = "button";
            boton.className = "review-event-btn";
            boton.textContent = "Marcar revisado";
            boton.addEventListener("click", async () => {
                boton.disabled = true;
                try { await marcarEventoVigilanciaRevisado(evento.id); }
                catch (error) { console.error(error); boton.disabled = false; }
            });
            accion.appendChild(boton);
        } else {
            const revisado = document.createElement("span");
            revisado.className = "event-reviewed";
            revisado.textContent = "Revisado";
            accion.appendChild(revisado);
        }
    });
}

async function cargarVigilanciaInteligente() {
    const indicador = document.getElementById("smartAnalysisStatus");
    if (!indicador) return;
    try {
        const parametros = new URLSearchParams({
            limite: "10", nivel: surveillanceLevelFilter, tipo: surveillanceTypeFilter
        });
        const [estadoRespuesta, eventosRespuesta, resumenRespuesta] = await Promise.all([
            fetch("/api/vigilancia/estado", { cache: "no-store" }),
            fetch(`/api/vigilancia/eventos?${parametros}`, { cache: "no-store" }),
            fetch("/api/vigilancia/resumen", { cache: "no-store" })
        ]);
        if (!estadoRespuesta.ok || !eventosRespuesta.ok || !resumenRespuesta.ok) throw new Error("API no disponible");
        const estado = await estadoRespuesta.json();
        const eventos = await eventosRespuesta.json();
        const resumen = await resumenRespuesta.json();
        indicador.textContent = estado.estado || "Sin eventos recientes";
        indicador.className = estado.disponible === false ? "pill bad" : "pill ok";
        const orientacion = document.getElementById("faceOrientationStatus");
        if (orientacion) {
            const valor = estado.orientacion_estimada || "No determinada";
            orientacion.textContent = `Orientación: ${valor}`;
        }
        const persona = document.getElementById("personDetectionStatus");
        if (persona) persona.textContent = `Persona: ${estado.estado_persona || "Sin persona"}`;
        const visibilidad = document.getElementById("faceVisibilityStatus");
        if (visibilidad) {
            const valor = estado.visibilidad_facial || "No concluyente";
            visibilidad.textContent = `Visibilidad: ${valor}`;
            visibilidad.className = valor === "Rostro visible" ? "pill ok" : "pill";
        }
        const nivel = document.getElementById("surveillanceAlertLevel");
        if (nivel) {
            const valor = estado.nivel_alerta || "normal";
            nivel.textContent = `Nivel: ${valor}`;
            nivel.className = ["alto", "revisión"].includes(valor) ? "pill bad" : (valor === "normal" ? "pill ok" : "pill");
        }

        mostrarResumenVigilancia(resumen);
        mostrarEventosVigilancia(eventos);
    } catch (error) {
        indicador.textContent = "Análisis inteligente no disponible";
        indicador.className = "pill bad";
        console.error("Error cargando vigilancia inteligente:", error);
    }
}

if (document.getElementById("smartAnalysisStatus")) {
    const captureModal = document.getElementById("surveillanceCaptureModal");
    document.getElementById("closeCaptureModal")?.addEventListener("click", () => captureModal?.close());
    captureModal?.addEventListener("click", evento => {
        if (evento.target === captureModal) captureModal.close();
    });
    document.getElementById("latestAlertImage")?.addEventListener("click", evento => {
        abrirCapturaVigilancia(
            evento.currentTarget.src,
            evento.currentTarget.dataset.captureTitle,
            evento.currentTarget.dataset.captureMeta
        );
    });
    document.querySelectorAll(".event-filter").forEach(boton => {
        boton.addEventListener("click", () => {
            document.querySelectorAll(".event-filter").forEach(item => item.classList.remove("active"));
            boton.classList.add("active");
            surveillanceLevelFilter = boton.dataset.level;
            cargarVigilanciaInteligente();
        });
    });
    document.getElementById("eventTypeFilter")?.addEventListener("change", evento => {
        surveillanceTypeFilter = evento.target.value;
        cargarVigilanciaInteligente();
    });
    cargarVigilanciaInteligente();
    setInterval(cargarVigilanciaInteligente, 3000);
}
