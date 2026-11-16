if (!window.mwNavigationInitialized) {
  window.mwNavigationInitialized = true;
  document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-nav-toggle]").forEach((toggle) => {
    toggle.addEventListener("click", () => {
      const menu = document.getElementById(toggle.getAttribute("aria-controls"));
      if (!menu) return;
      const isOpen = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!isOpen));
      menu.classList.toggle("is-open", !isOpen);
      });
    }
  });

  document.querySelectorAll("[data-safe-referer]").forEach((link) => {
    link.addEventListener("click", (event) => {
      const referer = link.dataset.safeReferer;
      if (!referer || window.history.length <= 1) return;
      try {
        if (new URL(referer, window.location.href).origin === window.location.origin) {
          event.preventDefault();
          window.history.back();
        }
      } catch {
        // Keep the validated fallback href when the browser cannot parse the referrer.
      }
    });
  });
});
