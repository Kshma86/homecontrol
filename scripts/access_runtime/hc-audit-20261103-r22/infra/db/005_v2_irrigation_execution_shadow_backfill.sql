begin;

create unique index if not exists ux_execution_plan_id
  on hc.execution (plan_id)
  where plan_id is not null;

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
  'irrigation',
  'legacy_irrigation',
  'shadow_ready',
  0,
  'homecontrol/cmd/irrigation/esp-irrigation-1/valve',
  case
    when p.type = 'irrigation.water_start.shadow_plan' then jsonb_build_object(
      'cmd', 'set',
      'value', 'open',
      'source', 'v2_shadow',
      'schedule_id', p.target_ref,
      'schedule_label', p.inputs #>> '{scheduler,label}',
      'duration_minutes', p.inputs #> '{scheduler,duration_minutes}',
      'shadow_only', true
    )
    when p.type = 'irrigation.water_stop.shadow_plan' then jsonb_build_object(
      'cmd', 'set',
      'value', 'close',
      'source', 'v2_shadow',
      'schedule_id', p.target_ref,
      'schedule_label', p.inputs #>> '{scheduler,label}',
      'reason', 'v2_shadow_schedule_stop',
      'shadow_only', true
    )
    else '{}'::jsonb
  end,
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
from hc.plan p
where p.domain = 'irrigation'
  and p.type in ('irrigation.water_start.shadow_plan', 'irrigation.water_stop.shadow_plan')
  and not exists (
    select 1
    from hc.execution x
    where x.plan_id = p.id
  );

commit;
