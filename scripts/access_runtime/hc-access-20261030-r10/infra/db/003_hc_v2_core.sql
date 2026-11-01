begin;

create extension if not exists pgcrypto;

create table if not exists hc.event (
  id uuid primary key default gen_random_uuid(),
  type text not null check (length(trim(type)) > 0),
  source text not null check (length(trim(source)) > 0),
  domain text,
  entity_id bigint references hc.entity(id) on delete set null,
  occurred_at timestamptz not null default now(),
  received_at timestamptz not null default now(),
  correlation_id uuid,
  causation_id uuid references hc.event(id) on delete set null,
  idempotency_key text,
  payload jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  status text not null default 'recorded',
  created_at timestamptz not null default now()
);

create unique index if not exists ux_event_idempotency_key
  on hc.event (idempotency_key)
  where idempotency_key is not null;

create index if not exists ix_event_occurred_at
  on hc.event (occurred_at desc);

create index if not exists ix_event_type_occurred_at
  on hc.event (type, occurred_at desc);

create index if not exists ix_event_domain_occurred_at
  on hc.event (domain, occurred_at desc);

create index if not exists ix_event_entity_occurred_at
  on hc.event (entity_id, occurred_at desc);

create index if not exists ix_event_correlation_id
  on hc.event (correlation_id);

comment on table hc.event is
  'HC V2 immutable event store. Events are facts: what happened, when, from where, and with what payload.';

create table if not exists hc.plan (
  id uuid primary key default gen_random_uuid(),
  event_id uuid references hc.event(id) on delete set null,
  correlation_id uuid,
  domain text not null check (length(trim(domain)) > 0),
  type text not null check (length(trim(type)) > 0),
  target_type text,
  target_ref text,
  entity_id bigint references hc.entity(id) on delete set null,
  status text not null default 'planned',
  intended_start_at timestamptz,
  expires_at timestamptz,
  reasoning text,
  inputs jsonb not null default '{}'::jsonb,
  actions jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_by text not null default 'system',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_plan_created_at
  on hc.plan (created_at desc);

create index if not exists ix_plan_domain_status_created_at
  on hc.plan (domain, status, created_at desc);

create index if not exists ix_plan_event_id
  on hc.plan (event_id);

create index if not exists ix_plan_correlation_id
  on hc.plan (correlation_id);

create index if not exists ix_plan_entity_created_at
  on hc.plan (entity_id, created_at desc);

comment on table hc.plan is
  'HC V2 plan store. Plans describe intended actions before execution authority touches devices.';

create table if not exists hc.execution (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid references hc.plan(id) on delete set null,
  event_id uuid references hc.event(id) on delete set null,
  correlation_id uuid,
  domain text not null check (length(trim(domain)) > 0),
  executor text not null default 'legacy',
  status text not null default 'pending',
  attempt integer not null default 0,
  started_at timestamptz,
  ended_at timestamptz,
  command_topic text,
  command_payload jsonb not null default '{}'::jsonb,
  confirmation jsonb not null default '{}'::jsonb,
  result jsonb not null default '{}'::jsonb,
  error text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_execution_created_at
  on hc.execution (created_at desc);

create index if not exists ix_execution_domain_status_created_at
  on hc.execution (domain, status, created_at desc);

create index if not exists ix_execution_plan_id
  on hc.execution (plan_id);

create index if not exists ix_execution_event_id
  on hc.execution (event_id);

create index if not exists ix_execution_correlation_id
  on hc.execution (correlation_id);

comment on table hc.execution is
  'HC V2 execution store. Executions record what actually happened when a plan reached an executor.';

commit;
