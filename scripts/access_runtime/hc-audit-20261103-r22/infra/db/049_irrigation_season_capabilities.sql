update hc.domain_season_profile
set settings = (settings - 'control_enabled') || jsonb_build_object(
      'manual_watering', coalesce((settings ->> 'manual_watering')::boolean, (settings ->> 'control_enabled')::boolean, profile = 'summer'),
      'scheduled_watering', coalesce((settings ->> 'scheduled_watering')::boolean, (settings ->> 'control_enabled')::boolean, profile = 'summer'),
      'solar_pump_automation', coalesce((settings ->> 'solar_pump_automation')::boolean, (settings ->> 'control_enabled')::boolean, profile = 'summer'),
      'maintenance_controls', coalesce((settings ->> 'maintenance_controls')::boolean, (settings ->> 'control_enabled')::boolean, profile = 'summer'),
      'measurements_logging', true
    ),
    updated_at = now()
where domain = 'irrigation';
