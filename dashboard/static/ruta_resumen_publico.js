function crearMiniMarcadoresPublico() {
  const contenedor = document.getElementById("rutaResumenMarcadores");
  for (const [id, punto] of Object.entries(MAPA_MAQUETA)) {
    if (punto.tipo !== "salida" && punto.tipo !== "tacho") continue;
    const marcador = document.createElement("span");
    marcador.className = `mini-map-marker ${punto.tipo === "salida" ? "base" : "bin"}`;
    marcador.style.left = `${punto.x}%`; marcador.style.top = `${punto.y}%`;
    marcador.textContent = punto.tipo === "salida" ? "S" : id;
    contenedor.appendChild(marcador);
  }
}

async function cargarResumenRutaPublico() {
  const respuesta = await fetch("/api/estado-urbano/ruta");
  if (!respuesta.ok) return;
  const ruta = (await respuesta.json()).ruta;
  const vacio = document.getElementById("rutaResumenVacia");
  const datos = document.getElementById("rutaResumenDatos");
  const estado = document.getElementById("rutaResumenEstado");
  if (!ruta) {
    vacio.querySelector("p").textContent = "Aún no se ha generado un recorrido de recojo.";
    return;
  }
  estado.hidden = !ruta.desactualizada;
  estado.textContent = ruta.desactualizada ? "Lecturas nuevas" : "Actualizada";
  estado.className = `mini-pill ${ruta.desactualizada ? "level-mid" : "level-low"}`;
  if (!ruta.orden_tachos.length) {
    vacio.querySelector("p").textContent = "No hay contenedores que requieran recojo en este momento.";
    document.getElementById("rutaResumenVaciaFecha").textContent = `Última generación: ${ruta.fecha_generacion}`;
    return;
  }
  const recorrido = ["salida", ...ruta.orden_tachos, "salida"];
  document.getElementById("rutaResumenLinea").setAttribute("points", rutaPorCalles(recorrido).points);
  document.getElementById("rutaResumenSecuencia").textContent = recorrido.map(id => id === "salida" ? "Punto de salida" : `Contenedor ${id}`).join(" → ");
  document.getElementById("rutaResumenProgramados").textContent = ruta.tachos_incluidos.length;
  document.getElementById("rutaResumenOmitidos").textContent = ruta.tachos_omitidos.length;
  document.getElementById("rutaResumenDistancia").textContent = Math.round(ruta.distancia_estimada);
  document.getElementById("rutaResumenFecha").textContent = `Última generación: ${ruta.fecha_generacion}`;
  vacio.hidden = true; datos.hidden = false;
}

document.addEventListener("DOMContentLoaded", () => {
  crearMiniMarcadoresPublico();
  cargarResumenRutaPublico().catch(error => console.error(error));
});
