# simplify11 HC integráció

Forrás: HC_AI_EGYSZERUSITES_ATADAS_20261013.md.

Az új identity képességjelzők megmaradnak a HC snapshotban. MOTOR_TEST + test_manual_control + manual_claim_from_disarmed mellett a Kézi mód közvetlenül DISARMED vagy IDLE állapotból kérhető, ARM nélkül. Az összesített stopped nem HC-kapu; a szükséges kerékfeedbacket, IMU-t, dőlést és megállási időt a natív rover ellenőrzi. Régi firmware esetén az IDLE/stopped claim út megmarad.

A WebSocket a claimed válasz új epochját/lease-ét használja. 50 ms ütemben teljes ERPM keretet küld, elengedett deadmannél nulla célokkal. Kapcsolatvesztés, stale állapot és peer-váltás lezárja a lease-t és nullázza a helyi célokat. Nincs automatikus claim/ARM/motor replay. Harmadik motor nélküli lease nulla harmadik korláttal használható, nemnulla harmadik cél nem fogadható el.

A konfiguráció elfogad teljes 31 mezős RCP2 vagy pontosan 10/13 mezős ERPM objektumot. A kompakt változat teljes csere: a bináris CRC-számításhoz az inaktív mezők nullára bővülnek. A régi teljes konfiguráció CRC-je változatlan. A szerkesztő explicit kompakt/teljes átváltást kínál; alapból a HC-ban tárolt teljes objektum marad. A kompakt Apply nem őrzi meg a kihagyott kalibrációt. A régi teljes RCP1 dekódolás, mentés és explicit Apply szintén támogatott.

A necessary_parameters rover-visszajelzés ellenőrzött, és a snapshot része. 202 csak befogadás, az eredmény külön GET-tel olvasható vissza. Nincs automatikus Apply/retry vagy régi tranzakció miatti HC-zárolás.

Az új UART HEALTH mezők láthatók. Folyamatban lévő helyreállítás, zárt port vagy hiányzó peer nem enged kézi módot; a kumulatív helyreállítási számlálók nem tiltanak. A friss natív állapot továbbra is kötelező.

A motorlimit és VESC-minimum nem változott. MOTOR_TEST nem támogat autonóm START-ot vagy távoli firmware-frissítést.

Éles GET ellenőrzés: a HC látja mindhárom új identity jelzőt, a STATE friss DISARMED/hibamentes, a UART port nyitott és nem recovering. A rover konfigurációja az ellenőrzéskor PENDING rev2, CRC27384620, CONFIG_RECOVERY_REQUIRED; test_manual_control=false. Az átadás az automatikus PENDING törlést tiltja, ezért nem történt natív konfiguráció-/ARM-/claim-/motorparancs. Ez tényleges roveroldali helyreállítási állapot, nem visszahozott HC Apply-zárolás. A kézi panel kiírja a natív okot.
