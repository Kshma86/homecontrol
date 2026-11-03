# HC_BRINGUP — natív roverkapcsolat, csak olvasás

2026-10-11: az aktuális rover `esp-hc-bringup-20261010` /
`stm-hc-bringup-20261010`, natív HTTP 3.1.0 `HC_BRINGUP` módban.
Forrás: `HC_AI_SZERVIZ_ATADAS_20261010.md` és a
`hc-rover-bringup-20261010.zip`-ben lévő `HC_AI_BRINGUP_ATADAS_20261010.md`.
A régi LAN2/FIRST_INSTALL_SERVICE átadás történeti; nincs automatikus fallback.

## Kapcsolat

- Backend: `MOWER_V3_REMOTE_URL=http://192.168.1.119`.
- A meglévő privát `ROVER_API_TOKEN_FILE` adja a Bearer-hitelesítést.
  Nincs új token, böngészőtoken, MQTT vagy új WebSocket.
- `MOWER_V3_READ_ONLY=1` az aktuális telepítésben: parancs/STOP, kézi
  kapcsolat és natív firmware create/image/abort/finish backendoldalon is
  tiltott, még kezelői bejelentkezés után is. Nincs rover-I/O vagy tartós
  frissítési szándék létrehozása az elutasított műveletből.
  Operatív firmware-re váltáskor ezt csak külön, tudatos üzembe helyezési
  feladatban szabad megváltoztatni; kompatibilitásból nem kapcsoljuk át.
- A böngésző csak GET `/api/mower/v3/bringup/snapshot`-ot használ, no-store.
  Backendben négy fix GET: `/api/v3/identity`, `/state`, `/update`, `/health`.
  3 s/kérés, legfeljebb 8192 bájt, szigorú JSON, tiltott proxy/redirect.
  Csak ellenőrzött mezők jutnak a böngészőbe; hibaválaszok törzse nem.
- Megosztott activity lock és tartós HC-frissítési guard megmarad.
  A natív METADATA_ERROR lock nem kerüli meg a HC megőrzött session-kapuját.

## Mit mutat a Mower tab?

Alapértelmezés a **HC Bringup — csak olvasás**. Csak a kiválasztott nézet
mountol/pollol. Külön kiválasztható a HC-draft editor, a történeti LAN2
szerviznézet és a megőrzött üzemi adapter. A mostani read-only telepítés az
üzemi nézet vezérlőit is tiltja. Legacy és RTK Editor változatlan.

- Valódi ESP/STM firmware, boot, STM state/source_seq/state_seq/epoch,
  source-valid/age. STM-frissességi határ 1500 ms a későbbi GET-ek várakozásával,
  HC monotonic és böngészőidővel együtt. Azonos source_seq nem fiatalít;
  korábbi sorszám, változó azonos sorszámú evidencia vagy visszalépő epoch
  nem friss. Új boot új kötés, uint32 wrap megengedett.
- Nullable safety és hex fault_mask csak az elkülönített, pontos
  HC_BRINGUP diagnosztikai sémában elfogadott. Az üzemi STATE/updater
  validatorok és VG ABI2/release kapuk nem lazultak.
- `DISARMED / EMPTY` STM-diagnosztika, nem mozgásengedély. A `stopped=false`
  nem mozgásmérés: nincs fizikai VESC-megállási bizonyíték. A safety/szenzor
  nullok ismeretlenek maradnak. Stale/kieséskor az aktuális mezők ismeretlenek.
- Wi-Fi/RSSI/heap/deadline/UART, valamint task/stack részletek. A hálózati
  health-forrás 3000 ms után helyben lejár; ismételt published_ms nem fiatalít.
- Updater: valódi `locked=true / ERROR / METADATA_ERROR / can_finish=false`.
  Nincs loader/session-metaadat; nincs feloldás, bootstrap, session vagy reset.
- Minden rover-módosító képesség false, `hardware_qualified=false`.
  A compatible=true kizárólag protokollegyezés. HC-draft nem rover-APPLIED.

## Ellenőrzés a HC-projekt gyökeréből

```sh
python3 -B scripts/check_mower_v3.py --url http://127.0.0.1
```

Az alapértelmezett és a `--bringup` ugyanazt a csak GET bringup riportot
adja. `--service`: történeti LAN2. `--operational`: megőrzött üzemi
snapshot/operator/releases ellenőrzés. A `--url` a **HC** címe, nem a roveré.
Nincs login, token a parancssorban, írás, STOP-próba vagy automatikus retry.
A 0 kilépési kód a riport lefutását jelenti, nem üzembe helyezési minősítést;
a `stm_fresh` / connection / update_error külön ellenőrzendő.

Mock tesztek a ZIP-ből változatlanul átvett, titokmentes
`tests/fixtures/mower_hc_bringup_20261010.json` GET-mintákat használják.
Nem tesztfixture telepítése a roverre. A backend/SSR tesztek külön ellenőrzik
a lock melletti olvasást, boot/seq/epoch/age/kiesés kezelést, titokszűrést és
a read-only tiltást; nem küldenek módosító kérést éles hardverre.

## Telepített ellenőrzés — 2026-10-11

Backend/frontend újraépítve és újraindítva, más szolgáltatás/rover újraindítása
nélkül. 233 backendtesztből 218 sikeres, 15 opcionális PostgreSQL-teszt
kihagyva; 59 frontendteszt és Vite build sikeres. A meglévő npm audit
1 moderate / 4 high figyelmeztetése külön dependency-feladat, nem lett módosítva.

Valódi HC backend, frontend és proxy GET egyaránt BRINGUP_CONNECTED / friss
STM. Két egymást követő proxy-minta azonos ESP/STM booton növekvő
source_seq (16495 → 16499), 248 ms effektív forráskor. DISARMED, Wi-Fi él,
METADATA_ERROR zárolás és can_finish=false megmaradt. Új JS-csomag a proxyn
kiszolgálva, read-only gate és üzemi controls_disabled igazolt. HC health:
DB/MQTT OK. Sem STOP, sem más roverírás/reset nem történt. Boot/sorszámok
futásidejű megfigyelések, nem konfigurációs konstansok vagy minősítések.
