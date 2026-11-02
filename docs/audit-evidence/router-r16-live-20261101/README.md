# A tényleges éles r16 önálló átvétele

A `vm-acceptance.json` az új éles snapshot és a külső Git változatlan bootstrapjének
friss restore-ját, elérhetetlen FTP-s próbáját és rebootját rögzíti. A külön korábbi
candidate-kör a `../ai-ssd-closure-20261101/` alatt marad; az ismételt teljes restore
abban futott. Az új kör nem használt candidate commitot.

A `production-check.json` csak olvasó éles ellenőrzés. A `git-verification.json`
a delegált mirror teljes előzményét vizsgálta a publikus exporter mintáival.
A `lab-cleanup.json` a privát példányok törlését igazolja. A helperkódok megmaradnak,
a titkok és a privát restore-naplók nem kerülnek a publikus bizonyítékok közé.

[Tételes lezárás](../../ai-ssd-backup-closure-20261101.md).
