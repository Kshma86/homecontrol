begin;

alter table hc.irrigation_schedule
  drop constraint if exists irrigation_schedule_day_of_week_key;

create index if not exists ix_irrigation_schedule_day_start
  on hc.irrigation_schedule (day_of_week, start_time, id);

commit;
