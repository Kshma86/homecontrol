# Irrigation Scenarios And Eval Cases

Use these scenarios as regression guidance when changing irrigation behavior.
They are written for humans and AI agents. Convert high-risk scenarios into
unit tests when the implementation changes.

## Manual Commands

### Unknown Command

Given:

- `/api/irrigation/command` receives `{"name": "does_not_exist"}`.

Expected:

- HTTP `400`.
- Response has `ok: false`.
- No MQTT publish happens.

Current unit test:

- `test_unknown_command_returns_400_without_publish`

### Ping Command

Given:

- `/api/irrigation/command` receives `{"name": "ping"}`.

Expected:

- Publish `{"cmd": "ping"}` to the system command topic.
- Invalidate `irrigation`.
- Return a context hint with `/api/context/irrigation`.

Current unit test:

- `test_ping_command_publishes_and_invalidates_irrigation`

### Valve Close Command

Given:

- `/api/irrigation/command` receives `{"name": "valve_close"}`.

Expected:

- Use close confirmation flow, not a raw publish-only command.
- Publish `{"cmd": "set", "value": "close", "reason": "manual_command"}`.
- Return HTTP `200` on confirmation, HTTP `502` on confirmation failure.
- Invalidate `irrigation`.

## Manual Session Lifecycle

### Manual Start Success

Given:

- No `running` or `starting` irrigation session exists.
- User requests `duration_minutes = 20`.
- Valve open confirmation succeeds.

Expected:

- Insert a session with status `starting`.
- Publish open command with `source: homecontrol-admin`.
- Update session to `running`.
- Store confirmation details in `start_payload`.
- `requested_stop_at` is now + 20 minutes.
- `safety_stop_at` is now + `IRRIGATION_MANUAL_MAX_MINUTES`.
- Return HTTP `200`.
- Invalidate `irrigation`.

### Manual Start While Active

Given:

- A session exists with status `running` or `starting`.
- User requests another manual start.

Expected:

- Return HTTP `409`.
- Do not publish an MQTT open command.
- Do not create a second active session.

### Manual Start Duration Clamp

Given:

- `IRRIGATION_MANUAL_MAX_MINUTES = 180`.
- User requests `duration_minutes = 999`.

Expected:

- Actual session duration is `180`.
- Safety stop remains `180`.
- Response reports the clamped duration.

### Manual Start Open Confirmation Fails

Given:

- No active session exists.
- Open command publish either fails or valve never confirms `OPEN`.

Expected:

- Session is updated to `start_failed`.
- `stopped_at` is set.
- `error` includes the valve confirmation failure.
- Return HTTP `502`.
- Invalidate `irrigation`.

### Manual Stop Without Session

Given:

- `/api/irrigation/manual/stop` receives no `session_id`.
- No session has status `running`.

Expected:

- HTTP `404`.
- Error is `no running session`.
- No MQTT publish happens.

Current unit test:

- `test_stop_manual_without_running_session_returns_404`

### Manual Stop Success

Given:

- A session exists with status `running`.
- Close confirmation succeeds.

Expected:

- Publish close command with reason `manual_stop`.
- Update status to `stopped`.
- Store confirmation details in `stop_payload`.
- Return HTTP `200`.
- Invalidate `irrigation`.

### Manual Stop Confirmation Fails

Given:

- A session exists with status `running`.
- Close confirmation fails.

Expected:

- Update status to `stop_failed`.
- Store the failed confirmation details.
- Return HTTP `502`.
- Do not pretend the session stopped.

## Physical Safety

### Overdue Session

Given:

- A `running` session has `requested_stop_at <= now()` or
  `safety_stop_at <= now()`.

Expected:

- `stop_overdue_sessions()` calls close confirmation with reason
  `auto_timeout`.
- On success, status becomes `auto_stopped`.
- On failure, status becomes `stop_failed`.

### No Physical Watering

Given:

- A session has status `running`.
- It started at least 90 seconds ago.
- Live telemetry reports both motorized and manual valves as closed.

Expected:

- `fail_sessions_without_physical_watering()` marks it
  `failed_no_watering`.
- If linked to a pilot decision, execution status becomes
  `no_physical_watering`.

## Valve State

### Live Valve State

Given:

- MQTT monitor payload has:

```json
{
  "pump_metrics": {
    "json": {
      "valve": "open",
      "manual_valve": "closed",
      "valve_current": "0.12"
    }
  }
}
```

Expected:

- `valve` is `OPEN`.
- `motor_fully_open` is true.
- `manual_closed` is true.
- `valve_current_a` is `0.12`.

