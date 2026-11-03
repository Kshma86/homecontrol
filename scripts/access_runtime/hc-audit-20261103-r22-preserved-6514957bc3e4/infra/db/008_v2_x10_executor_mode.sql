alter table hc.scheduler_config
  drop constraint if exists scheduler_config_mode_check;

alter table hc.scheduler_config
  add constraint scheduler_config_mode_check
  check (mode in ('legacy', 'v2_shadow', 'v2_plan_only', 'v2_execute_irrigation', 'v2_execute_x10'));
