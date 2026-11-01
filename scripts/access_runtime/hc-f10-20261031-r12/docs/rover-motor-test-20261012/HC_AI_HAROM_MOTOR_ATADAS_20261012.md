# HC átadás – három motor, közvetlen eRPM és kalibrált hajtás

Kiegészítés: a külön feltölthető, felügyelt tesztkiadás aktuális szerződését
[MOTOR_TEST átadás](HC_AI_MOTOR_TEST_ATADAS_20261012.md) írja le. A lentebbi
normál/éles telepítési korlátok továbbra is érvényesek; az explicit tesztüzem
nem commissioning és nem loader/OTA-telepítés.

2026-10-12. Ez a roveroldali forrásbővítés szerződése, nem telepítési vagy
mozgási engedély. A működő HC-projekt másik gépen marad; itt nem módosítottuk.
A korábbi 3.1.0 identity/STATE/STOP/update szerződést nem értelmezzük át.
A jelenleg a boardokon lévő HC_BRINGUP továbbra is csak olvasható.

## Mi változott?

Az ESP hitelesített `/api/v3/manual` WebSocketjében új, explicit `drive_erpm`
üzenet van, amely az STM `MAN_ERPM` ágára jut. A három motor a meglévő sole
CAN-kimeneti tulajdonoson, közös lease/deadman/STOP/fault védelemmel működik.
Mindhárom motorhoz külön eRPM-rámpa van. A harmadik motor ugyanúgy vezérelhető;
a `blade_enabled=true` adat itt a harmadik motor engedélye, **nem** felszerelt
késpenge vagy biztonsági minősítés. Ezt a felhasználó kés nélküli tengelypróbához kérte.

Az RCP1 byteformátuma és 27-mezős JSON-ja változatlan. Az új **RCP2** 31 mezős,
verziózott konfiguráció, ugyanazon `/api/v3/parameters` tranzakciós API-val.
Az UART CFG ABI most **2**: a régi ABI1 peer nem jelenthet RCP2-képességet.
A loader/RFU2/update szolgáltatás ABI-ja ettől független. A telepítési R3Profile,
a 1284-byte-os régi trial capsule és a VG/RTE átadási rekord változatlan méretű;
az új motoradatok külön futásidejű struktúrában élnek.

## HC capability és session

- `identity.parameter_versions_supported`: `[1,2]` a codec támogatása.
  Ettől még `runtime_parameters=true`, friss `can_apply` és érvényes telepítés kell.
- `identity.manual_erpm=true` csak friss konfigurációs szolgáltatás, kompatibilis,
  nem update-locked session és aktív ERPM-profil mellett jelenik meg. Ez nem ARM
  vagy minősítés: a natív STM további belépési ellenőrzései döntik el az engedélyezést.
- WebSocket subprotocol változatlan: `homecontrol.mower.manual.v3`.
  A hitelesítés továbbra is backendoldali, nem böngészőbe másolt token.
- A claim üzenet változatlan. Csak valódi APPLIED/MANUAL ACK után van lease;
  nincs automatikus ARM, reconnect-reclaim vagy mozgás-visszajátszás.
- A `claimed` válasz kiegészül `drive_mode` (`ERPM` vagy `METRIC`) és
  `motor_erpm_limits:[bal,jobb,harmadik]` mezőkkel. `lease_ms=350` változatlan.
- Ismeretlen/false capability, hibás/stale boot/epoch, nem APPLIED claim vagy
  zárt telepítés mellett nem küldünk motorparancsot, nem váltunk legacy vezérlésre.

ERPM-módú bemenet (a számok kizárólag üzenetpéldák, nem motorindítási utasítás):

```json
{"type":"drive_erpm","lease_id":123,"control_epoch":7,"seq":1,"left_erpm":100,"right_erpm":100,"third_erpm":200,"deadman":true}
```

Mindhárom target előjeles int32. További/ismeretlen kulcs hibás. A backend
korlátozza őket az aktív roverlimitekkel; az ESP és STM önállóan is ellenőrzi.
Az STM oldalon `wheel_direction`/`blade_direction` csak külön, szándékosan
beállított roveroldali előjel. A VESC `m_invert_direction` nem másolandó ide:
ID1 már invertált, ID2/ID3 nem; második, automatikus invertálást nem vezetünk be.

A megszokott `stop` és `release` formátum marad. `stop` ERPM-módban mindhárom
motor célját nullázza, `deadman=false`; nem csak a kerekeket. `deadman=false`
nem nulla targettel hibás és megszünteti a lease-t. A globális STOP/DISARM,
kapcsolatvesztés, IMU-vesztés/dőlési FAULT és update maintenance is tiltja a kimenetet.
Nulla cél bypassolja a rámpát; irányváltás először nullára megy. Nincs mechanikai
RPM-re vagy mm/s-ra címkézett eRPM. ERPM-módban nincs autonóm START.

## RCP2 paraméterek

Az alap 27 kulcs megtartva, `parameters_version=2`, négy új kulcs:

| Kulcs | Érték / jelentés |
|---|---|
| `drive_mode` | `ERPM` vagy `CALIBRATED` |
| `wheel_electrical_ratio_milli` | [bal,jobb], elektromos fordulat / kerékfordulat ×1000, 0..100000000; kalibrált módban mindkettő legalább 1000 |
| `motor_accel_erpm_s` | [bal,jobb,harmadik], külön rámpa 1..100000 eRPM/s |
| `blade_brake_ma` | harmadik motor STOP-fékezőárama 0..2147483647 mA; a motor/VESC tényleges korlátját külön ellenőrizni kell |

