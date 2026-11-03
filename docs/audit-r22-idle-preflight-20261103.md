# r22 – korai robot-kapu és a hiányzó hibanapló javítása

**Lezárás (REPAIR-084): az r22 éles átadása sikeres; a korábbi indítók nem ismétlendők.**
[Aktuális végső állapot és bizonyítékok](audit-r22-live-handover-20261103.md).
Az alábbi előkészítési/hibaállapot történeti.

REPAIR-083, 2026-11-03. Aktív továbbra is **hc-security-20261102-r18**.
Az élesítési engedély érvényes; az audit átadása még nincs lezárva.

A felhasználó elindította a continuation-2 csomagot, amely azonnal `ValueError`
üzenettel megállt. A kiadásjelző és a `deployment-status.json` változatlan;
utóbbi a korábbi, 13:17 körüli `previous_release_restored` állapotot mutatja.
A continuation-2 `private` könyvtára még nem jött létre, így az indító a
`started.json` előtti ellenőrzések egyikén állt meg. Új átállítás nem indult.

Az indító hibája: azt írta, hogy privát naplót őrzött meg, miközben a korai
kivételnél a naplókönyvtár még nem létezett. A kivételkezelő elnyelte az írás
hibáját. Emiatt az eredeti konkrét kivételszöveg utólag nem igazolható.
Ezt az ügynök által készített indító hibásan ígérte; a lezárt csomagot megőrizzük.

Natív, csak olvasó újrafuttatásban a baseline-ellenőrzés pontosan ezt adta:

```text
ValueError: Robot must be idle or charging for the bridge handover
```

A robot először `1` (cleaning_or_room_cleaning), a későbbi ellenőrzéskor `5`
(returning_or_relocating) állapotú volt. A meglévő átadási guard csak `6`
(idle_docked) és `13` (charging) állapotban enged tovább. Ez az újrafuttatásban
igazolt blokkoló feltétel; az eredeti elveszett napló teljes bizonyosságú pótlását
nem állítjuk. A robotnak nem küldtünk parancsot.

Friss éles ellenőrzés: backend `ok: true`, 15 futó konténer, 10 healthy check,
mind a 16 image az r18-é, az öt timer aktív. Az AI tiltott, routeres mentés
engedélyezett. A lezárt continuation-2 összes nyugtázott fájlhashe egyezik.

## A külön operátori indító

`scripts/audit_release/run_r22_when_idle.py` nem új alkalmazáskiadás.
Ellenőrzi a változatlan continuation-2 belépőjének rögzített SHA-256 értékét,
valamint annak teljes elfogadási nyugtáját és az eredeti r22 ellenőrzését.

A korai naplókönyvtárat még a kiadás és a baseline ellenőrzése előtt létrehozza.
Minden hibás kísérlet külön, kizárólag root által olvasható, felül nem írt fájlt
kap; az ellenőrzési fázist és a traceback helyeit is megőrzi. A terminálra csak
ismert, titokmentes ok vagy a kivétel típusa kerül.

Kizárólag a pontos robot-idle guard hibájára vár, legfeljebb két órát,
30 másodperces állapotjelzéssel. Nem irányítja a robotot, és nem ismétli meg
egyéb guardok hibáját. Ha a robot dokkol/tölt és a baseline-kapuk teljesülnek,
egyszer meghívja a változatlan continuation-2 teljes `main()` folyamatát.
Annak minden eredeti kapuja, új elő- és utómentése, restore-próbája és automatikus
rollbackje megmarad. Létező `started.json` esetén az indító elutasítja az ismétlést.

Ez a korai megállás még nem használt el egy megkezdett continuation-tranzakciót:
nincs `private` könyvtár vagy `started.json`. Ez indokolja, hogy a guardok újbóli
teljes ellenőrzése után ugyanaz a lezárt csomag indulhat; nem vak újraélesítés.

**10 új célzott teszt sikeres:** robotvárás és időkorlát, más guard azonnali
elutasítása, megkezdett folyamat ismétlésének tiltása, korai hiba tényleges
naplózása, privát jogosultságok, felülírás/symlink elutasítása, valamint annak
ellenőrzése, hogy hibás kapu mellett nincs aktiválás, jó kapuk után pedig az
eredeti belépő egyszer fut. A korábbi 66 csomagteszt nyugtája változatlan;
ezeket most nem számítjuk újrafuttatottnak.

Bizonyítékok: [éles állapot](audit-evidence/r22-idle-preflight-20261103/native-live-state.json),
[operátori ellenőrzés](audit-evidence/r22-idle-preflight-20261103/operator-validation.json).

A natív indítás `sudo: a password is required` eredménnyel megállt;
az új operátori indító nem futott rootként. Helyi sudo-hitelesítés szükséges.

Aktuális helyi parancs:

```bash
sudo python3 /srv/docker/homecontrol/scripts/audit_release/run_r22_when_idle.py
```

A robot miatti várakozás közben az r18 tovább működik. Az audit állapota:
46 Ellenőrzött; HC-41 és HC-43 Folyamatban. Új teljes VM/bare-metal/reboot
próba nem történt.
