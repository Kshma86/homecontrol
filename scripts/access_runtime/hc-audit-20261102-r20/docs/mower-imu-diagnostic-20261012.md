# MOTOR_TEST IMU_STALE – élő HC ellenőrzés, 2026-10-12

Csak GET műveletek történtek; nem küldtünk ARM-ot, resetet vagy motorparancsot.

## Bizonyíték

Két korábbi kezelői ARM kérés natív STM eredménye REJECTED / IMU_STALE:
`hc3-mv5no7j9-bnq0n3u81b6`, `hc3-mv5nox9c-ah5yu8if1wv`.
Az ESP boot E5710BF205F9F94F, STM boot AA472FB126D1C12E változatlan.
A konfiguráció revision 1, CRC 27384620, RCP2/ERPM, ACTIVE + applied=true.
A STATE friss, DISARMED, stopped=true, fault_mask=0.

Három health mintában WiFi és STM peer él. Az IMU task cycles
623858 → 624431 → 625005, task age 12 → 10 → 8 ms.
Az imu_resets végig 1; sensor_mailbox_drops, uart_input_errors,
uart_tx_expired, uart_rx_faults végig 0. A task futása önmagában nem
szenzormérési bizonyíték. Az imu service_misses számláló
122335 → 122458 → 122571, okát a health adatból nem lehet megállapítani.

A csomag shared/rover_control.h r3_control_imu kapuja
r3_sample_fresh(..., 250U) hiányára ad IMU_STALE hibát. Tehát az STM
nem rendelkezik elfogadható, legfeljebb 250 ms korú IMU mintával.
Az általános HC/STATE frissessége ettől független.

## Következő roveroldali ellenőrzés

A csomag ROVER_SYSTEM_SPEC_v3.1.0.md szerint BNO086, I2C 0x4B,
ESP SDA GPIO8, SCL GPIO9, INT GPIO10, RST GPIO11. Tervezett rotation-vector
riport 50 Hz, ESP → STM legfrissebb orientáció 20 Hz, eredeti mérési idővel.

Ellenőrizendő: valódi I2C inicializáció és report-enable eredmény; fogadott
rotation-vector riportok számlálója, sorszáma és kora; sensor epoch/current
profile-mount alkalmazás; UART IMU küldési/fogadási sorszám és STM sample age.
A health API nem adja meg ezeket a konkrét mérési bizonyítékokat.
A megpróbált GET /api/v3/pose nem szolgáltatott használható választ;
ebből nem következtetünk szenzorhibára. A csomag és a HC workspace nem
biztosítja a teljes élő ESP BNO086 driver/sketch forrását vagy a board
USB diagnosztikáját. Így I2C/szenzor és IMU-adattovábbítás között jelenleg
nem lehet bizonyíték alapján dönteni. Firmware- vagy hardvermódosítás nem történt.
