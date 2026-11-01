# Ideiglenes JSON-tesztmód

2026-10-22-én a felhasználó kérésére aktiválva, automatikus lejárat nélkül.

Éles értékek: think=false, temperature=0, num_predict=256, format="json", stream=false. A num_ctx változatlanul 16384.

Az előző értékeket a `before-json-test-2026-10-22.json` őrzi. Visszaállításkor a meglévő AI config API-n a temperature=0.2, num_predict=1536 és format="" értékeket kell menteni. A think és stream továbbra is false. A modell, végpont és egyéb konfiguráció változatlan.

A format beállítás az Ollama-kérésekre vonatkozik. A HC közvetlen, determinisztikus szöveges válaszágai nem modellkérések, így azokra nem vonatkozik a JSON-kényszerítés.
