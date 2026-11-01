begin;

create unique index if not exists ux_plan_event_id
  on hc.plan (event_id)
  where event_id is not null;

create unique index if not exists ux_execution_plan_id
  on hc.execution (plan_id)
  where plan_id is not null;

with x10_events as (
  select
    e.*,
    coalesce(e.payload ->> 'source_ref', e.payload ->> 'label', 'xiaomi_x10') as target_ref,
    (
      select coalesce(jsonb_agg(segment::integer), '[]'::jsonb)
      from unnest(string_to_array(coalesce(e.payload ->> 'segments', ''), ',')) as raw(segment)
      where trim(segment) ~ '^[0-9]+$'
    ) as segment_list
  from hc.event e
  where e.domain = 'xiaomi_x10'
    and e.type = 'scheduler.clean_start.shadow'
),
inserted_plans as (
  insert into hc.plan (
    event_id,
    domain,
    type,
    target_type,
    target_ref,
    status,
    intended_start_at,
    reasoning,
    inputs,
    actions,
    metadata,
    created_by
  )
  select
    e.id,
    'xiaomi_x10',
    'xiaomi_x10.clean_start.shadow_plan',
    'schedule',
    e.target_ref,
    'shadow_planned',
    null,
    'Shadow plan generated from an existing V2 X10 scheduler event. Legacy remains command owner; this plan does not execute devices.',
    jsonb_build_object(
      'scheduler', jsonb_build_object(
        'mode', e.payload ->> 'mode',
        'source', e.payload ->> 'source',
        'source_ref', e.payload ->> 'source_ref',
        'label', e.payload ->> 'label',
        'days', e.payload -> 'days',
        'days_mask', e.payload ->> 'days_mask',
        'event_time', e.payload ->> 'event_time',
        'start_time', e.payload ->> 'start_time',
        'map_id', e.payload ->> 'map_id',
        'segments', e.segment_list,
        'suction', e.payload ->> 'suction',
        'water_level', e.payload ->> 'water_level',
        'clean_mode', e.payload ->> 'clean_mode',
        'legacy_status', e.payload ->> 'legacy_status'
      ),
      'shadow', jsonb_build_object(
        'command_owner', 'legacy',
        'side_effects', false
      )
    ),
    jsonb_build_array(
      jsonb_build_object(
        'capability', 'vacuum.schedule.clean',
        'target', e.target_ref,
        'command', jsonb_build_object(
          'map_id', e.payload ->> 'map_id',
          'segments', e.segment_list,
          'start_time', coalesce(e.payload ->> 'start_time', e.payload ->> 'event_time'),
          'days', coalesce(e.payload ->> 'days_mask', e.payload ->> 'raw_days'),
          'enabled', 1,
          'mode', e.payload ->> 'clean_mode',
          'suction', e.payload ->> 'suction',
          'water_level', e.payload ->> 'water_level',
          'shadow_only', true
        ),
        'side_effects', false
      )
    ),
    jsonb_build_object(
      'model', 'HC_V2',
      'component', 'v2_scheduler_shadow_backfill',
      'event_type', e.type,
      'scheduler_run_id', e.payload ->> 'scheduler_run_id'
    ),
    'v2_scheduler_shadow_backfill'
  from x10_events e
  where not exists (
    select 1
    from hc.plan p
    where p.event_id = e.id
  )
  returning *
),
x10_plans as (
  select p.*
  from inserted_plans p
  union
  select p.*
  from hc.plan p
  join x10_events e on e.id = p.event_id
)
insert into hc.execution (
  plan_id,
  event_id,
  domain,
  executor,
  status,
  attempt,
  command_topic,
  command_payload,
  confirmation,
  result,
  metadata
)
select
  p.id,
  p.event_id,
  'xiaomi_x10',
  'legacy_xiaomi_x10',
  'shadow_ready',
  0,
  'homecontrol/xiaomi_x10/command/schedule_clean',
  coalesce(p.actions #> '{0,command}', '{}'::jsonb),
  '{}'::jsonb,
  jsonb_build_object(
    'shadow', true,
    'would_publish', true,
    'published', false,
    'reason', 'legacy_remains_command_owner'
  ),
  jsonb_build_object(
    'model', 'HC_V2',
    'component', 'v2_scheduler_shadow_backfill',
    'command_owner', 'legacy',
    'side_effects', false,
    'scheduler_run_id', p.metadata ->> 'scheduler_run_id'
  )
from x10_plans p
where not exists (
  select 1
  from hc.execution x
  where x.plan_id = p.id
);

commit;
