const UMBRAL_RECOJO = 50;
const UMBRAL_URGENTE = 80;
let estadoTachos = [];
let firmaLecturas = "";
let firmaRutaGenerada = null;

function permutaciones(items) {
  if (items.length <= 1) return [items];
  return items.flatMap((item, indice) =>
    permutaciones(items.filter((_, i) => i !== indice)).map(resto => [item, ...resto])
  );
}

function calcularRuta(ids) {
  let mejor = null;
  for (const orden of permutaciones(ids)) {
    const recorrido = ["salida", ...orden, "salida"];
    const total = rutaPorCalles(recorrido).dist;
    if (!mejor || total < mejor.distancia) mejor = { orden, recorrido, distancia: total };
  }
  return mejor;
}

function seleccionarTachos(tachos) {
  return tachos.filter(t => t.reciente && t.porcentaje != null && t.porcentaje >= UMBRAL_RECOJO);
}

function clasificar(tacho) {
  if (!tacho.reciente || tacho.porcentaje == null) return { clase: "no-data", texto: "Sin datos recientes", corto: "Sin datos" };
  if (tacho.porcentaje >= UMBRAL_URGENTE) return { clase: "urgent", texto: "Recojo urgente", corto: "Urgente" };
  if (tacho.porcentaje >= UMBRAL_RECOJO) return { clase: "recommended", texto: "Recojo recomendado", corto: "Recomendado" };
  return { clase: "normal", texto: "No requiere recojo", corto: "Sin recojo" };
}

const CLASE_MARCADOR = {
  salida: "map-marker base marker-salida",
  tacho: "map-marker bin marker-tacho no-data",
  ambiente: "map-marker sensor marker-ambiente",
  vigilancia: "map-marker sensor marker-vigilancia",
  hito: "map-marker marker-hito"
};
let tachosEnRuta = new Set();

function dibujarMarcadores() {
  const contenedor = document.getElementById("marcadoresMapa");
  for (const [id, punto] of Object.entries(MAPA_MAQUETA)) {
    const marcador = document.createElement("span");
    marcador.className = CLASE_MARCADOR[punto.tipo] || "map-marker";
    marcador.id = `marcador-${id}`;
    marcador.style.left = `${punto.x}%`;
    marcador.style.top = `${punto.y}%`;
    marcador.textContent = punto.etiqueta;
    contenedor.appendChild(marcador);
  }
}

function resaltarTachosEnRuta(ids) {
  tachosEnRuta = new Set(ids);
  for (const [id, punto] of Object.entries(MAPA_MAQUETA)) {
    if (punto.tipo !== "tacho") continue;
    document.getElementById(`marcador-${id}`)?.classList.toggle("en-ruta", tachosEnRuta.has(id));
  }
}

function renderTachos() {
  for (const tacho of estadoTachos) {
    const estado = clasificar(tacho);
    const card = document.getElementById(`rutaTacho${tacho.id}`);
    card.className = `collection-bin-card ${estado.clase}`;
    document.getElementById(`rutaEstado${tacho.id}`).textContent = estado.corto;
    document.getElementById(`rutaPorcentaje${tacho.id}`).textContent = tacho.reciente && tacho.porcentaje != null ? `${tacho.porcentaje}%` : "--";
    document.getElementById(`rutaDecision${tacho.id}`).textContent = estado.texto;
    document.getElementById(`rutaActualizacion${tacho.id}`).textContent = `Última actualización: ${tacho.ultima_actualizacion || "--"}`;
    const marcador = document.getElementById(`marcador-${tacho.id}`);
    if (marcador) marcador.className = `map-marker bin marker-tacho ${estado.clase}${tachosEnRuta.has(tacho.id) ? " en-ruta" : ""}`;
  }
}

async function cargarLecturas() {
  const respuesta = await fetch("/api/ruta-recoleccion-datos");
  if (!respuesta.ok) throw new Error("No se pudieron obtener las lecturas de residuos");
  const datos = await respuesta.json();
  estadoTachos = datos.tachos || [];
  const nuevaFirma = JSON.stringify(estadoTachos.map(t => [t.id, t.porcentaje, t.reciente, t.ultima_actualizacion]));
  if (firmaRutaGenerada && firmaLecturas && nuevaFirma !== firmaLecturas) {
    document.getElementById("lecturasNuevas").hidden = false;
  }
  firmaLecturas = nuevaFirma;
  renderTachos();
}

function agregarItem(lista, texto, clase = "") {
  const item = document.createElement("li");
  item.className = clase;
  item.textContent = texto;
  lista.appendChild(item);
}

async function guardarPlanificacion(orden, incluidos, omitidos, distanciaTotal) {
  const csrf = document.querySelector('input[name="csrf_token"]')?.value;
  const respuesta = await fetch("/api/ruta-recoleccion-guardar", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf || "" },
    body: JSON.stringify({ orden, incluidos, omitidos, distancia: distanciaTotal, niveles: estadoTachos })
  });
  if (!respuesta.ok) throw new Error("No se pudo guardar la planificación");
  return (await respuesta.json()).ruta;
}

