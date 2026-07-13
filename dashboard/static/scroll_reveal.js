document.addEventListener("DOMContentLoaded", () => {
  const elementos = document.querySelectorAll(".reveal-up");
  if (!elementos.length) return;

  const sinMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (sinMovimiento || !("IntersectionObserver" in window)) {
    elementos.forEach(el => el.classList.add("is-visible"));
    return;
  }

  const observador = new IntersectionObserver((entradas) => {
    entradas.forEach(entrada => {
      if (!entrada.isIntersecting) return;
      entrada.target.classList.add("is-visible");
      observador.unobserve(entrada.target);
    });
  }, { threshold: 0.15, rootMargin: "0px 0px -40px 0px" });

  elementos.forEach(el => observador.observe(el));
});
