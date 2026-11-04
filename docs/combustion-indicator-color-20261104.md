# HC jelzőlámpa színjavítás – 2026-11-04

A felhasználó szerint a lámpa a zöld jelzés 60 másodperces ritmusában sárgán
villogott. Az élő HC állapota `green`, konfigurált színe `#00ff00`, fényereje
50 volt. A Zigbee2MQTT XY visszajelzése zöldet mutatott (`x=0.1724`, `y=0.7468`),
így a visszajelzés önmagában nem igazolta a látható fény színét.

Az izzó `CK-BL702-AL-01(7009_Z102LG03-1)`, IEEE azonosítója
`0xe8ca50e272a90000`. A telepített meghajtó csak XY módot engedélyezett;
a HS formátumú MQTT parancsot is XY Zigbee paranccsá alakította. A készülék
jelentett színképességei a natív HS vezérlést is tartalmazzák.

Az `infra/zigbee2mqtt/hc-indicator-native-hs.cjs` az upstream meghajtót örökli,
kizárólag erre az IEEE azonosítóra illeszkedik, és a színparancsokat natív
`moveToHueAndSaturation` parancsra alakítja. A fényerő, kapcsolás és a HC
védelmi döntései külön, változatlan vezérlést kapnak. A szinkronizált XY
visszajelzés megmarad a HC visszaellenőrzése számára.

A meghajtó a `zigbee/bridge/request/converter/save` API-n betöltve,
`status=ok` válasszal. Tartós futási példánya:
`infra/zigbee2mqtt/data/external_converters/hc-indicator-native-hs.cjs`.
Nem kellett szolgáltatást újraindítani vagy a védelmet kikapcsolni.

Ellenőrzés: négy teszt sikeres, lefedik a célzott illesztést, a zöld/narancs/piros
HS parancsokat, az XY visszajelzés megőrzését és a fényerő érintetlenségét.

```sh
docker exec -i -e HC_INDICATOR_CONVERTER=/app/data/external_converters/hc-indicator-native-hs.cjs zigbee2mqtt node - < infra/zigbee2mqtt/test-indicator-native-hs.cjs
```

Az élő, színparancs utáni visszajelzés: `state=OFF`, `color_mode=hs`,
`hue=120`, `saturation=100`, `brightness=50`. Az elszívó a betöltéskor már
`idle` állapotú volt, ezért rendes villanást ekkor nem lehetett megfigyelni.
A látható szín javulásához még felhasználói visszaellenőrzés szükséges.

Visszaállítás: a `zigbee/bridge/request/converter/remove` API-n
`{"name":"hc-indicator-native-hs.cjs"}` kérés eltávolítja a futási példányt
és újra az upstream definíciót választja ki, újraindítás nélkül.
