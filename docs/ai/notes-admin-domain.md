# Notes And Admin Domain Context

## Scope

The notes/admin module manages lightweight issue/request notes and admin
bootstrap CRUD for devices, entities, metrics, metric rules, and opening sensor
policy.

Primary implementation:

- `infra/backend/admin_service.py`
- `infra/backend/api_route_modules.py`
- `infra/db/020_notes.sql`
- `infra/db/022_zigbee_window_contacts.sql`
- `infra/db/023_opening_sensor_policy.sql`
- `infra/db/024_opening_sensor_room_order.sql`

## Ownership

- Durable truth: `hc.notes`, `hc.device`, `hc.entity`, `hc.metric`,
  `hc.entity_metric`, `hc.opening_sensor_policy`.
- Context sections: `notes`, `home_statistics`, plus affected domain contexts.

## API Endpoints

Notes:

- `GET /api/notes`
- `POST /api/notes`
- `PUT /api/notes/<note_id>`
- `DELETE /api/notes/<note_id>`
- `GET /api/context/notes`

Admin:

- `GET /api/admin/bootstrap`
- `POST /api/admin/metrics`
- `POST /api/admin/devices`
- `PUT /api/admin/devices/<device_id>`
- `GET /api/homecontrol/statistics`

## Notes Rules

Note type must be:

- `issues`
- `requests`

Text is required on create and when updating text.

Update can change:

- `text`
- `comment`
- `done`

An update with no fields is invalid.

Create/update/delete invalidates `notes`.

## Admin Rules

Metric value type must be:

- `num`
- `bool`
- `text`
- `json`

Device platform must be:

- `zigbee`
- `tuya`
- `wifi`
- `system`
- `other`

Device and entity names are required.

Opening sensor policy fields:

- `opening_type`: `window` or `door`
- `room_position`
- `opening_label`
- `has_mosquito_net`

Admin changes invalidate:

- `power_wall`
- `tuya`
- `irrigation`
- `home_statistics`

## Safety Rules

- Do not create metrics with arbitrary unknown value types.
- Do not create nameless devices/entities.
- Preserve context invalidation after admin mutations because many read models
  depend on entity/metric registration.
