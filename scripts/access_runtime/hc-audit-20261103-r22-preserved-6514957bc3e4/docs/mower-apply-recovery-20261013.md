# MOTOR_TEST Apply egyeztetési javítás – 2026-10-13

A HC megtartotta a korábbi, másik boothoz kötött Apply kérés zárolását.
Az ismételt kérés BUSY / „Korábbi Apply egyeztetése vagy a kézi kapcsolat
lezárása szükséges” választ kapott. A böngésző a visszautasított új kérés
korrelációját törölte, de a szerveren maradt régi kérését nem ismerte,
ezért nem kínált használható egyeztetést.

A naplóban azonosított régi kérés: hc3-mv5op5y2-hzx3b8ttwu,
ESP 91A8A1DA90FA6C86 / STM E35C35B981E287A4, várt revision 2,
CRC 27384620. A jelenlegi bootok eltérnek; a rover a korábbi revision 1-et
állította vissza natív ACTIVE/APPLIED állapotba. A HC draft revision 9.

Javítás:

- A HC Apply ledger tartós privát JSON-ba kerül, atomikus cserével; a
  mutáció előtt mentett szándék megmarad backend-újraindításkor is.
- BUSY válasz és hitelesített status GET visszaadja a konkrét függő
  korrelációt. A böngésző ezt megőrzi, megjeleníti, és GET-tel egyezteti.
- Friss, pontos request/revision/CRC ACTIVE/APPLIED boot-restore esetén
  a kérés valóban APPLIED-ként egyeztethető az új natív bootpár mellett.
- Másik boothoz tartozó, nem alkalmazott kérés csak friss natív,
  megállt DISARMED, üres lease, előző ACTIVE/APPLIED revision,
  nem busy és can_apply állapot mellett lesz CANCELLED / BOOT_CHANGED.
  Ez nem hamis alkalmazási siker. Az újraindítás után nem folytatható
  régi kérés HC-zárolását oldja, roveroldali művelet nélkül.
- Azonos boot, PENDING/FAULT, stale adat vagy eltérő korreláció marad
  UNKNOWN és tiltott. Nincs erőltetés, NVS-törlés, automatikus POST,
  ARM vagy kézi claim. A draft változatlanul megmarad.

Ellenőrzés: 249 backendteszt (15 környezeti skip), 71 frontendteszt,
sikeres build. Valós roverre Apply/motorparancsot a javítás közben nem küldtünk.

Kihelyezés után a rover átmenetileg nem volt elérhető, ekkor az UNKNOWN
zárolás megmaradt. A kapcsolat helyreállása után hitelesített GET-egyeztetés:
CANCELLED / BOOT_CHANGED, pending_apply=null; friss DISARMED, can_apply=true,
natív ACTIVE/APPLIED revision 1. A tartós ledger pending mezője null,
a HC draft továbbra is revision 9. Új rover Apply nem történt.
