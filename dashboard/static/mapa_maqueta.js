/* Único lugar para configurar el mapa de la maqueta: imagen de fondo y posiciones (en %). */
const MAPA_MAQUETA_IMG = "/static/img/mapa_maqueta.jpeg";

const MAPA_MAQUETA = Object.freeze({
  salida: { x: 12, y: 84, tipo: "salida",     etiqueta: "Punto de salida" },
  A:      { x: 10, y: 23, tipo: "tacho",      etiqueta: "Tacho A" },
  B:      { x: 57, y: 10, tipo: "tacho",      etiqueta: "Tacho B" },
  C:      { x: 41, y: 44, tipo: "tacho",      etiqueta: "Tacho C" },
  D:      { x: 61, y: 83, tipo: "tacho",      etiqueta: "Tacho D" },
  A1:     { x: 48, y: 15, tipo: "ambiente",   etiqueta: "A1 · Ambiente" },
  A2:     { x: 48, y: 79, tipo: "ambiente",   etiqueta: "A2 · Ambiente" },
  VG:     { x: 24, y: 79, tipo: "vigilancia", etiqueta: "VG" },
  torres: { x: 50, y: 47, tipo: "hito",       etiqueta: "Torres Gemelas" }
});

/* Red vial de la maqueta: ejes centrales de las avenidas, en % del mapa.
   Las rutas viajan solo por estas calles (trazado tipo cuadrícula). */
const CALLES_MAQUETA = Object.freeze({
  verticales: [35, 65],
  horizontales: [35, 68]
});

/* Proyecta un punto libre (dentro de una manzana) a la calle más cercana. */
function puntoEnVia(p) {
  let mejor = null;
  for (const x of CALLES_MAQUETA.verticales) {
    if (!mejor || Math.abs(p.x - x) < mejor.dist) mejor = { x, y: p.y, eje: "v", dist: Math.abs(p.x - x) };
  }
  for (const y of CALLES_MAQUETA.horizontales) {
    if (!mejor || Math.abs(p.y - y) < mejor.dist) mejor = { x: p.x, y, eje: "h", dist: Math.abs(p.y - y) };
  }
  return mejor;
}

/* Puntos intermedios (esquinas) para ir de un punto en vía a otro siguiendo calles. */
function tramoVial(a, b) {
  if (a.eje === "v" && b.eje === "v") {
    if (a.x === b.x) return [];
    let corte = null;
    for (const hy of CALLES_MAQUETA.horizontales) {
      const costo = Math.abs(a.y - hy) + Math.abs(b.y - hy);
      if (!corte || costo < corte.costo) corte = { hy, costo };
    }
    return [{ x: a.x, y: corte.hy }, { x: b.x, y: corte.hy }];
  }
  if (a.eje === "h" && b.eje === "h") {
    if (a.y === b.y) return [];
    let corte = null;
    for (const vx of CALLES_MAQUETA.verticales) {
      const costo = Math.abs(a.x - vx) + Math.abs(b.x - vx);
      if (!corte || costo < corte.costo) corte = { vx, costo };
    }
    return [{ x: corte.vx, y: a.y }, { x: corte.vx, y: b.y }];
  }
  return a.eje === "v" ? [{ x: a.x, y: b.y }] : [{ x: b.x, y: a.y }];
}

/* Trayecto completo entre dos puntos del mapa: acceso a la vía, calles y llegada. */
function trayectoEntrePuntos(origen, destino) {
  const va = puntoEnVia(origen), vb = puntoEnVia(destino);
  const crudo = [origen, va, ...tramoVial(va, vb), vb, destino];
  const puntos = [];
  for (const p of crudo) {
    const ultimo = puntos[puntos.length - 1];
    if (!ultimo || ultimo.x !== p.x || ultimo.y !== p.y) puntos.push({ x: p.x, y: p.y });
  }
  let dist = 0;
  for (let i = 1; i < puntos.length; i++) {
    dist += Math.hypot(puntos[i].x - puntos[i - 1].x, puntos[i].y - puntos[i - 1].y);
  }
  return { puntos, dist };
}

/* Convierte un recorrido de ids (["salida","A",...,"salida"]) en la polyline
   que sigue las calles y su distancia total. */
function rutaPorCalles(recorrido) {
  const puntos = [];
  let dist = 0;
  for (let i = 1; i < recorrido.length; i++) {
    const tramo = trayectoEntrePuntos(MAPA_MAQUETA[recorrido[i - 1]], MAPA_MAQUETA[recorrido[i]]);
    dist += tramo.dist;
    puntos.push(...(puntos.length ? tramo.puntos.slice(1) : tramo.puntos));
  }
  return { dist, points: puntos.map(p => `${p.x},${p.y}`).join(" ") };
}

/* Precarga la imagen; si carga bien la aplica como fondo de todos los mapas
   (grande y mini). Si falla, se conserva el plano placeholder con cuadrícula. */
document.addEventListener("DOMContentLoaded", () => {
  const fondo = new Image();
  fondo.onload = () => {
    for (const mapa of document.querySelectorAll(".model-map, .mini-model-map")) {
      mapa.style.setProperty("--mapa-maqueta-fondo", `url("${MAPA_MAQUETA_IMG}")`);
      mapa.classList.add("map-has-image");
    }
  };
  fondo.src = MAPA_MAQUETA_IMG;
});