function mostrarRutaGuardada(ruta) {
  if (!ruta) return;
  const vacio = document.getElementById("rutaVacia");
  const contenido = document.getElementById("rutaContenido");
  const linea = document.getElementById("rutaLinea");
  firmaRutaGenerada = JSON.stringify(ruta.niveles_analizados || []);
  document.getElementById("lecturasNuevas").hidden = !ruta.desactualizada;
  resaltarTachosEnRuta(ruta.orden_tachos);
  if (!ruta.orden_tachos.length) {
    vacio.textContent = "No hay tachos que requieran recojo en este momento.";
    vacio.hidden = false;
    contenido.hidden = true;
    linea.setAttribute("points", "");
    return;
  }
  const recorrido = ["salida", ...ruta.orden_tachos, "salida"];
  document.getElementById("rutaTexto").textContent = recorrido.map(id => id === "salida" ? "Punto de salida" : `Tacho ${id}`).join(" → ");
  document.getElementById("rutaDistancia").textContent = Math.round(ruta.distancia_estimada);
  linea.setAttribute("points", rutaPorCalles(recorrido).points);
  const niveles = ruta.niveles_analizados || [];
  const programadosLista = document.getElementById("tachosProgramados");
  const omitidosLista = document.getElementById("tachosOmitidos");
  programadosLista.replaceChildren(); omitidosLista.replaceChildren();
  for (const id of ruta.orden_tachos) {
    const tacho = niveles.find(t => t.id === id) || { id, porcentaje: null, reciente: false };
    const estado = clasificar(tacho);
    agregarItem(programadosLista, `Tacho ${id} · ${tacho.porcentaje ?? "--"}% · ${estado.texto}`, estado.clase);
  }
  for (const id of ruta.tachos_omitidos) {
    const tacho = niveles.find(t => t.id === id) || { id, porcentaje: null, reciente: false };
    const estado = clasificar(tacho);
    const nivel = tacho.reciente && tacho.porcentaje != null ? `${tacho.porcentaje}%` : "Sin datos";
    agregarItem(omitidosLista, `Tacho ${id} · ${nivel} · ${estado.texto}`, estado.clase);
  }
  document.getElementById("rutaGeneradaEn").textContent = `Generado: ${ruta.fecha_generacion}`;
  vacio.hidden = true; contenido.hidden = false;
}

async function cargarUltimaRuta() {
  const respuesta = await fetch("/api/ruta-recoleccion-ultima");
  if (respuesta.ok) mostrarRutaGuardada((await respuesta.json()).ruta);
}

async function generarRecorrido() {
  const seleccionados = seleccionarTachos(estadoTachos);
  const omitidos = estadoTachos.filter(t => !seleccionados.includes(t));
  const vacio = document.getElementById("rutaVacia");
  const contenido = document.getElementById("rutaContenido");
  const linea = document.getElementById("rutaLinea");
  firmaRutaGenerada = firmaLecturas;
  document.getElementById("lecturasNuevas").hidden = true;

  if (!seleccionados.length) {
    resaltarTachosEnRuta([]);
    const guardada = await guardarPlanificacion([], [], omitidos.map(t => t.id), 0);
    vacio.textContent = "No hay tachos que requieran recojo en este momento.";
    vacio.hidden = false;
    contenido.hidden = true;
    linea.setAttribute("points", "");
    document.getElementById("rutaGeneradaEn").textContent = guardada ? `Generado: ${guardada.fecha_generacion}` : "";
    return;
  }

  const mejor = calcularRuta(seleccionados.map(t => t.id));
  resaltarTachosEnRuta(mejor.orden);
  document.getElementById("rutaTexto").textContent = mejor.recorrido.map(id => id === "salida" ? "Punto de salida" : `Tacho ${id}`).join(" → ");
  document.getElementById("rutaDistancia").textContent = Math.round(mejor.distancia);
  linea.setAttribute("points", rutaPorCalles(mejor.recorrido).points);

  const programadosLista = document.getElementById("tachosProgramados");
  const omitidosLista = document.getElementById("tachosOmitidos");
  programadosLista.replaceChildren();
  omitidosLista.replaceChildren();
  for (const id of mejor.orden) {
    const tacho = seleccionados.find(t => t.id === id);
    const estado = clasificar(tacho);
    agregarItem(programadosLista, `Tacho ${id} · ${tacho.porcentaje}% · ${estado.texto}`, estado.clase);
  }
  for (const tacho of omitidos) {
    const estado = clasificar(tacho);
    const nivel = tacho.reciente && tacho.porcentaje != null ? `${tacho.porcentaje}%` : "Sin datos";
    agregarItem(omitidosLista, `Tacho ${tacho.id} · ${nivel} · ${estado.texto}`, estado.clase);
  }
  const guardada = await guardarPlanificacion(mejor.orden, seleccionados.map(t => t.id), omitidos.map(t => t.id), mejor.distancia);
  document.getElementById("rutaGeneradaEn").textContent = `Generado: ${guardada.fecha_generacion}`;
  vacio.hidden = true;
  contenido.hidden = false;
}

document.addEventListener("DOMContentLoaded", async () => {
  dibujarMarcadores();
  try { await cargarLecturas(); await cargarUltimaRuta(); } catch (error) { console.error(error); }
  document.getElementById("generarRecorrido").addEventListener("click", async () => {
    try { await cargarLecturas(); await generarRecorrido(); } catch (error) { console.error(error); }
  });
  setInterval(() => cargarLecturas().catch(error => console.error(error)), 5000);
});