Current unit test:

- `test_live_valve_state_reads_mqtt_monitor_payloads`

### Manual Valve Blocks Scheduler

Given:

- Latest `manual_valve_state` contains `OPEN`, `OPENING`, `BETWEEN`, or
  `MOVING`.

Expected:

- `manual_valve_scheduler_guard().blocked` is true.
- Legacy and V2 scheduled starts do not run.

### Manual Valve Closed Does Not Block Scheduler

Given:

- Latest `manual_valve_state` contains `CLOSED`.

Expected:

- `manual_valve_scheduler_guard().blocked` is false.

## Schedule Updates

### Invalid Time Format

Given:

- Schedule update receives `start_time = "6am"` or `stop_time = "bad"`.

Expected:

- HTTP `400`.
- Error says the field must be `HH:MM`.

### Inverted Window

Given:

- Schedule update receives `start_time = "18:00"` and `stop_time = "06:00"`.

Expected:

- HTTP `400`.
- Error is `start_time must be before stop_time`.

Current unit test:

- `test_update_schedule_rejects_inverted_window`

### Update Today's Schedule

Given:

- The updated schedule is for today.
- `start_time`, `stop_time`, or `is_active` changes.

Expected:

- `last_started_on` resets to null.
- `last_stopped_on` resets to null.
- `irrigation` and `irrigation_pilot` contexts are invalidated.

## Legacy Scheduler

### Due Start

Given:

- Schedule is active.
- Today matches `day_of_week`.
- Current local time is within `[start_time, stop_time)`.
- `last_started_on` is not today.
- No active session exists.
- Manual valve guard is not blocked.

Expected:

- Schedule starts once.
- `last_started_on` is set to today.
- An irrigation session is created.
- Open command is confirmed before status becomes `running`.

### Due Start In Navigator Mode

Given:

- Same as due start.
- Pilot config mode is `navigator`.
- Pilot rules recommend a different final duration.

Expected:

- Decision is logged with `navigator_only`.
- Actual watering uses the schedule duration, not the recommendation.

### Due Start In Pilot Skip Mode

Given:

- Same as due start.
- Pilot mode is `pilot`.
- Rain or forecast rules set `final_duration = 0`.

Expected:

- No open command is published.
- Decision is logged as `skipped`.
- `last_started_on` is still set to today.

### Due Stop Success

Given:

- Schedule is active and started today.
- Current local time is at or after `stop_time`.
- Matching session started by `scheduler` or `pilot` is `running`.

Expected:

- Close command is sent with reason `schedule_stop`.
- If confirmed, schedule `last_stopped_on` is set to today.

### Due Stop Failure

Given:

- Same as due stop.
- Close confirmation fails and session becomes `stop_failed`.

Expected:

- Do not set `last_stopped_on`.
- Scheduler may retry on later ticks.

## Pilot Rules

### Analysis Connects Scheduler And Pilot

Given:

- AI context contains irrigation schedules and recent sessions.
- AI context also contains `irrigation_pilot.config.mode`,
  `recommendation.triggered_rules`, and `today_decision.execution_status`.
- Scheduler context contains `engine.publish_domains`.

Expected:

- Explain whether the active rule was advisory or execution-affecting.
- In `navigator` mode, say the rule was a recommendation and did not by itself
  change watering duration.
- In `pilot` mode, say `final_duration` was the intended effective duration, or
  watering was skipped if `final_duration = 0`.
- Use `execution_status` to say whether it was only evaluated, skipped,
  command-confirmed, failed, or completed.
- Use `scheduler.engine.publish_domains` before claiming V2 published an
  irrigation command.

### Session Payload Links To Pilot

Given:

- A recent irrigation session has `start_payload.pilot_final_duration`,
  `start_payload.pilot_triggered_rules`, `start_payload.pilot_reason`, or
  `start_payload.stop_policy`.

Expected:

- Link that session to the pilot/scheduler decision.
- Use `stop_policy.effective_duration_minutes` and `effective_stop_at` for V2
  pilot effective stop analysis.
- Do not infer pilot influence from weather alone.

### Rain Skip Has Priority

Given:

- `rain_24h_mm` is greater than `rain_24h_threshold_mm`.
- Temperature is also above `heat_threshold_c`.

Expected:

- `final_duration = 0`.
- Triggered rules contain only `rain_skip`.
- Heat correction is not applied.

### Forecast Skip Has Priority Over Temperature

Given:

- `rain_24h_mm` is not greater than threshold.
- `forecast_rain_24h_mm` is greater than threshold.
- `pop_percent` is greater than threshold.
- Temperature is above `heat_threshold_c`.

