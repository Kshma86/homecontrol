# HC-45 KVM-bizonyítékok – 2026-10-30

A `summary.json` az aktuális eredmény. A friss/ismételt és valódi mentésből végzett
restore külön JSON; a `first-reboot-failure.json` a javítás előtti sikertelen
rebootot rögzíti. A végleges eredmény az `after-reboot-probe.json`,
`reboot-result.json` és `fixed-network-boot.json`. Az `unit-rollback.json` egyetlen
injektált enable-hibakód mellett végzett tényleges systemd-visszagörgetés.
A host-végrehajtó restart-/crash-próbái és a vendég saját Dockerén végzett
backend-restart külön bizonyíték. A fizikai eszközök nem voltak elérhetők.

A megtartott próbascriptek a mérés ellenőrizhetőségét szolgálják; kizárólag
eldobható, `hc-restore-vm` nevű KVM-vendégben használhatók. Nem önálló VM-telepítő
csomag, a privát fixture/bundle és kulcsmásolatok a próba végén törölve lettek.
Új futás előtt külön lemez, izoláció, üres OS, saját Docker/systemd, érvényes
mentés és privát age/restic bemenet szükséges. A `vmctl.py` a QEMU-konténer saját
loopback SSH-forwardján dolgozott, host Docker-socket átadása nélkül.
A részletes leltár és bizonyítási határ: `../../hc45-vm-restore-20261030.md`.
A tesztlogok hálózat nélküli, csak olvasható forrást használó saját konténerből
származnak; a tulajdonjogteszt a konténeren belül UID0-t igényel.
