# HomeControl UI page inventory

Baseline inventory captured on 2026-09-06 before navigation cleanup. No page is marked for deletion yet; usage data should guide the later desktop/mobile/admin split.

| Page ID | Label | Current role | Initial bucket |
|---|---|---|---|
| home | Home | Desktop overview and quick control | Daily desktop |
| mobile-dashboard | Mobile | Mobile overview and quick control | Daily mobile |
| tablet-dashboard | Tablet | Tablet overview and quick control | Daily tablet |
| irrigation | Irrigation | Irrigation control and configuration | User |
| statistics | Irrigation Stats | Irrigation, weather and tank history | User/analysis |
| solar | Solar | Detailed inverter state and history | User/analysis |
| x10 | X10 Robot | Robot control, map and schedules | User |
| climate | Climate | Climate control and history | User |
| mower | Mower | v3.1 status/control, deadman relay and offline RCP1 parameter drafts | User |
| mower-legacy | Mower Legacy | Static old-field preview; all controls disabled, no network effects | Reference |
| rtk-editor | RTK Editor | Existing map/coverage editor, unchanged during v3 foundation | User/analysis |
| power-wall | Power Wall | Power sockets, meters and bindings | User/admin |
| nyest-scheduler | Marten Deterrent | Deterrent schedules and state | User |
| scheduler | Scheduler | Cross-domain scheduling | User/admin |
| hc-stat | House stats | Sensor statistics | Analysis |
| usage-statistics | Usage Stats | Anonymous page usage by platform | Admin/analysis |
| ai | AI | Assistant and AI status | User/admin |
| tuya | Tuya | Tuya device playground | Admin/debug |
| sql-lab | SQL LAB | Direct database inspection | Admin/debug |
| performance | Performance | Runtime and host metrics | Admin |
| backup | Backup | Backup and restore operations | Admin |
| hc-admin | HC Admin | Entity and integration administration | Admin |
| parameters | Parameters | Runtime parameters | Admin |
| notes | Notes | Operational notes | Admin |
| debug | DEBUG | Logs and diagnostics | Admin/debug |
| documentation | Docs | Embedded documentation | Reference |
| about | About | Architecture and system information | Reference |

## Usage measurement

Each actual tab activation writes one local database event with page ID, timestamp, anonymous browser ID, device class (`mobile`, `tablet`, `desktop`), viewport size, standalone/PWA flag and user-agent. IP addresses and personal names are not stored.

Aggregated data is available from `GET /api/page-usage/summary?days=30`. The first useful navigation review should happen after at least 2–4 weeks of normal use.
