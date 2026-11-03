alter table hc.climate_schedule_rule
  add column if not exists season_profile text not null default 'summer';

alter table hc.climate_schedule_rule
  drop constraint if exists climate_schedule_rule_season_profile_check;

alter table hc.climate_schedule_rule
  add constraint climate_schedule_rule_season_profile_check
  check (season_profile in ('summer', 'winter'));

create index if not exists ix_climate_schedule_rule_profile_day_time
  on hc.climate_schedule_rule (season_profile, day_of_week, start_time);
