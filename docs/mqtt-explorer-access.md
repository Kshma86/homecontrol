# MQTT Explorer – előkészített megfigyelői hozzáférés

**Aktuális állapot, 2026-10-31: az új brokerprofil éles, az alábbi SSH-alagút és
jelszavas kapcsolat most használható.** A fejlesztői PC-n a tényleges reconnect
még ellenőrizendő. Az eredeti privát profil Explorer- és dashboard-jelszava
megegyezik az élesített kiadás credentialjével; nem kell új jelszót generálni.
A profil `active=false` értéke történeti előkészítési jelző.
[Éles átadás](../backups/deployments/hc-access-20261030-r10/DEPLOYMENT.md).
Az alábbi 2026-10-30-i státuszbekezdések történetiek; a kapcsolódási mezők aktuálisak.

2026-10-30. **Előkészítve, nincs élesítve.** A jelenlegi Explorer-kapcsolatot
még ne írd át. Az új profilt a HC-41 átállásakor lehet aktiválni; a broker,
az ESP-kivétel hálózati szűrése és a kliensátadás még külön élesítési feladat.

Az Explorer saját felhasználója **`hc_explorer`**, külön jelszóval. Csak
megfigyelésre használható: `homecontrol/#`, `zigbee/#`, `$SYS/broker/#` olvasható.
Parancsot, telemetriát és retained állapotot sem írhat, törlésre sem jogosult.
A dashboard saját hozzáférése ettől külön marad.

## Kapcsolódás az éles átállás után

A fejlesztői PC termináljában indítsd el az SSH-alagutat:

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:21884:127.0.0.1:1884 a@192.168.1.133
```

A terminál maradjon nyitva. Ha a dashboard miatt ez az alagút már fut, ugyanazt
használhatja az Explorer is; a 21884-es porthoz nem kell második alagutat indítani.
Az SSH a szokásos HC-belépésedet használja, nem az MQTT-jelszót. A HC címét és a
parancs helyi konfigurációját ellenőriztük, tényleges PC→HC SSH-próba nem történt.

Az Explorerben hozz létre új kapcsolatot a meglévő profil megtartásával:

| Mező | Érték |
|---|---|
| Név | HC – megfigyelés (SSH) |
| Protokoll | MQTT / `mqtt://`, TCP |
| Host | `127.0.0.1` |
| Port | `21884` |
| Felhasználónév | `hc_explorer` |
| Jelszó | A privát profilfájlból, lásd alább |
| MQTT-verzió | 5.0, ha a használt kliens támogatja; a meglévő 3.1.1 is használható |
| MQTT TLS | Kikapcsolva ennél a profilnál; az átvitelt az SSH-alagút védi |
| Feliratkozások | `homecontrol/#`, `zigbee/#`, `$SYS/broker/#` |

A kliens általános `#` feliratkozását is a broker olvasási ACL-je korlátozza;
az Explorer Publish felülete nem ad írási jogot. Kézi vezérléshez később külön
engedélyezett profil szükséges, a megfigyelői jelszóval nem vezérelhető eszköz.

## A privát profil helye

A HC-n elkészült privát jelöltcsomag:

```text
/srv/docker/homecontrol/backups/mqtt-access/hc41-20261030-explorer/mqtt-explorer.connection.json
```

A fájl tartalmazza a külön Explorer-jelszót és a kézzel beírható mezőket.
**Ez mezőreferencia, nem ellenőrzött alkalmazásimport-formátum.** A profil 0600,
a szülőcsomag 0700 jogosultságú; a broker jelszóadatbázisa már hash-elt.
Az `active=false` az előkészített állapotot jelzi. A jelszó nincs a dokumentumban,
auditnaplóban vagy a chatben. Csak az Explorer saját hozzáférése adható át a PC-re,
a teljes credentialkönyvtár és broker-jelszóadatbázis nem.

A csomag nincs bekötve az éles brokerhez. A kiadási csomag véglegesítésekor ezt
a hozzáférést meg kell őrizni, vagy az új privát profilból újra át kell adni;
egy másik jelölt generálása önmagában nem módosít élő jelszót.

## Ellenőrzés

15 hitelesítési/profil/csomagvédelmi unit teszt és **15 valódi, elkülönített
brokerforgatókönyv** sikeres. A brokerfutás a korábbi 14 esetet is megismételte,
és kiegészült az Explorer MQTT5-próbájával; ezek nem összeadandó darabszámok.
Mind a 11 szerepkör kapcsolódott. Az Explorer valódi MQTT5 kliensként olvasta
a retained öntözési és Zigbee-állapotot; öt különböző parancs-/telemetria-topicra
QoS1 retained írást megkísérelve a broker minden esetben `Not authorized`
PUBACK-ot adott (135), a megfigyelő backend nem kapta meg az üzeneteket.
A profil jelszava különbözik a dashboardétól.

A labor network=none volt, nem kapott Docker-socketet, nem volt publikált port
és éles üzenet. Az Explorer grafikus alkalmazása és a PC SSH-alagútja nem vett
részt a próbában. A célzott változás nem igényelte az előző teljes backend-suite
újrafuttatását; annak korábbi 422 tesztje külön, történeti bizonyíték.

[Gépi eredmény és diff](audit-evidence/hc41-explorer-20261030/summary.json),
[teljes HC-41 átállási terv](hc41-staged-mqtt-auth.md).
