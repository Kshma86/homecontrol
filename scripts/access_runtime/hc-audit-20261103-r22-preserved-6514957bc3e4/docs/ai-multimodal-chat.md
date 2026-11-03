# HC multimodális AI-chat

## Audit és megoldás

Az egyetlen kommunikációs útvonal megmaradt:
`AiChat → POST /api/ai/chat → AiProxyService → AI gateway /chat → Ollama /api/chat`.
A kontextusépítés, tudásbázis, audit, modellkezelés, helyi szöveges előzménymentés és a szöveges providerek megmaradtak.

Az audit során nem volt hálózati chatstream: az Ollama-kérés `stream: false`, a frontend a teljes választ időzítővel, fokozatosan jeleníti meg. Ez változatlan. A modellletöltés különálló streamkezelése is változatlan.

A képes üzenetek mindkét rétegben kihagyják a determinisztikus szöveges válaszágat. A gateway minden képes kérésnél az aktuális, mentett konfiguráció modelljére és Ollama-végpontjára kér `/api/show` adatot; csak a `capabilities` mezőben szereplő `vision` engedélyez. Név alapján nincs találgatás. Ismeretlen képesség esetén nincs képküldés. Más providerek képes kérése elutasított; a szöveges működésük változatlan.

A natív szerződés alapja az [Ollama API dokumentációja](https://github.com/ollama/ollama/blob/main/docs/api.md).

## API-szerződés

A meglévő `POST /api/ai/chat` JSON-kérés opcionális `images` listával bővült:

```json
{
  "message": "Mi látható a képeken?",
  "history": [{"role": "user", "content": "Korábbi kérdés"}],
  "images": [{"mime_type": "image/png", "data": "<nyers base64, data URL előtag nélkül>"}]
}
```

- `images` elhagyható, `null` vagy üres lista: korábbi szöveges működés.
- Képpel az üres `message` is megengedett.
- Maximum 4 kép, képenként 3 MiB dekódolt adat; legfeljebb 20 millió pixel, kizárólag állókép.
- MIME: `image/jpeg`, `image/png`, `image/webp`. A MIME-nak egyeznie kell a dekódolt formátummal.
- A frontend fájlkiterjesztést, MIME-ot, darabszámot és méretet ellenőriz; a backend és a gateway base64-et, formátumot, pixelkorlátot, képszerkezetet és teljes dekódolhatóságot is ellenőriz Pillow-val.
- Teljes kéréskorlát: 17 MiB a backendben, gatewayben és mindkét Nginx-rétegben.
- Az előzmények továbbra is szövegesek; korábbi képek nem kerülnek automatikusan újraküldésre.
- A sikeres válasz meglévő szerződése megmarad (`ok`, `reply`, `provider`, `model`, `context`, gatewayből `elapsed_ms`).
- Hibás kép vagy nem vision modell: HTTP 400, `{ "ok": false, "error": "…" }`.
- Túlméretes teljes kérés: a backend/Nginx HTTP 413; közvetlen gatewayhívásnál HTTP 400.
- Provider-/kapcsolati hiba: HTTP 502. Képes kérésnél nincs szöveges fallback, amely sikeres képelemzésnek tűnhetne.

Az AI gateway a meglévő rendszer- és előzményüzenetek után az aktuális user üzenetet így állítja össze:

```json
{"role": "user", "content": "Mi látható?", "images": ["<base64>", "<base64>"]}
```

A képek nem kerülnek az `options`, a prompt vagy külön API mezőjébe az Ollama felé.

## Komponensek és tárolás

- `infra/frontend/src/features/ai/AiChat.jsx`, `aiApi.js`, `aiImages.mjs`, `styles.css`: többszörös képkiválasztás, előnézet, eltávolítás, hibák, meglévő kérési útvonal és válaszanimáció.
- `infra/backend/ai_proxy_service.py`, `api_route_modules.py`: validálás, méretkorlát, továbbítás; képes kérésnél nincs közvetlen HC-szövegválasz.
- `apps/ai-server/ai_server.py`: újravalidálás, vision ellenőrzés, natív Ollama images mező, hibakezelés.
- Mindkét Python-szolgáltatás `ai_images.py` modulja azonos. Külön Docker build context miatt két példány szükséges; teszt őrzi az egyezésüket. Pillow 11.3.0 a rögzített függőség.
- Mindkét Nginx konfiguráció: külön chatméretkorlát és kikapcsolt request buffering; nincs automatikus request body tempfájl-pufferelés.

A képadatok csak az aktuális munkamenet memóriájában és a folyamatban lévő kérésekben élnek. A frontend localStorage mentése kihagyja a képeket; az audit nem kap képadatot. Nincs új fájl-, adatbázis- vagy objektumtárolás. A sikertelen kérés csatolmányai a szerkesztőben maradnak újrapróbáláshoz. A Clear törli a memóriabeli képeket is. Az Ollama saját üzemeltetési naplózási beállításai külön szolgáltatási felelősség.

## Ellenőrzés

- Backend Python 3.12 + a Dockerfile rögzített függőségei: `python -m unittest discover -s infra/backend/tests -p 'test_ai*.py'`: **29 sikeres teszt**.
- Képformátumok, több kép, hamis MIME, hibás base64, sérült kép, méret-/pixel-/darabszámkorlát; natív Ollama payload, vision tiltás, providerhibák, audit, HTTP JSON-szerződés és 413 ellenőrzése.
- Frontend: `npm run test:ai`: **4 sikeres teszt**; `npm run test:mower`: **83 meglévő teszt sikeres**.
- Frontend production build és mindhárom alkalmazás Docker-buildje sikeres.
- Éles szolgáltatás újraindítása és valódi vision modellel végzett végponttól végpontig próba nem történt. A provider válaszait a tesztek helyettesítik.

Élesítéskor a backend, AI gateway és frontend image újraépítése, valamint a külső proxy konfigurációjának újratöltése szükséges.

## Kontekstuskeret javítása

Képes kérésnél a system prompt legfeljebb 4000 karakter, a HC-adatokból 3000, a tudásanyagból 2000 karakteres kivonat, az előzményből legfeljebb 4 üzenet és összesen 3000 karakter kerül a modellhez. A felhasználó aktuális kérdése és eredeti képei az első kérésben változatlanok.

Ollama HTTP 400 kontextustúllépésnél egyszeri újrapróbálás történik: csak a korlátozott system prompt, az aktuális kérdés és az aránytartóan legfeljebb 1024 × 1024 pixelre kicsinyített képek maradnak. A kicsinyítés csökkentheti az apró részletek olvashatóságát. A kliens eredeti csatolmányait nem módosítjuk. Ismételt túllépés érthető hibát ad; egyéb hibákat nem próbálunk újra. A num_ctx és a szöveges kérések működése változatlan.

## Soros, független többképes feldolgozás (2026-10-22)

Módosítás előtti audit: az éles gateway `ollama_reply` függvényén helyettesített hálózati hívással mért eredmény: 1 Ollama-kérés, 2 elem a user üzenet `images` listájában, mindkét bemeneti kép továbbítva. A frontend `imagePayload`, a HC proxy validálása/továbbítása és a gateway is megőrizte a teljes listát. A hiba tehát nem a második csatolmány elvesztése volt a HC kérésösszeállításakor.

A feldolgozás most a meglévő AI gateway `sequential_image_replies` ciklusában történik, a meglévő `ollama_reply` hívásával. Minden kép külön, egymás után kerül az Ollamához, azonos aktuális user prompttal, egyetlen képpel. Nincs korábbi beszélgetési előzmény, korábbi képadat, korábbi modellválasz vagy automatikus HC háttéradat. A konfigurált system prompt megmarad (a korábbi 4000 karakteres vision korláttal). A natív kérés `think: false`, `stream: false`; a tesztidőszak konfigurált JSON-formátuma, temperature és num_predict értékei megmaradnak. A kiszolgáló nem indít összegző modellkérést.

Az `ollama_reply` több képet tartalmazó közvetlen hívást elutasít, hogy véletlenül se készülhessen újabb közös többképes kérés. A korábbi egyszeri kontextuskeret-újrapróbálás is kizárólag ugyanazt az egy képet kapja. A hálózati időkorlát kísérletenként `AI_REQUEST_TIMEOUT / (2 × képszám)`, így a soros hívások és a lehetséges egyszeri újrapróbálások a korábbi teljes modellkérési időkerethez igazodnak. Ez nem változtatja meg a csak szöveges kérések időkorlátját.

A bemeneti API-szerződés változatlan. Sikeres vagy részben sikeres válaszban a meglévő `reply` mező tartalmazza az összefűzött, `1. kép`, `2. kép` stb. sorokkal tagolt választ. A frontend ezt egyetlen assistant üzenetben jeleníti meg. További mezők:

```json
{
  "ok": true,
  "reply": "1. kép\nElső válasz\n\n2. kép\nHiba: ...",
  "partial": true,
  "image_results": [
    {"index": 1, "ok": true, "reply": "Első válasz"},
    {"index": 2, "ok": false, "error": "..."}
  ]
}
```

A `partial` akkor true, ha a feldolgozások közül van hibás is. Ha minden kép feldolgozása sikertelen, HTTP 502 és `ok: false` válasz érkezik; az `error` tartalmazza az összes sorszámozott hibát, az `image_results` az egyedi eredményeket. Nem vision modell vagy hibás feltöltés továbbra is a korábbi validálási szabályok szerint elutasított; a hibánkénti folytatás az elfogadott képek modellfeldolgozására vonatkozik.

Csak a gateway forrása és a tesztek változtak; nincs új kommunikációs réteg, frontendváltozás, tartós képtárolás vagy domainfüggő képfeldolgozás. A szöveges chat a meglévő history/context ágat használja.

Regressziós ellenőrzés: **42 AI- és HTTP-teszt sikeres** a rögzített Docker-függőségekkel. Lefedés: egy kép, több kép teljes és sorrendtartó továbbítása, változatlan prompt, kizárt előzmények, thinking tiltás, részleges hiba utáni folytatás, üres válasz, időtúllépés, teljes kudarc, képenkénti időkorlát, változatlan szöveges előzmény- és kontextuskezelés, korábbi feltöltési és kontextuskeret-tesztek.

Élesítés utáni teljes HC → gateway → Ollama próba: két generált kép (piros, majd kék), ugyanazzal a prompttal és szándékosan eltérő színt említő régi előzménnyel. A `qwen3-vl:4b` HTTP 200 választ adott, `partial: false`, az eredmény helyesen `1. kép: piros`, `2. kép: kék`, 4824 ms modellfeldolgozási idővel. A két válasz egyetlen assistant üzenetben szerepel.