RCP2-ben a külön `wheel_motor_pole_pairs` és `wheel_gear_ratio_milli` mezők
mindig `[0,0]`: a mért összesített tényező helyettesíti őket. Nem írunk be 7
póluspárt vagy 2,769-es áttételt pusztán egy nem ellenőrzött VESC Info-mezőből.
ERPM-módban a megadott geometria/antennaadatok megtarthatók, de a nem használt
metric/autonóm mezők kanonikus nulla értéket kapnak:
`blade_pole_pairs`, `blade_rpm_limit`, `max_slope_mdeg`,
`stop_deceleration_mm_s2`, `stop_test_max_ms`, `max_linear_mm_s`,
`max_yaw_mdeg_s`, `accel_mm_s2`, `yaw_accel_mdeg_s2`,
`gnss_hacc_limit_mm`, `heading_accuracy_limit_mdeg`.
Ez **nem** nulla fizikai megállási idő vagy végrehajtott stopmérés: a funkció
nem elérhető. A nyers mód megállási megfigyelése friss, pontosan nulla eRPM-et
kér mindkét keréknél folyamatos 300 ms, és engedélyezett harmadik motornál
folyamatos 1000 ms alatt; ettől nem lesz önálló hardveres megállási minősítés.

Az IMU beépítési kvaterniója, a dőléslimit és az eRPM-/fékezési/rámpalimitek
ERPM-módban is szükségesek. A motor3 engedélyezhető ismeretlen pólusszám mellett,
mert ebben a módban elektromos fordulatszámot kérünk, nem mechanikai kés-RPM-et.
CALIBRATED módban a metric/stop/GNSS adatokat a teljes validátor ellenőrzi;
letiltott harmadik motorhoz a mechanikai póluspár/RPM mezők nullák lehetnek.

Adatforrás: `config/rover_three_motor.draft.json`. **Hiányos draft**, nem aktív
vagy feltölthető beállítás: null mezőkkel az encode/APPLY helyesen elutasítja.
`blade_enabled=true` felhasználói kérés; irányok +1 azt jelzik, hogy nem kívánunk
további roveroldali invertálást, tényleges előremenetüket még ellenőrizni kell.
6000/6000/25000 eRPM a régi roverlimitek, nem az exportált VESC ±100000-es
plafonjának átvétele. A kerület 650 mm a megadott gördülési adat; a 207 mm
VESC-átmérő ennek kerekített megfelelője. IMU-kalibrációt nem találunk ki.

Referencia: `tools/rover_parameters.py` check/canonical/encode/decode támogat
RCP1-et és RCP2-t. Az eredeti `schema` parancs továbbra is csak RCP1;
RCP2-nél a teljes codec-validátor és e dokumentum az irányadó.
RCP2 bináris: 256 byte, `RCP2` magic, uint16 verzió 2; régi mezőoffsetek maradnak;
152: mode uint8 (1/2), 153–155: nulla; 156/160: kerékarányok u32;
164/168/172: rámpák u32; 176: motor3 fék u32; 180–251: nulla;
252: CRC32. RCF1/NVS rekordja változatlanul 512 byte, benne explicit verziózott payload.
Régi peer/frissítési hash/profile-CRC nem írható át runtime-CRC-re.

## Exportokból megállapított állapot

CAN 1/2/3, 500 kbit/s VESC-mode; STATUS1–4 50 Hz; mindhárom timeout 1000 ms,
timeout-fék 0 A. UART App engedélyezve. A motor- és app-exportokat csak olvastuk;
a VESC firmware/config nem változott itt. A 207 mm beállítást a felhasználó jelezte,
a korábbi motor-export még 83 mm-t tartalmazhat. A VESC Tool csatlakozása alive
üzenetekkel befolyásolja a timeoutpróbát; ne tekintsük így végzett próbát igazoltnak.

## Nyitott telepítési akadályok – ne jelenjen meg „működő kézi üzem”

- A jelenlegi boardokon a read-only HC_BRINGUP van. Nem történt ebben a munkában
  feltöltés, motorindítás vagy hardveres próba.
- A telepítési/factory profil és a loader/CAN-stop minősítés még nincs kész;
  a normál ESP startup/updater kapuja zárt. Ezt nem írjuk át hamis unlocked IDLE-ra.
- A natív `RoverV3ControlInputs.deployment_verified` továbbra is 0; a runtime
  paraméteralkalmazás továbbra sem állít `commissioned=true` bitet. Ezek tényleges
  telepítési/admission bekötése nélkül az új hárommotoros ág sem enged ARM-ot.
- A standalone LEGACY alkalmazásban a natív konfigurációs megállási bizonyíték
  nincs bekötve; az új codec nem oldja meg önmagában az első konfiguráció telepítését.
- Kés nélküli tengelypróba nem igazolja a kés későbbi felszerelésével járó működést.
  Ehhez külön helyi megállási/biztonsági ellenőrzés kell.

Következő roveroldali munka: a valódi telepítési/tesztüzemi admission és az első
konfigurációs belépés rendezése, aztán helyi, mozgásbiztos első próbák. A mostani
fordítások forrás-/codec-/natív fordítási ellenőrzések, nem kiadási jóváhagyások.
