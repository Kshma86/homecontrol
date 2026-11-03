begin;

create table if not exists hc.mqtt_flood_state (
  topic_base text primary key,
  entity_id bigint references hc.entity(id) on delete set null,
  active boolean not null default false,
  severity text not null default 'resolved' check (severity in ('warning', 'critical', 'resolved')),
  window_count integer not null default 0,
  messages_per_minute double precision not null default 0,
  first_exceeded_at timestamptz,
  detected_at timestamptz,
  last_seen_at timestamptz not null default now(),
  resolved_at timestamptz,
  updated_at timestamptz not null default now()
);

create index if not exists ix_mqtt_flood_state_active_updated
  on hc.mqtt_flood_state (active, updated_at desc);

commit;
