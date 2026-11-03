# R23 indítás – diagnosztika, 2026-11-03

Az ismételt indító `FileExistsError` hibával megállt az `activation-attempt.json`
kizárólagos létrehozásánál. A jelző egy korábbi indításé; nem töröltük.
A systemd naplóban az első worker exit 1 állapota látható; jelenleg nem fut.
A korábbi hiba pontos okának privát naplóbeli megerősítése még hátravan.

Az önálló natív állapotellenőrzés sikeres: aktív r22; az összes 16 konténer
azonosítója/image-e, 805 runtime-forráshash, 25 unitfájl, öt timer és öt
backup-mount rendben. A robot lekérdezése 13-as, töltő állapotot jelzett.
Az r23 823 lezárt forrásfájlja változatlan; élesítést nem ismételtünk.

Az ellenőrzőben ettől külön, reprodukálható hibát találtunk: a lefagyasztott
`mqtt_read_probe.py` 65 536 bájtos korlátja az élő, **197 796 bájtos**, 58 elemes
`zigbee/bridge/devices` választ elutasítja. Az eredeti probe `TimeoutError`-t ad.
A javított, csak olvasó inventory-probe 2 MiB-os üzenetkorláttal, legfeljebb 1024
eszközzel, konkrét topicokkal, IEEE-cím- és duplikációellenőrzéssel sikeresen
olvasta ugyanazt az 58 eszközt. Sem publish, sem eszközvezérlés nem történt.
Öt célzott teszt igazolja a nagy válasz elfogadását, a túl nagy/hibás/hiányos/
duplikált adatok elutasítását és a verziókapu megőrzését.
Ez előkészített folytatási javítás, az r23 lezárt csomagját nem írja át.

A root privát naplóhoz a kezelő helyi sudo-ja szükséges:

```bash
sudo python3 /srv/docker/homecontrol/scripts/container_update/diagnose_start.py
```

Ez csak olvas. Nem töröl jelzőt, nem indít szolgáltatást vagy frissítést.
Csak rögzített hibaosztályokat, engedélyezett traceback-helyeket és állapotokat
ír ki; nyers naplót, parancsargumentumokat, eszközazonosítót vagy titkot nem.
A diagnosztika négy célzott redakciós tesztje sikeres. A kimenet alapján az
eredeti hiba és az átállítás előtti állapot ellenőrzése szükséges a folytatáshoz.

Bizonyíték: `maintenance/container-update-20261103/bounded-inventory-live-probe.json`.
Az eredeti audit és a lezárt kiadások megőrizve. HC-41/43 továbbra is Folyamatban.
