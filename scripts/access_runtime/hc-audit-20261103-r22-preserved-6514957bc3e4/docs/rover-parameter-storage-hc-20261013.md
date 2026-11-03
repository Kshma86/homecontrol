# hw15 / persistence12 HC integráció

Forrás: HC_AI_PARAM_TAROLAS_ATADAS_20261013.md. Ez felülírja a korábbi HC automatikus konfigurációmentés és HC-forrású alapkonfiguráció leírását.

A rover a paraméterek forrása. Az editor megnyitáskor és 3 másodperces frissítéskor csak GET-et küld. Elsődleges adat az ellenőrzött stored_parameters; régi simplify11 esetén a friss ACTIVE/APPLIED parameters. A tárolt objektum verzióját és bináris CRC-jét a HC ellenőrzi. Tárolt értékek az STM állapotától függetlenül beolvashatók. A korábbi HC-fájl csak jelölt gyorsítótár, nem írja felül a rovert. Átmeneti null/stale válasz nem törli a szerkesztőt.

A HC nem ment automatikusan a roverre vagy HC draftként. Értékváltozást a kanonikus 256 bájtos RCP-adattal hasonlít össze; kulcssorrend és formázás nem számít. Változatlan értékekre nincs natív POST és nincs új revízió. A backend külön is érvényesíti ezt.

A Mentés roverre gomb friss GET állapotból veszi a bootokat, epochot és revíziót, és ellenőrzi a natív can_apply jelzőt. A helyi szerkesztés alapjához képest megváltozott roverrevízió konfliktus: nincs automatikus felülírás vagy keverés. A helyi szöveg megmarad, az új roverértékek külön összehasonlíthatók. A felhasználó explicit betöltheti azokat vagy megtarthatja szerkesztését az új alaphoz.

Egy valódi változtatás egyetlen natív POST. A 202 nem siker: a HC legfeljebb 20 automatikus, csak GET eredményegyeztetést végez, a request/revision/CRC és friss ACTIVE/APPLIED korrelációt ellenőrizve. Elveszett HTTP-válasz után is megmarad az egyeztetés; nincs POST retry. Ez nem tartós HC Apply-zárolás. A natív PENDING/UNKNOWN elvetése továbbra sem automatikus.

Normál rover-restart után a HC csak visszaolvassa az ESP saját boot-restore eredményét. A tárolt paraméter önmagában nem APPLIED, can_apply vagy mozgási engedély. A kézi mód a friss natív képességet és állapotot használja. A 10/13 mezős ERPM továbbra is teljes csere; kalibráció megőrzéséhez teljes RCP2 szerkesztendő.

Kézi relé időzítési javítás: a claim kérés 1,5 s belépési időkeretet kap; a motorcélok 100 ms korlátja megmarad. A belépést megelőző natív állapotlekérdezések alatt beérkező claimet a relé nem dobja el 100 ms után. STOP/release nem veszhet el motorcélokra szánt elévülés miatt. A belépési snapshot rövid olvasási lock-torlódását legfeljebb 1 s-ig kivárja; továbbra is friss állapot és natív claim-képesség szükséges. Elutasított natív/browser frame és a relé megszakításának fázisa korlátozott, tokent nem tartalmazó diagnosztikát kap.
