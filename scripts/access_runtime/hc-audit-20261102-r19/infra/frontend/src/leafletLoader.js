let pending;

export function loadLeaflet() {
  if (pending) return pending;
  const elements = [];
  pending = Promise.all([
    ["link", "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css", "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="],
    ["script", "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js", "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="],
  ].map(([tag, url, integrity]) => new Promise((resolve, reject) => {
    const element = document.createElement(tag);
    elements.push(element);
    element.integrity = integrity;
    element.crossOrigin = "anonymous";
    if (tag === "link") {
      element.rel = "stylesheet";
      element.href = url;
    } else {
      element.src = url;
      element.async = true;
    }
    const timeout = window.setTimeout(() => finish(new Error("A térképkönyvtár betöltése túl sokáig tart.")), 20000);
    function finish(error) {
      window.clearTimeout(timeout);
      element.onload = element.onerror = null;
      if (error) reject(error);
      else resolve();
    }
    element.onload = () => finish();
    element.onerror = () => finish(new Error("A térképkönyvtár nem tölthető be. Frissítsd az oldalt az újrapróbálkozáshoz."));
    document.head.appendChild(element);
  }))).then(() => {
    if (!window.L) throw new Error("A térképkönyvtár nem érhető el.");
    return window.L;
  }).catch((error) => {
    elements.forEach((element) => element.remove());
    pending = undefined;
    throw error;
  });
  return pending;
}
