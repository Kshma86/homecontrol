begin;

update hc.scheduler_config
set mode = 'v2_shadow',
    updated_at = now(),
    updated_by = 'migration_007',
    notes = coalesce(notes, 'migrated unified_shadow to v2_shadow')
where mode = 'unified_shadow';

alter table hc.scheduler_config
  drop constraint if exists scheduler_config_mode_check;

alter table hc.scheduler_config
  add constraint scheduler_config_mode_check
  check (mode in ('legacy', 'v2_shadow', 'v2_plan_only', 'v2_execute_irrigation'));

commit;
