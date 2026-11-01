# HC AI átadás — a tényleges elsőindítási szervizhez

**Újabb, ténylegesen telepített kiadás:**
[`HC_AI_BRINGUP_ATADAS_20261010.md`](HC_AI_BRINGUP_ATADAS_20261010.md).
Most már a normál natív R3/HTTP API olvasható a routeres LAN-on, HC_BRINGUP
módban, továbbra is mozgás és távoli frissítés nélkül. Ez a service leírás
az előző LAN2 kiadás történeti átadása, nem a most futó endpointok listája.

**Legújabb operátori irány: helyi Wi-Fi kliens, csak beállításra AP.**
Először olvasd: [`docs/HC_ROVER_LAN_BACKEND_20261010.md`](docs/HC_ROVER_LAN_BACKEND_20261010.md).
A működő HC v3.1/VG ABI2 HTTP-adapterét nem kell új rendszerre cserélni;
ennek kódját/validatorait kérjük a roveroldali illesztéshez. Az állandó AP-s útmutató
korábbi állapot; a HC most a rover LAN-címére csatlakozik.

**Ezt olvasd először.** A 2026-10-10-es éles CAN-maintenance átadás továbbra is
a későbbi célrendszer szerződése. A kezelő most kifejezetten egy korlátozott,
feltölthető elsőindítási kiadást engedélyezett. Annak API-ja külön:
[`docs/ROVER_FIRST_INSTALL_SERVICE.md`](docs/ROVER_FIRST_INSTALL_SERVICE.md).

**A mostani HC-kapcsolódási feladat pontos, önálló leírása:**
[`docs/HC_ROVER_CONNECT_NOW_20261010.md`](docs/HC_ROVER_CONNECT_NOW_20261010.md).
Ebben van a hálózati/backend bekötés, a 27-mezős séma, minden kérés/válasz,
hibakezelés és a késznek tekintés feltétele. A valódi, hitelesített HTTP GET
kapcsolódást a korábbi dev8/AP kiadáson Wi-Fi-n is ellenőriztük;
ez nem az új LAN-kapcsolat bizonyítéka. Paraméter-POST még nem történt.

A LAN célkiadás `esp-service-20261010-lan2`, STM `service-20261010`.
Csak a beállító AP `Rover-Setup-6087EC`: `http://192.168.4.1/`, fejlesztői
jelszó `rover123`; a service API kizárólag a LAN-címen használható.
A változatlan Bearer-token nincs ebben
a csomagban; a tulajdonos külön adja meg a HC helyi titoktárolójának.
Az éles HTTP paraméter-APPLY / update API nem válaszolhat sikerrel ezen a képen.

HC most implementálható:

1. Szerviz állapotlap: friss STM UID, parkolás, tiltott mozgás, firmware-azonosság.
2. Teljes RCP1-paraméter szerkesztő a meglévő séma szerint, tetszőleges valódi
   értékekkel; a null sablon nem működő alapbeállítás. Ne töltsön tesztfixture-t.
3. Mentés: `service_abi=1`, friss `stm_uid`, GET-ből származó
   `expected_revision`; 202 után állapotkövetés, végül pontos paraméter/readback
   egyezés és nőtt revízió. `STAGED_NOT_APPLIED`, nem ACTIVE/APPLIED.
4. Induláskor mentett paraméterek beolvasása. `applied=false` és
   `motion_permitted=false` mindig látható, soha ne legyen ARM/motor gomb.
5. Későbbi éles migráció külön üzemmód/feladat, nem automatikus bitátállítás.

Referenciakliens:

```sh
python3 tools/rover_hc_service.py status --url http://rover-6087ec.local --access PRIVATE_ACCESS_JSON
python3 tools/rover_hc_service.py get --url http://rover-6087ec.local --access PRIVATE_ACCESS_JSON
python3 tools/rover_hc_service.py stage --url http://rover-6087ec.local --access PRIVATE_ACCESS_JSON --parameters REAL_PARAMETERS_JSON
```

A `stage` kifejezett művelet; a kliens nem ismétli meg a POST-ot ismeretlen
eredménynél. Nincs titokirányítás HTTP-átirányításon/proxyn keresztül.
USB diagnosztika: `tools/rover_service_probe.py`. A fizikai VESC firmware változatlan.
F9P/IMU/NTRIP és éles frissítés ebben a szervizkiadásban még tiltva vannak.

Ne téveszd össze a host teszteket és a sikeres boardindulást az éles
hardverminősítéssel. A szervizből a későbbi VG root/RFI2/APP/NOR telepítéshez
valódi telepítési és mért stop/watchdog/táp adatok továbbra is szükségesek.