Expected:

- `final_duration = 0`.
- Triggered rules contain `forecast_skip`.
- Heat correction is not applied.

### Garden Soil Wet Skip

Given:

- Rain and forecast skip do not apply.
- `Moisture_02` has a fresh soil moisture sample.
- Soil moisture is greater than `soil_wet_skip_threshold_percent`.

Expected:

- `final_duration = 0`.
- Triggered rules contain `soil_wet_skip`.
- Temperature correction is not applied.

### Garden Soil Dry Increase

Given:

- Rain, forecast, and wet soil skip do not apply.
- `Moisture_02` has a fresh soil moisture sample.
- Soil moisture is less than `soil_dry_threshold_percent`.

Expected:

- `soil_dry_correction_percent` is applied to the base duration.
- Triggered rules contain `soil_dry_increase`.
- Temperature correction is not applied.

### Stale Garden Soil Sample Is Ignored

Given:

- `Moisture_02` soil moisture sample age is greater than
  `soil_sample_max_age_hours`.

Expected:

- Soil moisture inputs are visible in decision details.
- `SoilMoistureUsable = false`.
- No soil moisture skip or correction is applied.

### Threshold Equality Does Not Trigger

Given:

- `rain_24h_mm` equals `rain_24h_threshold_mm`.
- `forecast_rain_24h_mm` equals `forecast_rain_threshold_mm`.
- `pop_percent` equals `pop_threshold_percent`.
- Temperature equals `heat_threshold_c` or `cold_threshold_c`.

Expected:

- No skip or correction rule triggers because comparisons are strict.

### Heat Increase

Given:

- Base duration is `60`.
- Temperature is greater than `heat_threshold_c`.
- `heat_correction_percent = 20`.
- No rain or forecast skip applies.

Expected:

- `final_duration = 72`.
- Triggered rules contain `heat_increase`.

### Cold Decrease

Given:

- Base duration is `60`.
- Temperature is less than `cold_threshold_c`.
- `cold_correction_percent = -20`.
- No rain or forecast skip applies.

Expected:

- `final_duration = 48`.
- Triggered rules contain `cold_decrease`.

## V2 Scheduler

### Scheduler Tick Without Irrigation Publish Domain

Given:

- V2 execution engine `publish_domains` does not include `irrigation`.

Expected:

- `IrrigationService.scheduler_tick()` does not call legacy or V2 start/stop
  branches.

Current unit test:

- `test_scheduler_tick_skips_without_irrigation_publish_domain`

### Scheduler Tick With Irrigation Publish Domain

Given:

- V2 execution engine `publish_domains` includes `irrigation`.

Expected:

- `scheduler_tick()` calls `run_v2_due_schedules()`.
- Then it calls `stop_v2_due_schedules()`.
- It does not call legacy start/stop branches.

Current unit test:

- `test_scheduler_tick_uses_v2_branch_for_irrigation_publish_domain`

### V2 Pilot Skip

Given:

- V2 schedule is due.
- Pilot mode is `pilot`.
- Pilot rules set `final_duration = 0`.

Expected:

- Mark schedule `last_started_on = current_date`.
- Log pilot decision as `v2_skipped`.
- Mark matching V2 open execution as `skipped`.
- Do not publish open command.

### V2 Effective Stop

Given:

- V2 schedule has a running `v2_scheduler` session.
- Its `requested_stop_at <= now()`.

Expected:

- Publish close command with reason `v2_effective_stop`.
- Mark matching V2 close execution `confirmed` on success or `failed` on
  failure.
- Mark schedule stopped only on success or already-stopped state.

## Context Invalidation

### Irrigation Mutations

Any of these should invalidate `irrigation`:

- manual start;
- manual stop;
- direct irrigation command;
- Nano config command;
- schedule update.

### Pilot Mutations

Any of these should invalidate `irrigation_pilot`:

- schedule update;
- pilot config update;
- manual pilot evaluation;
- weather fetch.

Weather fetch should also include `weather` in `context.read_after`.

## Suggested Focused Test Additions

Add tests when touching these areas:

- Manual start rejects a second active session.
- Failed open confirmation marks `start_failed`.
- Failed close confirmation marks `stop_failed`.
- Pilot rule precedence and strict threshold equality.
- Navigator mode logs recommendation but preserves scheduled duration.
- Pilot skip does not publish open command.
- Schedule update for today resets `last_started_on` and `last_stopped_on`.
- V2 skip marks execution `skipped`.
- V2 effective stop waits for `requested_stop_at`, not only schedule
  `stop_time`.
