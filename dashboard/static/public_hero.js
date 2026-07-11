const HERO_INTERVALO_MS = 6000;

document.addEventListener("DOMContentLoaded", () => {
  const hero = document.querySelector(".public-hero");
  if (!hero) return;

  const slides = Array.from(hero.querySelectorAll(".public-hero-slide"));
  const dots = Array.from(hero.querySelectorAll(".hero-dot"));
  if (slides.length < 2) return;

  let indiceActual = slides.findIndex(slide => slide.classList.contains("is-active"));
  if (indiceActual < 0) indiceActual = 0;
  let temporizador = null;

  function mostrar(indice) {
    slides[indiceActual].classList.remove("is-active");
    dots[indiceActual]?.classList.remove("is-active");
    indiceActual = indice;
    slides[indiceActual].classList.add("is-active");
    dots[indiceActual]?.classList.add("is-active");
  }

  function siguiente() {
    mostrar((indiceActual + 1) % slides.length);
  }

  function reiniciarAutoplay() {
    if (temporizador) clearInterval(temporizador);
    temporizador = setInterval(siguiente, HERO_INTERVALO_MS);
  }

  dots.forEach((boton, indice) => {
    boton.addEventListener("click", () => {
      if (indice === indiceActual) return;
      mostrar(indice);
      reiniciarAutoplay();
    });
  });

  reiniciarAutoplay();
});
