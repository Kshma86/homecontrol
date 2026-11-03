-- HC-07: explicit legacy representation normalization, once only.
-- Existing per-capability choices and active seasons are preserved.
update hc.domain_season_profile
set settings = (settings - 'control_enabled') || jsonb_build_object(
      'manual_watering', coalesce((settings ->> 'manual_watering')::boolean, (settings ->> 'control_enabled')::boolean, profile = 'summer'),
      'scheduled_watering', coalesce((settings ->> 'scheduled_watering')::boolean, (settings ->> 'control_enabled')::boolean, profile = 'summer'),
      'solar_pump_automation', coalesce((settings ->> 'solar_pump_automation')::boolean, (settings ->> 'control_enabled')::boolean, profile = 'summer'),
      'maintenance_controls', coalesce((settings ->> 'maintenance_controls')::boolean, (settings ->> 'control_enabled')::boolean, profile = 'summer'),
      'measurements_logging', true
    ),
    updated_at = now()
where domain = 'irrigation' and (settings ? 'control_enabled' or not settings ?& array['manual_watering','scheduled_watering','solar_pump_automation','maintenance_controls','measurements_logging']);

-- Preserve every valid operator-selected status, including done=true/status=open.
update hc.notes set status=case when done then 'tested' else 'open' end where status is null or status='';
alter table hc.notes alter column status set default 'open';
alter table hc.notes alter column status set not null;
