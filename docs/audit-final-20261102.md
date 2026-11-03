# Audit javítási kör – éles átadás, 2026-11-03

Aktív: **hc-audit-20261103-r22**. A HC-15/16/20/23/24/26 javításai élesek.
A backend, mDNS és Growatt-poller új image-en fut; a többi konténer megőrzött.
Mind a 805 runtime-forráshash egyezik, az öt timer aktív,
a komponensek állapota és az AI-tiltás/routeres mentés ellenőrzött.

Friss helyi/HC/Git/router mentés és külön PostgreSQL-restore sikeres.
Run: `7a6236e4b0a5472a8566024665ffc619`; snapshot: `08acafbc0721e29c85997a3f12298f81fe0b28c088fd3b494adf3f58bc2b5d45`.
A pontos nyugták: `backups/releases/hc-audit-20261103-r22/evidence/post-live-check.json`
és `router-live-acceptance.json`. A lezárt csomagot és korábbi bizonyítékokat nem írtuk át.

**A jelenlegi javítási kör átvétele lezárva: 46 Ellenőrzött; HC-41 és HC-43 Folyamatban.**
HC-41 az ESP MQTT-jelszó migrációja miatt, HC-43 a felhasználó döntése szerint a gyártói
javításig marad nyilvántartva. Ezeket nem minősítjük javítottnak. Az AI tiltva marad.
A korábbi ellenőrzött r18 recovery-jelölt teljes friss/ismételt/reboot próbája megmaradt;
ez nem új r22 bare-metal VM-próba. Az új kiadás friss mentésének SHA-256/PG-restore átvétele sikeres.

Rollback csak ugyanennek vagy az előző kiadásnak az aktív állapotából:

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-audit-20261103-r22/source/scripts/audit_release/activate.py rollback
```

A visszagörgetés az r18-at állítja vissza. Későbbi kiadásról a guard elutasítja.
A privát csomagtartalom nem megosztható. Újraaktiválást sikeres csomagon nem ismétlünk.
