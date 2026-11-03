begin;

create unique index if not exists ux_plan_event_id
  on hc.plan (event_id)
  where event_id is not null;

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
  'irrigation',
  case
    when e.type = 'scheduler.water_start.shadow' then 'irrigation.water_start.shadow_plan'
    when e.type = 'scheduler.water_stop.shadow' then 'irrigation.water_stop.shadow_plan'
    else 'irrigation.scheduler.shadow_plan'
  end,
  'schedule',
  coalesce(e.payload ->> 'source_ref', e.payload ->> 'label', 'irrigation'),
  'shadow_planned',
  null,
  'Shadow plan generated from an existing V2 scheduler event. Legacy remains command owner; this plan does not execute devices.',
  jsonb_build_object(
    'scheduler', jsonb_build_object(
      'mode', e.payload ->> 'mode',
      'source', e.payload ->> 'source',
      'source_ref', e.payload ->> 'source_ref',
      'label', e.payload ->> 'label',
      'day_of_week', e.payload -> 'day_of_week',
      'event_time', e.payload ->> 'event_time',
      'start_time', e.payload ->> 'start_time',
      'stop_time', e.payload ->> 'stop_time',
      'duration_minutes', e.payload -> 'duration_minutes',
      'legacy_status', e.payload ->> 'legacy_status'
    ),
    'shadow', jsonb_build_object(
      'command_owner', 'legacy',
      'side_effects', false
    )
  ),
  case
    when e.type = 'scheduler.water_start.shadow' then jsonb_build_array(
      jsonb_build_object(
        'capability', 'irrigation.valve.open',
        'target', coalesce(e.payload ->> 'source_ref', e.payload ->> 'label', 'irrigation'),
        'duration_minutes', e.payload -> 'duration_minutes',
        'scheduled_start', e.payload ->> 'start_time',
        'scheduled_stop', e.payload ->> 'stop_time',
        'side_effects', false
      )
    )
    when e.type = 'scheduler.water_stop.shadow' then jsonb_build_array(
      jsonb_build_object(
        'capability', 'irrigation.valve.close',
        'target', coalesce(e.payload ->> 'source_ref', e.payload ->> 'label', 'irrigation'),
        'scheduled_stop', coalesce(e.payload ->> 'stop_time', e.payload ->> 'event_time'),
        'side_effects', false
      )
    )
    else '[]'::jsonb
  end,
  jsonb_build_object(
    'model', 'HC_V2',
    'component', 'v2_scheduler_shadow_backfill',
    'event_type', e.type,
    'scheduler_run_id', e.payload ->> 'scheduler_run_id'
  ),
  'v2_scheduler_shadow_backfill'
from hc.event e
where e.domain = 'irrigation'
  and e.type in ('scheduler.water_start.shadow', 'scheduler.water_stop.shadow')
  and not exists (
    select 1
    from hc.plan p
    where p.event_id = e.id
  );

commit;
