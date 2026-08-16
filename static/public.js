// Apparition en fondu + léger décalage des blocs ".reveal" quand ils entrent
// dans l'écran. Dégrade proprement (tout visible immédiatement) si
// IntersectionObserver n'est pas disponible.
document.addEventListener("DOMContentLoaded", function () {
    var elements = document.querySelectorAll(".reveal");
    if (!elements.length) return;

    if (!("IntersectionObserver" in window)) {
        elements.forEach(function (el) { el.classList.add("reveal-visible"); });
        return;
    }

    var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add("reveal-visible");
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.15, rootMargin: "0px 0px -60px 0px" });

    elements.forEach(function (el) { observer.observe(el); });
});
