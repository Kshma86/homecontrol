-- HC-38 / hc-r1-058-v1: schema-only PostgreSQL 16 baseline, through release r1/058.
-- Fresh empty database only, via migrate_hc38.py; never replay 001-058 afterwards.
-- No rows, owners, ACLs or sequence counters. Presence-touch triggers stay DISABLED.
--
-- PostgreSQL database dump
--



SET LOCAL client_encoding = 'UTF8';
SET LOCAL standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', true);
SET LOCAL check_function_bodies = false;
SET LOCAL xmloption = content;
SET LOCAL client_min_messages = warning;
SET LOCAL row_security = off;

--
-- Name: hc; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA hc;


--
-- Name: platform_t; Type: TYPE; Schema: hc; Owner: -
--

CREATE TYPE hc.platform_t AS ENUM (
    'zigbee',
    'tuya',
    'wifi',
    'system',
    'other',
    'growatt'
);


--
-- Name: value_type_t; Type: TYPE; Schema: hc; Owner: -
--

CREATE TYPE hc.value_type_t AS ENUM (
    'num',
    'bool',
    'text',
    'json'
);


--
-- Name: refresh_presence(); Type: FUNCTION; Schema: hc; Owner: -
--

CREATE FUNCTION hc.refresh_presence() RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
  -- Online -> Offline ahol lejárt az időablak
  WITH threshold AS (
    SELECT
      em.entity_id,
      MIN(em.max_interval_sec) AS max_int
    FROM hc.entity_metric em
    WHERE em.is_enabled = TRUE
      AND em.max_interval_sec IS NOT NULL
    GROUP BY em.entity_id
  )
  UPDATE hc.entity_presence p
  SET status = 'offline',
      updated_at = now()
  FROM threshold t
  WHERE p.entity_id = t.entity_id
    AND p.status <> 'offline'
    AND p.last_seen_ts < (now() - make_interval(secs => t.max_int));

  -- availability state frissítés offline-ra (csak ahol offline lett)
  INSERT INTO hc.entity_state(entity_id, key, ts, v_text)
  SELECT p.entity_id, 'availability', now(), 'offline'
  FROM hc.entity_presence p
  WHERE p.status = 'offline'
  ON CONFLICT (entity_id, key)
  DO UPDATE SET ts = EXCLUDED.ts, v_text = EXCLUDED.v_text;
END $$;


--
-- Name: tg_set_updated_at(); Type: FUNCTION; Schema: hc; Owner: -
--

CREATE FUNCTION hc.tg_set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END $$;


--
-- Name: tg_touch_presence(); Type: FUNCTION; Schema: hc; Owner: -
--

CREATE FUNCTION hc.tg_touch_presence() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  INSERT INTO hc.entity_presence(entity_id, last_seen_ts, status, updated_at)
  VALUES (NEW.entity_id, now(), 'online', now())
  ON CONFLICT (entity_id)
  DO UPDATE SET last_seen_ts = EXCLUDED.last_seen_ts,
                status = 'online',
                updated_at = now();

  -- opcionálisan az entity_state-be is kiírjuk az availability-t
  INSERT INTO hc.entity_state(entity_id, key, ts, v_text)
  VALUES (NEW.entity_id, 'availability', now(), 'online')
  ON CONFLICT (entity_id, key)
  DO UPDATE SET ts = EXCLUDED.ts, v_text = EXCLUDED.v_text;

  RETURN NEW;
END $$;


--
-- Name: tg_validate_entity_state(); Type: FUNCTION; Schema: hc; Owner: -
--

CREATE FUNCTION hc.tg_validate_entity_state() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
  m hc.metric%ROWTYPE;
BEGIN
  SELECT * INTO m FROM hc.metric WHERE key = NEW.key AND is_active = TRUE;
  IF NOT FOUND OR m.enforce_validation = FALSE THEN
    RETURN NEW; -- laza
  END IF;

  IF m.value_type = 'num' THEN
    IF NEW.v_num IS NULL OR NEW.v_bool IS NOT NULL OR NEW.v_text IS NOT NULL OR NEW.v_json IS NOT NULL THEN
      RAISE EXCEPTION 'state type mismatch for key=% expected num', NEW.key;
    END IF;
    IF m.min_num IS NOT NULL AND NEW.v_num < m.min_num THEN
      RAISE EXCEPTION 'state out of range (min) key=% value=%', NEW.key, NEW.v_num;
    END IF;
    IF m.max_num IS NOT NULL AND NEW.v_num > m.max_num THEN
      RAISE EXCEPTION 'state out of range (max) key=% value=%', NEW.key, NEW.v_num;
    END IF;

  ELSIF m.value_type = 'bool' THEN
    IF NEW.v_bool IS NULL OR NEW.v_num IS NOT NULL OR NEW.v_text IS NOT NULL OR NEW.v_json IS NOT NULL THEN
      RAISE EXCEPTION 'state type mismatch for key=% expected bool', NEW.key;
    END IF;

  ELSIF m.value_type = 'text' THEN
    IF NEW.v_text IS NULL OR NEW.v_num IS NOT NULL OR NEW.v_bool IS NOT NULL OR NEW.v_json IS NOT NULL THEN
      RAISE EXCEPTION 'state type mismatch for key=% expected text', NEW.key;
    END IF;

  ELSIF m.value_type = 'json' THEN
    IF NEW.v_json IS NULL OR NEW.v_num IS NOT NULL OR NEW.v_bool IS NOT NULL OR NEW.v_text IS NOT NULL THEN
      RAISE EXCEPTION 'state type mismatch for key=% expected json', NEW.key;
    END IF;
  END IF;

  RETURN NEW;
END $$;


--
-- Name: tg_validate_measurement(); Type: FUNCTION; Schema: hc; Owner: -
--

CREATE FUNCTION hc.tg_validate_measurement() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
  m hc.metric%ROWTYPE;
BEGIN
  SELECT * INTO m FROM hc.metric WHERE key = NEW.key AND is_active = TRUE;
  IF NOT FOUND OR m.enforce_validation = FALSE THEN
    RETURN NEW; -- laza: ismeretlen vagy nem enforced -> átenged
  END IF;

  -- típus ellenőrzés
  IF m.value_type = 'num' THEN
    IF NEW.v_num IS NULL OR NEW.v_bool IS NOT NULL OR NEW.v_text IS NOT NULL OR NEW.v_json IS NOT NULL THEN
      RAISE EXCEPTION 'measurement type mismatch for key=% expected num', NEW.key;
    END IF;
    IF m.min_num IS NOT NULL AND NEW.v_num < m.min_num THEN
      RAISE EXCEPTION 'measurement out of range (min) key=% value=%', NEW.key, NEW.v_num;
    END IF;
    IF m.max_num IS NOT NULL AND NEW.v_num > m.max_num THEN
      RAISE EXCEPTION 'measurement out of range (max) key=% value=%', NEW.key, NEW.v_num;
    END IF;

  ELSIF m.value_type = 'bool' THEN
    IF NEW.v_bool IS NULL OR NEW.v_num IS NOT NULL OR NEW.v_text IS NOT NULL OR NEW.v_json IS NOT NULL THEN
      RAISE EXCEPTION 'measurement type mismatch for key=% expected bool', NEW.key;
    END IF;

  ELSIF m.value_type = 'text' THEN
    IF NEW.v_text IS NULL OR NEW.v_num IS NOT NULL OR NEW.v_bool IS NOT NULL OR NEW.v_json IS NOT NULL THEN
      RAISE EXCEPTION 'measurement type mismatch for key=% expected text', NEW.key;
    END IF;

  ELSIF m.value_type = 'json' THEN
    IF NEW.v_json IS NULL OR NEW.v_num IS NOT NULL OR NEW.v_bool IS NOT NULL OR NEW.v_text IS NOT NULL THEN
      RAISE EXCEPTION 'measurement type mismatch for key=% expected json', NEW.key;
    END IF;
  END IF;

  RETURN NEW;
END $$;


SET LOCAL default_tablespace = '';

SET LOCAL default_table_access_method = heap;

--
-- Name: ai_chat_audit; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.ai_chat_audit (
    id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    started_at timestamp with time zone,
    question text NOT NULL,
    answer text,
    provider text,
    model text,
    status_code integer,
    ok boolean,
    error text,
    source text,
    total_ms numeric,
    context_ms numeric,
    knowledge_ms numeric,
    model_ms numeric,
    db_query_count integer,
    skills jsonb DEFAULT '[]'::jsonb NOT NULL,
    data_sources jsonb DEFAULT '[]'::jsonb NOT NULL,
    skill_timings jsonb DEFAULT '[]'::jsonb NOT NULL,
    context_timings jsonb DEFAULT '[]'::jsonb NOT NULL,
    upstream jsonb DEFAULT '{}'::jsonb NOT NULL,
    request_meta jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: ai_chat_audit_id_seq; Type: SEQUENCE; Schema: hc; Owner: -
--

CREATE SEQUENCE hc.ai_chat_audit_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ai_chat_audit_id_seq; Type: SEQUENCE OWNED BY; Schema: hc; Owner: -
--

ALTER SEQUENCE hc.ai_chat_audit_id_seq OWNED BY hc.ai_chat_audit.id;


--
-- Name: climate_schedule_rule; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.climate_schedule_rule (
    id bigint NOT NULL,
    label text NOT NULL,
    day_of_week smallint,
    start_time time without time zone NOT NULL,
    is_enabled boolean DEFAULT false NOT NULL,
    power text DEFAULT 'on'::text NOT NULL,
    mode text DEFAULT 'heat'::text NOT NULL,
    target_temperature integer DEFAULT 23 NOT NULL,
    fan_speed text DEFAULT 'auto'::text NOT NULL,
    light text DEFAULT 'off'::text NOT NULL,
    rule_engine jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    extra_fan text DEFAULT 'keep'::text NOT NULL,
    season_profile text DEFAULT 'summer'::text NOT NULL,
    CONSTRAINT climate_schedule_rule_day_of_week_check CHECK (((day_of_week >= 0) AND (day_of_week <= 6))),
    CONSTRAINT climate_schedule_rule_extra_fan_check CHECK ((extra_fan = ANY (ARRAY['keep'::text, 'on'::text, 'off'::text]))),
    CONSTRAINT climate_schedule_rule_fan_speed_check CHECK ((fan_speed = ANY (ARRAY['keep'::text, 'auto'::text, 'low'::text, 'mediumlow'::text, 'medium'::text, 'mediumhigh'::text, 'high'::text, 'quiet'::text, 'turbo'::text]))),
    CONSTRAINT climate_schedule_rule_light_check CHECK ((light = ANY (ARRAY['keep'::text, 'on'::text, 'off'::text]))),
    CONSTRAINT climate_schedule_rule_mode_check CHECK ((mode = ANY (ARRAY['keep'::text, 'auto'::text, 'cool'::text, 'dry'::text, 'fan'::text, 'heat'::text]))),
    CONSTRAINT climate_schedule_rule_power_check CHECK ((power = ANY (ARRAY['keep'::text, 'on'::text, 'off'::text]))),
    CONSTRAINT climate_schedule_rule_season_profile_check CHECK ((season_profile = ANY (ARRAY['summer'::text, 'winter'::text]))),
    CONSTRAINT climate_schedule_rule_target_temperature_check CHECK (((target_temperature >= 8) AND (target_temperature <= 30)))
);


--
-- Name: climate_schedule_rule_id_seq; Type: SEQUENCE; Schema: hc; Owner: -
--

CREATE SEQUENCE hc.climate_schedule_rule_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: climate_schedule_rule_id_seq; Type: SEQUENCE OWNED BY; Schema: hc; Owner: -
--

ALTER SEQUENCE hc.climate_schedule_rule_id_seq OWNED BY hc.climate_schedule_rule.id;


--
-- Name: climate_window_guard; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.climate_window_guard (
    id integer NOT NULL,
    open_delay_seconds integer DEFAULT 60 NOT NULL,
    close_delay_seconds integer DEFAULT 60 NOT NULL,
    desired jsonb DEFAULT '{}'::jsonb NOT NULL,
    suspended boolean DEFAULT false NOT NULL,
    CONSTRAINT climate_window_guard_id_check CHECK ((id = 1))
);


--
-- Name: combustion_safety_config; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.combustion_safety_config (
    singleton boolean DEFAULT true NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    fan_on_w double precision DEFAULT 50 NOT NULL,
    fan_off_w double precision DEFAULT 20 NOT NULL,
    fan_on_seconds integer DEFAULT 5 NOT NULL,
    fan_off_seconds integer DEFAULT 20 NOT NULL,
    co_warning_ppm double precision DEFAULT 10 NOT NULL,
    co_shutdown_ppm double precision DEFAULT 20 NOT NULL,
    co_rise_ppm double precision DEFAULT 2 NOT NULL,
    auto_shutdown boolean DEFAULT true NOT NULL,
    green_interval_seconds integer DEFAULT 60 NOT NULL,
    secondary_interval_seconds integer DEFAULT 20 NOT NULL,
    closed_interval_seconds integer DEFAULT 4 NOT NULL,
    pulse_seconds double precision DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_by text DEFAULT 'migration'::text NOT NULL,
    green_brightness integer DEFAULT 50 NOT NULL,
    orange_brightness integer DEFAULT 200 NOT NULL,
    red_brightness integer DEFAULT 254 NOT NULL,
    green_color text DEFAULT '#00ff00'::text NOT NULL,
    orange_color text DEFAULT '#ff8c00'::text NOT NULL,
    red_color text DEFAULT '#ff0000'::text NOT NULL,
    CONSTRAINT combustion_safety_config_green_brightness_check CHECK (((green_brightness >= 1) AND (green_brightness <= 254))),
    CONSTRAINT combustion_safety_config_green_color_check CHECK ((green_color ~ '^#[0-9A-Fa-f]{6}$'::text)),
    CONSTRAINT combustion_safety_config_orange_brightness_check CHECK (((orange_brightness >= 1) AND (orange_brightness <= 254))),
    CONSTRAINT combustion_safety_config_orange_color_check CHECK ((orange_color ~ '^#[0-9A-Fa-f]{6}$'::text)),
    CONSTRAINT combustion_safety_config_red_brightness_check CHECK (((red_brightness >= 1) AND (red_brightness <= 254))),
    CONSTRAINT combustion_safety_config_red_color_check CHECK ((red_color ~ '^#[0-9A-Fa-f]{6}$'::text)),
    CONSTRAINT combustion_safety_config_singleton_check CHECK (singleton)
);


--
-- Name: combustion_safety_event; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.combustion_safety_event (
    id bigint NOT NULL,
    ts timestamp with time zone DEFAULT now() NOT NULL,
    level text NOT NULL,
    event_type text NOT NULL,
    reason text DEFAULT ''::text NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: combustion_safety_event_id_seq; Type: SEQUENCE; Schema: hc; Owner: -
--

CREATE SEQUENCE hc.combustion_safety_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: combustion_safety_event_id_seq; Type: SEQUENCE OWNED BY; Schema: hc; Owner: -
--

ALTER SEQUENCE hc.combustion_safety_event_id_seq OWNED BY hc.combustion_safety_event.id;


--
-- Name: combustion_safety_runtime; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.combustion_safety_runtime (
    singleton boolean DEFAULT true NOT NULL,
    revision bigint DEFAULT 0 NOT NULL,
    latched boolean DEFAULT true NOT NULL,
    co_warning_active boolean DEFAULT false NOT NULL,
    last_co double precision,
    last_co_sample_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    acknowledged_at timestamp with time zone,
    CONSTRAINT combustion_safety_runtime_singleton_check CHECK (singleton)
);


--
-- Name: command_outbox; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.command_outbox (
    id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    scheduled_at timestamp with time zone,
    sent_at timestamp with time zone,
    ack_at timestamp with time zone,
    entity_id bigint,
    topic text NOT NULL,
    payload jsonb NOT NULL,
    retain boolean DEFAULT true NOT NULL,
    qos smallint DEFAULT 1 NOT NULL,
    status text DEFAULT 'new'::text NOT NULL,
    error text
);


--
-- Name: command_outbox_id_seq; Type: SEQUENCE; Schema: hc; Owner: -
--

CREATE SEQUENCE hc.command_outbox_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: command_outbox_id_seq; Type: SEQUENCE OWNED BY; Schema: hc; Owner: -
--

ALTER SEQUENCE hc.command_outbox_id_seq OWNED BY hc.command_outbox.id;


--
-- Name: measurement; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.measurement (
    ts timestamp with time zone NOT NULL,
    entity_id bigint NOT NULL,
    key text NOT NULL,
    v_num double precision,
    v_bool boolean,
    v_text text,
    v_json jsonb,
    meta jsonb
)
WITH (autovacuum_analyze_scale_factor='0.02', autovacuum_analyze_threshold='10000');


--
-- Name: daily_measurement_count; Type: VIEW; Schema: hc; Owner: -
--

CREATE VIEW hc.daily_measurement_count AS
 SELECT (ts)::date AS nap,
    count(*) AS sorok
   FROM hc.measurement
  GROUP BY ((ts)::date);


--
-- Name: device; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.device (
    id bigint NOT NULL,
    platform hc.platform_t NOT NULL,
    ext_id text,
    name text NOT NULL,
    location text,
    model text,
    manufacturer text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: device_id_seq; Type: SEQUENCE; Schema: hc; Owner: -
--

CREATE SEQUENCE hc.device_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: device_id_seq; Type: SEQUENCE OWNED BY; Schema: hc; Owner: -
--

ALTER SEQUENCE hc.device_id_seq OWNED BY hc.device.id;


--
-- Name: domain_season_active; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.domain_season_active (
    domain text NOT NULL,
    profile text NOT NULL,
    activated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT domain_season_active_domain_check CHECK ((domain = ANY (ARRAY['irrigation'::text, 'climate'::text]))),
    CONSTRAINT domain_season_active_profile_check CHECK ((profile = ANY (ARRAY['summer'::text, 'winter'::text])))
);


--
-- Name: domain_season_profile; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.domain_season_profile (
    domain text NOT NULL,
    profile text NOT NULL,
    settings jsonb DEFAULT '{}'::jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT domain_season_profile_domain_check CHECK ((domain = ANY (ARRAY['irrigation'::text, 'climate'::text]))),
    CONSTRAINT domain_season_profile_profile_check CHECK ((profile = ANY (ARRAY['summer'::text, 'winter'::text])))
);


--
-- Name: entity; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.entity (
    id bigint NOT NULL,
    device_id bigint NOT NULL,
    name text NOT NULL,
    topic_base text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: entity_id_seq; Type: SEQUENCE; Schema: hc; Owner: -
--

CREATE SEQUENCE hc.entity_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: entity_id_seq; Type: SEQUENCE OWNED BY; Schema: hc; Owner: -
--

ALTER SEQUENCE hc.entity_id_seq OWNED BY hc.entity.id;


--
-- Name: entity_metric; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.entity_metric (
    entity_id bigint NOT NULL,
    metric_key text NOT NULL,
    store_mode text DEFAULT 'both'::text NOT NULL,
    deadband_num double precision,
    min_interval_sec integer,
    max_interval_sec integer,
    is_enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: entity_presence; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.entity_presence (
    entity_id bigint NOT NULL,
    last_seen_ts timestamp with time zone DEFAULT now() NOT NULL,
    status text DEFAULT 'unknown'::text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: entity_state; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.entity_state (
    entity_id bigint NOT NULL,
    key text NOT NULL,
    ts timestamp with time zone DEFAULT now() NOT NULL,
    v_num double precision,
    v_bool boolean,
    v_text text,
    v_json jsonb,
    meta jsonb
);


--
-- Name: event; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.event (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    type text NOT NULL,
    source text NOT NULL,
    domain text,
    entity_id bigint,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    received_at timestamp with time zone DEFAULT now() NOT NULL,
    correlation_id uuid,
    causation_id uuid,
    idempotency_key text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    status text DEFAULT 'recorded'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT event_source_check CHECK ((length(TRIM(BOTH FROM source)) > 0)),
    CONSTRAINT event_type_check CHECK ((length(TRIM(BOTH FROM type)) > 0))
);


--
-- Name: execution; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.execution (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    plan_id uuid,
    event_id uuid,
    correlation_id uuid,
    domain text NOT NULL,
    executor text DEFAULT 'legacy'::text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    attempt integer DEFAULT 0 NOT NULL,
    started_at timestamp with time zone,
    ended_at timestamp with time zone,
    command_topic text,
    command_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    confirmation jsonb DEFAULT '{}'::jsonb NOT NULL,
    result jsonb DEFAULT '{}'::jsonb NOT NULL,
    error text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT execution_domain_check CHECK ((length(TRIM(BOTH FROM domain)) > 0))
);


--
-- Name: irrigation_controller_temp_daily; Type: VIEW; Schema: hc; Owner: -
--

CREATE VIEW hc.irrigation_controller_temp_daily AS
 SELECT (date_trunc('day'::text, ts))::date AS day,
    round((avg(v_num))::numeric, 2) AS avg_controller_temp_c,
    round((min(v_num))::numeric, 2) AS min_controller_temp_c,
    round((max(v_num))::numeric, 2) AS max_controller_temp_c,
    count(*) AS samples
   FROM hc.measurement
  WHERE (key = 'controller_temp_c'::text)
  GROUP BY ((date_trunc('day'::text, ts))::date);


--
-- Name: irrigation_controller_temp_daily_summary; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.irrigation_controller_temp_daily_summary (
    day date NOT NULL,
    avg_controller_temp_c numeric,
    min_controller_temp_c numeric,
    max_controller_temp_c numeric,
    samples bigint,
    refreshed_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: irrigation_daily_energy; Type: VIEW; Schema: hc; Owner: -
--

CREATE VIEW hc.irrigation_daily_energy AS
 WITH current_samples AS (
         SELECT measurement.ts,
            GREATEST(measurement.v_num, (0)::double precision) AS current_a,
            lead(measurement.ts) OVER (ORDER BY measurement.ts) AS next_ts
           FROM hc.measurement
          WHERE (measurement.key = 'pump_current_a'::text)
        ), current_intervals AS (
         SELECT current_samples.ts AS start_ts,
            LEAST(COALESCE(current_samples.next_ts, current_samples.ts), (current_samples.ts + '00:05:00'::interval)) AS end_ts,
            current_samples.current_a
           FROM current_samples
        ), current_by_day AS (
         SELECT (g.day_start)::date AS day,
            current_intervals.current_a,
            EXTRACT(epoch FROM (LEAST(current_intervals.end_ts, (g.day_start + '1 day'::interval)) - GREATEST(current_intervals.start_ts, g.day_start))) AS seconds
           FROM (current_intervals
             CROSS JOIN LATERAL generate_series(date_trunc('day'::text, current_intervals.start_ts), date_trunc('day'::text, current_intervals.end_ts), '1 day'::interval) g(day_start))
          WHERE ((current_intervals.end_ts > current_intervals.start_ts) AND (LEAST(current_intervals.end_ts, (g.day_start + '1 day'::interval)) > GREATEST(current_intervals.start_ts, g.day_start)))
        ), daily_current AS (
         SELECT current_by_day.day,
            count(*) AS current_samples,
            round((avg(current_by_day.current_a))::numeric, 3) AS avg_current_a,
            round((max(current_by_day.current_a))::numeric, 3) AS max_current_a,
            round((sum(current_by_day.seconds) / 3600.0), 3) AS measured_hours,
            round((sum(
                CASE
                    WHEN (current_by_day.current_a > (0.05)::double precision) THEN current_by_day.seconds
                    ELSE (0)::numeric
                END) / 60.0), 1) AS active_minutes,
            round(((sum((current_by_day.current_a * (current_by_day.seconds)::double precision)) / (3600.0)::double precision))::numeric, 3) AS amp_hours
           FROM current_by_day
          GROUP BY current_by_day.day
        ), daily_voltage AS (
         SELECT (date_trunc('day'::text, measurement.ts))::date AS day,
            count(*) AS voltage_samples,
            round((avg(measurement.v_num))::numeric, 3) AS avg_voltage_v
           FROM hc.measurement
          WHERE (measurement.key = 'supply_voltage_12v'::text)
          GROUP BY ((date_trunc('day'::text, measurement.ts))::date)
        )
 SELECT c.day,
    c.current_samples,
    c.avg_current_a,
    c.max_current_a,
    c.measured_hours,
    c.active_minutes,
    c.amp_hours,
    v.voltage_samples,
    v.avg_voltage_v,
    round((c.amp_hours * v.avg_voltage_v), 2) AS watt_hours
   FROM (daily_current c
     LEFT JOIN daily_voltage v ON ((v.day = c.day)));


--
-- Name: irrigation_daily_energy_summary; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.irrigation_daily_energy_summary (
    day date NOT NULL,
    current_samples bigint,
    avg_current_a numeric,
    max_current_a numeric,
    measured_hours numeric,
    active_minutes numeric,
    amp_hours numeric,
    voltage_samples bigint,
    avg_voltage_v numeric,
    watt_hours numeric,
    refreshed_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: irrigation_manual_session; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.irrigation_manual_session (
    id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    requested_stop_at timestamp with time zone NOT NULL,
    safety_stop_at timestamp with time zone NOT NULL,
    stopped_at timestamp with time zone,
    status text DEFAULT 'running'::text NOT NULL,
    started_by text DEFAULT 'admin'::text NOT NULL,
    start_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    stop_payload jsonb,
    error text
);


--
-- Name: irrigation_manual_session_id_seq; Type: SEQUENCE; Schema: hc; Owner: -
--

CREATE SEQUENCE hc.irrigation_manual_session_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: irrigation_manual_session_id_seq; Type: SEQUENCE OWNED BY; Schema: hc; Owner: -
--

ALTER SEQUENCE hc.irrigation_manual_session_id_seq OWNED BY hc.irrigation_manual_session.id;


--
-- Name: irrigation_pilot_config; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.irrigation_pilot_config (
    id smallint DEFAULT 1 NOT NULL,
    mode text DEFAULT 'navigator'::text NOT NULL,
    base_duration_minutes integer DEFAULT 90 NOT NULL,
    rain_24h_threshold_mm numeric DEFAULT 5 NOT NULL,
    forecast_rain_threshold_mm numeric DEFAULT 5 NOT NULL,
    pop_threshold_percent integer DEFAULT 70 NOT NULL,
    heat_threshold_c numeric DEFAULT 32 NOT NULL,
    heat_correction_percent integer DEFAULT 20 NOT NULL,
    cold_threshold_c numeric DEFAULT 22 NOT NULL,
    cold_correction_percent integer DEFAULT '-20'::integer NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    soil_moisture_enabled boolean DEFAULT true NOT NULL,
    soil_sensor_topic_base text DEFAULT ''::text NOT NULL,
    soil_wet_skip_threshold_percent numeric DEFAULT 85 NOT NULL,
    soil_dry_threshold_percent numeric DEFAULT 45 NOT NULL,
    soil_dry_correction_percent integer DEFAULT 15 NOT NULL,
    soil_sample_max_age_hours integer DEFAULT 12 NOT NULL,
    heat_step_c numeric DEFAULT 5 NOT NULL,
    heat_multiplier_step numeric DEFAULT 0.1 NOT NULL,
    cold_step_c numeric DEFAULT 5 NOT NULL,
    cold_multiplier_step numeric DEFAULT '-0.1'::numeric NOT NULL,
    soil_wet_adjust_threshold_percent numeric DEFAULT 65 NOT NULL,
    soil_wet_multiplier_delta numeric DEFAULT '-0.5'::numeric NOT NULL,
    soil_dry_multiplier_delta numeric DEFAULT 0.15 NOT NULL,
    min_duration_multiplier numeric DEFAULT 0.2 NOT NULL,
    max_duration_multiplier numeric DEFAULT 1.5 NOT NULL,
    CONSTRAINT irrigation_pilot_config_base_duration_minutes_check CHECK (((base_duration_minutes >= 1) AND (base_duration_minutes <= 720))),
    CONSTRAINT irrigation_pilot_config_id_check CHECK ((id = 1)),
    CONSTRAINT irrigation_pilot_config_mode_check CHECK ((mode = ANY (ARRAY['navigator'::text, 'pilot'::text]))),
    CONSTRAINT irrigation_pilot_config_pop_threshold_percent_check CHECK (((pop_threshold_percent >= 0) AND (pop_threshold_percent <= 100)))
);


--
-- Name: irrigation_pilot_decision; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.irrigation_pilot_decision (
    id bigint NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    mode text NOT NULL,
    base_duration integer NOT NULL,
    final_duration integer NOT NULL,
    executed boolean DEFAULT false NOT NULL,
    reason text NOT NULL,
    triggered_rules jsonb DEFAULT '[]'::jsonb NOT NULL,
    weather_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    schedule_id bigint,
    execution_status text DEFAULT 'not_executed'::text NOT NULL,
    CONSTRAINT irrigation_pilot_decision_mode_check CHECK ((mode = ANY (ARRAY['navigator'::text, 'pilot'::text])))
);


--
-- Name: irrigation_pilot_decision_id_seq; Type: SEQUENCE; Schema: hc; Owner: -
--

CREATE SEQUENCE hc.irrigation_pilot_decision_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: irrigation_pilot_decision_id_seq; Type: SEQUENCE OWNED BY; Schema: hc; Owner: -
--

ALTER SEQUENCE hc.irrigation_pilot_decision_id_seq OWNED BY hc.irrigation_pilot_decision.id;


--
-- Name: irrigation_pump_daily; Type: VIEW; Schema: hc; Owner: -
--

CREATE VIEW hc.irrigation_pump_daily AS
 WITH samples AS (
         SELECT measurement.ts,
            COALESCE(measurement.v_bool, false) AS pump_running,
            lead(measurement.ts) OVER (ORDER BY measurement.ts) AS next_ts
           FROM hc.measurement
          WHERE (measurement.key = 'pump_running'::text)
        ), intervals AS (
         SELECT samples.ts AS start_ts,
            LEAST(COALESCE(samples.next_ts, samples.ts), (samples.ts + '00:05:00'::interval)) AS end_ts,
            samples.pump_running
           FROM samples
        ), by_day AS (
         SELECT (g.day_start)::date AS day,
            intervals.pump_running,
            EXTRACT(epoch FROM (LEAST(intervals.end_ts, (g.day_start + '1 day'::interval)) - GREATEST(intervals.start_ts, g.day_start))) AS seconds
           FROM (intervals
             CROSS JOIN LATERAL generate_series(date_trunc('day'::text, intervals.start_ts), date_trunc('day'::text, intervals.end_ts), '1 day'::interval) g(day_start))
          WHERE ((intervals.end_ts > intervals.start_ts) AND (LEAST(intervals.end_ts, (g.day_start + '1 day'::interval)) > GREATEST(intervals.start_ts, g.day_start)))
        )
 SELECT day,
    round((sum(
        CASE
            WHEN pump_running THEN seconds
            ELSE (0)::numeric
        END) / 60.0), 1) AS pump_running_minutes,
    round((sum(seconds) / 3600.0), 3) AS measured_hours,
    count(*) AS state_samples
   FROM by_day
  GROUP BY day;


--
-- Name: irrigation_pump_daily_summary; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.irrigation_pump_daily_summary (
    day date NOT NULL,
    pump_running_minutes numeric,
    measured_hours numeric,
    state_samples bigint,
    refreshed_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: irrigation_schedule; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.irrigation_schedule (
    id bigint NOT NULL,
    day_of_week smallint NOT NULL,
    label text NOT NULL,
    start_time time without time zone DEFAULT '06:00:00'::time without time zone NOT NULL,
    stop_time time without time zone DEFAULT '06:20:00'::time without time zone NOT NULL,
    is_active boolean DEFAULT false NOT NULL,
    last_started_on date,
    last_stopped_on date,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT irrigation_schedule_check CHECK ((start_time < stop_time)),
    CONSTRAINT irrigation_schedule_day_of_week_check CHECK (((day_of_week >= 0) AND (day_of_week <= 6)))
);


--
-- Name: irrigation_schedule_id_seq; Type: SEQUENCE; Schema: hc; Owner: -
--

CREATE SEQUENCE hc.irrigation_schedule_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: irrigation_schedule_id_seq; Type: SEQUENCE OWNED BY; Schema: hc; Owner: -
--

ALTER SEQUENCE hc.irrigation_schedule_id_seq OWNED BY hc.irrigation_schedule.id;


--
-- Name: irrigation_session_stats; Type: VIEW; Schema: hc; Owner: -
--

CREATE VIEW hc.irrigation_session_stats AS
 SELECT id,
    started_at,
    stopped_at,
    status,
    started_by,
    (start_payload ->> 'source'::text) AS source,
    (NULLIF((start_payload ->> 'schedule_id'::text), ''::text))::bigint AS schedule_id,
    (start_payload ->> 'schedule_label'::text) AS schedule_label,
    round((EXTRACT(epoch FROM (COALESCE(stopped_at, now()) - started_at)) / 60.0), 1) AS duration_minutes
   FROM hc.irrigation_manual_session s;


--
-- Name: irrigation_solar_daily; Type: VIEW; Schema: hc; Owner: -
--

CREATE VIEW hc.irrigation_solar_daily AS
 WITH charge_samples AS (
         SELECT measurement.ts,
            GREATEST(measurement.v_num, (0)::double precision) AS current_a,
            lead(measurement.ts) OVER (ORDER BY measurement.ts) AS next_ts
           FROM hc.measurement
          WHERE (measurement.key = 'solar_charge_current_a'::text)
        ), charge_intervals AS (
         SELECT charge_samples.ts AS start_ts,
            LEAST(COALESCE(charge_samples.next_ts, charge_samples.ts), (charge_samples.ts + '00:05:00'::interval)) AS end_ts,
            charge_samples.current_a
           FROM charge_samples
        ), charge_by_day AS (
         SELECT (g.day_start)::date AS day,
            charge_intervals.current_a,
            EXTRACT(epoch FROM (LEAST(charge_intervals.end_ts, (g.day_start + '1 day'::interval)) - GREATEST(charge_intervals.start_ts, g.day_start))) AS seconds
           FROM (charge_intervals
             CROSS JOIN LATERAL generate_series(date_trunc('day'::text, charge_intervals.start_ts), date_trunc('day'::text, charge_intervals.end_ts), '1 day'::interval) g(day_start))
          WHERE ((charge_intervals.end_ts > charge_intervals.start_ts) AND (LEAST(charge_intervals.end_ts, (g.day_start + '1 day'::interval)) > GREATEST(charge_intervals.start_ts, g.day_start)))
        ), metric_daily AS (
         SELECT (date_trunc('day'::text, measurement.ts))::date AS day,
            round((avg(measurement.v_num) FILTER (WHERE (measurement.key = 'solar_battery_voltage_v'::text)))::numeric, 3) AS avg_battery_voltage_v,
            round((min(measurement.v_num) FILTER (WHERE (measurement.key = 'solar_battery_voltage_v'::text)))::numeric, 3) AS min_battery_voltage_v,
            round((max(measurement.v_num) FILTER (WHERE (measurement.key = 'solar_battery_voltage_v'::text)))::numeric, 3) AS max_battery_voltage_v,
            round((avg(measurement.v_num) FILTER (WHERE (measurement.key = 'solar_charge_current_a'::text)))::numeric, 3) AS avg_charge_current_a,
            round((max(measurement.v_num) FILTER (WHERE (measurement.key = 'solar_charge_current_a'::text)))::numeric, 3) AS max_charge_current_a,
            round((avg(measurement.v_num) FILTER (WHERE (measurement.key = 'solar_pv_voltage_v'::text)))::numeric, 3) AS avg_pv_voltage_v,
            round((max(measurement.v_num) FILTER (WHERE (measurement.key = 'solar_pv_voltage_v'::text)))::numeric, 3) AS max_pv_voltage_v,
            round((avg(measurement.v_num) FILTER (WHERE (measurement.key = 'solar_pv_current_a'::text)))::numeric, 3) AS avg_pv_current_a,
            round((max(measurement.v_num) FILTER (WHERE (measurement.key = 'solar_pv_current_a'::text)))::numeric, 3) AS max_pv_current_a,
            round((avg(measurement.v_num) FILTER (WHERE (measurement.key = 'solar_controller_temp_c'::text)))::numeric, 2) AS avg_solar_controller_temp_c,
            round((max(measurement.v_num) FILTER (WHERE (measurement.key = 'solar_controller_temp_c'::text)))::numeric, 2) AS max_solar_controller_temp_c,
            count(*) AS samples
           FROM hc.measurement
          WHERE (measurement.key = ANY (ARRAY['solar_battery_voltage_v'::text, 'solar_charge_current_a'::text, 'solar_pv_voltage_v'::text, 'solar_pv_current_a'::text, 'solar_controller_temp_c'::text]))
          GROUP BY ((date_trunc('day'::text, measurement.ts))::date)
        ), charge_daily AS (
         SELECT charge_by_day.day,
            round(((sum((charge_by_day.current_a * (charge_by_day.seconds)::double precision)) / (3600.0)::double precision))::numeric, 3) AS charge_amp_hours,
            round((sum(charge_by_day.seconds) / 3600.0), 3) AS measured_hours
           FROM charge_by_day
          GROUP BY charge_by_day.day
        )
 SELECT m.day,
    m.avg_battery_voltage_v,
    m.min_battery_voltage_v,
    m.max_battery_voltage_v,
    m.avg_charge_current_a,
    m.max_charge_current_a,
    m.avg_pv_voltage_v,
    m.max_pv_voltage_v,
    m.avg_pv_current_a,
    m.max_pv_current_a,
    m.avg_solar_controller_temp_c,
    m.max_solar_controller_temp_c,
    m.samples,
    c.charge_amp_hours,
    c.measured_hours
   FROM (metric_daily m
     LEFT JOIN charge_daily c ON ((c.day = m.day)));


--
-- Name: irrigation_solar_daily_summary; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.irrigation_solar_daily_summary (
    day date NOT NULL,
    avg_battery_voltage_v numeric,
    min_battery_voltage_v numeric,
    max_battery_voltage_v numeric,
    avg_charge_current_a numeric,
    max_charge_current_a numeric,
    avg_pv_voltage_v numeric,
    max_pv_voltage_v numeric,
    avg_pv_current_a numeric,
    max_pv_current_a numeric,
    avg_solar_controller_temp_c numeric,
    max_solar_controller_temp_c numeric,
    samples bigint,
    charge_amp_hours numeric,
    measured_hours numeric,
    refreshed_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: irrigation_solar_pump_config; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.irrigation_solar_pump_config (
    id smallint DEFAULT 1 NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    daily_target_minutes integer DEFAULT 30 NOT NULL,
    batch_minutes integer DEFAULT 5 NOT NULL,
    cooldown_minutes integer DEFAULT 10 NOT NULL,
    min_charge_current_a numeric DEFAULT 0.8 NOT NULL,
    min_pv_voltage_v numeric DEFAULT 15 NOT NULL,
    min_battery_voltage_v numeric DEFAULT 12.2 NOT NULL,
    stop_battery_voltage_v numeric DEFAULT 11.8 NOT NULL,
    max_telemetry_age_seconds integer DEFAULT 180 NOT NULL,
    require_remote_mode boolean DEFAULT true NOT NULL,
    latest_decision jsonb,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT irrigation_solar_pump_config_batch_minutes_check CHECK (((batch_minutes >= 1) AND (batch_minutes <= 60))),
    CONSTRAINT irrigation_solar_pump_config_cooldown_minutes_check CHECK (((cooldown_minutes >= 0) AND (cooldown_minutes <= 240))),
    CONSTRAINT irrigation_solar_pump_config_daily_target_minutes_check CHECK (((daily_target_minutes >= 1) AND (daily_target_minutes <= 240))),
    CONSTRAINT irrigation_solar_pump_config_id_check CHECK ((id = 1)),
    CONSTRAINT irrigation_solar_pump_config_max_telemetry_age_seconds_check CHECK (((max_telemetry_age_seconds >= 10) AND (max_telemetry_age_seconds <= 3600)))
);


--
-- Name: irrigation_solar_pump_run; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.irrigation_solar_pump_run (
    id bigint NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    planned_stop_at timestamp with time zone NOT NULL,
    stopped_at timestamp with time zone,
    status text DEFAULT 'running'::text NOT NULL,
    start_payload jsonb,
    stop_payload jsonb,
    error text
);


--
-- Name: irrigation_solar_pump_run_id_seq; Type: SEQUENCE; Schema: hc; Owner: -
--

CREATE SEQUENCE hc.irrigation_solar_pump_run_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: irrigation_solar_pump_run_id_seq; Type: SEQUENCE OWNED BY; Schema: hc; Owner: -
--

ALTER SEQUENCE hc.irrigation_solar_pump_run_id_seq OWNED BY hc.irrigation_solar_pump_run.id;


--
-- Name: irrigation_tank_daily; Type: VIEW; Schema: hc; Owner: -
--

CREATE VIEW hc.irrigation_tank_daily AS
 SELECT (date_trunc('day'::text, ts))::date AS day,
    round((avg(v_num) FILTER (WHERE (key = 'liquid_level_percent'::text)))::numeric, 2) AS avg_level_percent,
    round((min(v_num) FILTER (WHERE (key = 'liquid_level_percent'::text)))::numeric, 2) AS min_level_percent,
    round((max(v_num) FILTER (WHERE (key = 'liquid_level_percent'::text)))::numeric, 2) AS max_level_percent,
    round((avg(v_num) FILTER (WHERE (key = 'liquid_depth'::text)))::numeric, 3) AS avg_depth_m
   FROM hc.measurement
  WHERE (key = ANY (ARRAY['liquid_level_percent'::text, 'liquid_depth'::text]))
  GROUP BY ((date_trunc('day'::text, ts))::date);


--
-- Name: irrigation_tank_daily_summary; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.irrigation_tank_daily_summary (
    day date NOT NULL,
    avg_level_percent numeric,
    min_level_percent numeric,
    max_level_percent numeric,
    avg_depth_m numeric,
    refreshed_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: metric; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.metric (
    key text NOT NULL,
    value_type hc.value_type_t NOT NULL,
    unit text,
    min_num double precision,
    max_num double precision,
    description text,
    enforce_validation boolean DEFAULT true NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mower_firmware_artifact; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.mower_firmware_artifact (
    artifact_id text NOT NULL,
    image bytea NOT NULL,
    elf bytea NOT NULL,
    saved_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT mower_firmware_artifact_artifact_id_check CHECK ((artifact_id ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT mower_firmware_artifact_elf_check CHECK (((octet_length(elf) >= 52) AND (octet_length(elf) <= 16777216))),
    CONSTRAINT mower_firmware_artifact_image_check CHECK ((((octet_length(image) >= 1280) AND (octet_length(image) <= 524288)) AND ((octet_length(image) % 32) = 0)))
);


--
-- Name: mower_firmware_exit; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.mower_firmware_exit (
    request_id text NOT NULL,
    session_request_id text NOT NULL,
    proof jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT mower_firmware_exit_proof_check CHECK ((jsonb_typeof(proof) = 'object'::text)),
    CONSTRAINT mower_firmware_exit_request_id_check CHECK ((request_id ~ '^[A-Za-z0-9_-]{1,64}$'::text))
);


--
-- Name: mower_firmware_job; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.mower_firmware_job (
    hc_job_id text NOT NULL,
    request_id text NOT NULL,
    artifact_id text NOT NULL,
    release_id text NOT NULL,
    state text NOT NULL,
    report jsonb NOT NULL,
    saved_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT mower_firmware_job_hc_job_id_check CHECK (((hc_job_id ~ '^[0-9A-F]{32}$'::text) AND (hc_job_id <> repeat('0'::text, 32)))),
    CONSTRAINT mower_firmware_job_release_id_check CHECK ((release_id ~ '^[A-Za-z0-9_.-]{1,64}$'::text)),
    CONSTRAINT mower_firmware_job_report_check CHECK ((jsonb_typeof(report) = 'object'::text)),
    CONSTRAINT mower_firmware_job_request_id_check CHECK ((request_id ~ '^[A-Za-z0-9_-]{1,64}$'::text)),
    CONSTRAINT mower_firmware_job_state_check CHECK ((state = 'HC_STAGED'::text))
);


--
-- Name: mower_firmware_operation; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.mower_firmware_operation (
    request_id text NOT NULL,
    session_request_id text NOT NULL,
    action text NOT NULL,
    state text NOT NULL,
    code text NOT NULL,
    service_boot text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT mower_firmware_operation_action_check CHECK ((action = ANY (ARRAY['IMAGE'::text, 'ABORT'::text, 'FINISH'::text]))),
    CONSTRAINT mower_firmware_operation_code_check CHECK ((code ~ '^[A-Z_0-9]{1,32}$'::text)),
    CONSTRAINT mower_firmware_operation_request_id_check CHECK ((request_id ~ '^[A-Za-z0-9_-]{1,64}$'::text)),
    CONSTRAINT mower_firmware_operation_service_boot_check CHECK (((service_boot ~ '^[0-9A-F]{16}$'::text) AND (service_boot <> repeat('0'::text, 16)))),
    CONSTRAINT mower_firmware_operation_state_check CHECK ((state = ANY (ARRAY['INTENT'::text, 'UNKNOWN'::text, 'ADMITTED'::text, 'REJECTED'::text])))
);


--
-- Name: mower_firmware_session; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.mower_firmware_session (
    request_id text NOT NULL,
    hc_job_id text NOT NULL,
    connection_key text NOT NULL,
    esp_boot text NOT NULL,
    profile_crc text NOT NULL,
    state text NOT NULL,
    update_id text,
    code text NOT NULL,
    revision integer NOT NULL,
    active boolean NOT NULL,
    singleton boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    closed boolean DEFAULT false NOT NULL,
    initial_stm_boot text,
    CONSTRAINT mower_firmware_session_active_check CHECK ((active = ((state <> 'REJECTED'::text) AND (NOT closed)))),
    CONSTRAINT mower_firmware_session_check1 CHECK (((state = 'ADMITTED'::text) = (update_id IS NOT NULL))),
    CONSTRAINT mower_firmware_session_check2 CHECK (((state = 'CREATE_INTENT'::text) = (revision = 1))),
    CONSTRAINT mower_firmware_session_code_check CHECK ((code ~ '^[A-Z_0-9]{1,32}$'::text)),
    CONSTRAINT mower_firmware_session_connection_key_check CHECK ((connection_key ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT mower_firmware_session_esp_boot_check CHECK (((esp_boot ~ '^[0-9A-F]{16}$'::text) AND (esp_boot <> repeat('0'::text, 16)))),
    CONSTRAINT mower_firmware_session_initial_stm_boot_check CHECK (((initial_stm_boot ~ '^[0-9A-F]{16}$'::text) AND (initial_stm_boot <> repeat('0'::text, 16)))),
    CONSTRAINT mower_firmware_session_profile_crc_check CHECK (((profile_crc ~ '^[0-9A-F]{8}$'::text) AND (profile_crc <> '00000000'::text))),
    CONSTRAINT mower_firmware_session_request_id_check CHECK ((request_id ~ '^[A-Za-z0-9_-]{1,64}$'::text)),
    CONSTRAINT mower_firmware_session_revision_check CHECK (((revision >= 1) AND (revision <= 2))),
    CONSTRAINT mower_firmware_session_singleton_check CHECK (singleton),
    CONSTRAINT mower_firmware_session_state_check CHECK ((state = ANY (ARRAY['CREATE_INTENT'::text, 'UNKNOWN'::text, 'ADMITTED'::text, 'REJECTED'::text]))),
    CONSTRAINT mower_firmware_session_update_id_check CHECK (((update_id ~ '^[0-9A-F]{32}$'::text) AND (update_id <> repeat('0'::text, 32))))
);


--
-- Name: mower_parameter_revision; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.mower_parameter_revision (
    rover_key text NOT NULL,
    revision bigint NOT NULL,
    expected_revision bigint NOT NULL,
    request_id text NOT NULL,
    parameters jsonb NOT NULL,
    draft_sha256 text NOT NULL,
    saved_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT mower_parameter_revision_check CHECK ((expected_revision = (revision - 1))),
    CONSTRAINT mower_parameter_revision_draft_sha256_check CHECK ((draft_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT mower_parameter_revision_parameters_check CHECK ((jsonb_typeof(parameters) = 'object'::text)),
    CONSTRAINT mower_parameter_revision_request_id_check CHECK ((request_id ~ '^[A-Za-z0-9_-]{1,64}$'::text)),
    CONSTRAINT mower_parameter_revision_revision_check CHECK (((revision >= 1) AND (revision <= '4294967295'::bigint))),
    CONSTRAINT mower_parameter_revision_rover_key_check CHECK ((rover_key ~ '^[A-Za-z0-9_-]{1,32}$'::text))
);


--
-- Name: mqtt_flood_state; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.mqtt_flood_state (
    topic_base text NOT NULL,
    entity_id bigint,
    active boolean DEFAULT false NOT NULL,
    severity text DEFAULT 'resolved'::text NOT NULL,
    window_count integer DEFAULT 0 NOT NULL,
    messages_per_minute double precision DEFAULT 0 NOT NULL,
    first_exceeded_at timestamp with time zone,
    detected_at timestamp with time zone,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    resolved_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT mqtt_flood_state_severity_check CHECK ((severity = ANY (ARRAY['warning'::text, 'critical'::text, 'resolved'::text])))
);


--
-- Name: notes; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.notes (
    id bigint NOT NULL,
    type text NOT NULL,
    text text NOT NULL,
    done boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    comment text DEFAULT ''::text NOT NULL,
    status text DEFAULT 'open'::text NOT NULL,
    scope text DEFAULT 'general'::text NOT NULL,
    CONSTRAINT notes_text_check CHECK ((length(TRIM(BOTH FROM text)) > 0)),
    CONSTRAINT notes_type_check CHECK ((type = ANY (ARRAY['issues'::text, 'requests'::text])))
);


--
-- Name: notes_id_seq; Type: SEQUENCE; Schema: hc; Owner: -
--

CREATE SEQUENCE hc.notes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: notes_id_seq; Type: SEQUENCE OWNED BY; Schema: hc; Owner: -
--

ALTER SEQUENCE hc.notes_id_seq OWNED BY hc.notes.id;


--
-- Name: opening_sensor_policy; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.opening_sensor_policy (
    entity_id bigint NOT NULL,
    opening_type text DEFAULT 'window'::text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    room_position integer,
    opening_label text,
    has_mosquito_net boolean DEFAULT false NOT NULL,
    rain_alert_enabled boolean DEFAULT false NOT NULL,
    climate_relevant boolean DEFAULT false NOT NULL,
    extractor_air_role text DEFAULT 'none'::text NOT NULL,
    CONSTRAINT opening_sensor_policy_extractor_air_role_check CHECK ((extractor_air_role = ANY (ARRAY['none'::text, 'secondary'::text, 'primary'::text]))),
    CONSTRAINT opening_sensor_policy_opening_type_check CHECK ((opening_type = ANY (ARRAY['window'::text, 'door'::text])))
);


--
-- Name: page_usage_event; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.page_usage_event (
    id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    page_id text NOT NULL,
    client_id text NOT NULL,
    device_class text NOT NULL,
    viewport_width integer,
    viewport_height integer,
    standalone boolean DEFAULT false NOT NULL,
    user_agent text
);


--
-- Name: page_usage_event_id_seq; Type: SEQUENCE; Schema: hc; Owner: -
--

CREATE SEQUENCE hc.page_usage_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: page_usage_event_id_seq; Type: SEQUENCE OWNED BY; Schema: hc; Owner: -
--

ALTER SEQUENCE hc.page_usage_event_id_seq OWNED BY hc.page_usage_event.id;


--
-- Name: plan; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.plan (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    event_id uuid,
    correlation_id uuid,
    domain text NOT NULL,
    type text NOT NULL,
    target_type text,
    target_ref text,
    entity_id bigint,
    status text DEFAULT 'planned'::text NOT NULL,
    intended_start_at timestamp with time zone,
    expires_at timestamp with time zone,
    reasoning text,
    inputs jsonb DEFAULT '{}'::jsonb NOT NULL,
    actions jsonb DEFAULT '[]'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by text DEFAULT 'system'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT plan_domain_check CHECK ((length(TRIM(BOTH FROM domain)) > 0)),
    CONSTRAINT plan_type_check CHECK ((length(TRIM(BOTH FROM type)) > 0))
);


--
-- Name: power_wall_policy; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.power_wall_policy (
    entity_id bigint NOT NULL,
    always_on boolean DEFAULT false NOT NULL,
    last_action_at timestamp with time zone,
    last_action text,
    last_error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    auto_climate boolean DEFAULT false NOT NULL,
    scheduler_enabled boolean DEFAULT false NOT NULL,
    scheduler_window_start time without time zone DEFAULT '20:00:00'::time without time zone NOT NULL,
    scheduler_window_end time without time zone DEFAULT '06:00:00'::time without time zone NOT NULL,
    scheduler_min_on_minutes integer DEFAULT 12 NOT NULL,
    scheduler_max_on_minutes integer DEFAULT 35 NOT NULL,
    scheduler_min_off_minutes integer DEFAULT 20 NOT NULL,
    scheduler_max_off_minutes integer DEFAULT 90 NOT NULL,
    scheduler_jitter_minutes integer DEFAULT 5 NOT NULL,
    display_name text,
    auto_climate_delay_minutes integer DEFAULT 0 NOT NULL,
    auto_climate_on_at timestamp with time zone,
    CONSTRAINT power_wall_policy_auto_climate_delay_minutes_check CHECK (((auto_climate_delay_minutes >= 0) AND (auto_climate_delay_minutes <= 120)))
);


--
-- Name: power_wall_schedule_session; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.power_wall_schedule_session (
    id bigint NOT NULL,
    entity_id bigint NOT NULL,
    planned_start_at timestamp with time zone NOT NULL,
    planned_end_at timestamp with time zone,
    actual_start_at timestamp with time zone,
    actual_end_at timestamp with time zone,
    duration_minutes integer,
    status text DEFAULT 'planned'::text NOT NULL,
    start_action jsonb,
    stop_action jsonb,
    error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT power_wall_schedule_session_status_check CHECK ((status = ANY (ARRAY['planned'::text, 'running'::text, 'completed'::text, 'cancelled'::text, 'failed'::text])))
);


--
-- Name: power_wall_schedule_session_id_seq; Type: SEQUENCE; Schema: hc; Owner: -
--

CREATE SEQUENCE hc.power_wall_schedule_session_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: power_wall_schedule_session_id_seq; Type: SEQUENCE OWNED BY; Schema: hc; Owner: -
--

ALTER SEQUENCE hc.power_wall_schedule_session_id_seq OWNED BY hc.power_wall_schedule_session.id;


--
-- Name: process_sensor_binding; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.process_sensor_binding (
    process_key text NOT NULL,
    entity_id bigint,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: scheduler_config; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.scheduler_config (
    id smallint DEFAULT 1 NOT NULL,
    mode text DEFAULT 'v2_execute_all'::text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_by text DEFAULT 'system'::text NOT NULL,
    notes text,
    CONSTRAINT scheduler_config_id_check CHECK ((id = 1)),
    CONSTRAINT scheduler_config_mode_check CHECK ((mode = ANY (ARRAY['v2_execute_irrigation'::text, 'v2_execute_x10'::text, 'v2_execute_climate'::text, 'v2_execute_x10_climate'::text, 'v2_execute_all'::text])))
);


--
-- Name: scheduler_job; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.scheduler_job (
    id bigint NOT NULL,
    domain text NOT NULL,
    action text NOT NULL,
    label text NOT NULL,
    schedule_kind text DEFAULT 'weekly'::text NOT NULL,
    day_of_week smallint,
    start_time time without time zone,
    stop_time time without time zone,
    is_enabled boolean DEFAULT false NOT NULL,
    source text DEFAULT 'unified'::text NOT NULL,
    source_ref text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT scheduler_job_day_of_week_check CHECK (((day_of_week >= 0) AND (day_of_week <= 6)))
);


--
-- Name: scheduler_job_id_seq; Type: SEQUENCE; Schema: hc; Owner: -
--

CREATE SEQUENCE hc.scheduler_job_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scheduler_job_id_seq; Type: SEQUENCE OWNED BY; Schema: hc; Owner: -
--

ALTER SEQUENCE hc.scheduler_job_id_seq OWNED BY hc.scheduler_job.id;


--
-- Name: scheduler_run; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.scheduler_run (
    id bigint NOT NULL,
    job_id bigint,
    domain text NOT NULL,
    action text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    attempt integer DEFAULT 0 NOT NULL,
    requested_at timestamp with time zone DEFAULT now() NOT NULL,
    started_at timestamp with time zone,
    confirmed_started_at timestamp with time zone,
    stop_requested_at timestamp with time zone,
    confirmed_stopped_at timestamp with time zone,
    completed_at timestamp with time zone,
    error text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    confirmation jsonb DEFAULT '{}'::jsonb NOT NULL,
    idempotency_key text
);


--
-- Name: scheduler_run_id_seq; Type: SEQUENCE; Schema: hc; Owner: -
--

CREATE SEQUENCE hc.scheduler_run_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scheduler_run_id_seq; Type: SEQUENCE OWNED BY; Schema: hc; Owner: -
--

ALTER SEQUENCE hc.scheduler_run_id_seq OWNED BY hc.scheduler_run.id;


--
-- Name: temperature_sensor_policy; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.temperature_sensor_policy (
    entity_id bigint NOT NULL,
    is_outdoor boolean DEFAULT false NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: weather_observation; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.weather_observation (
    id bigint NOT NULL,
    ts timestamp with time zone DEFAULT now() NOT NULL,
    source text DEFAULT 'openweathermap'::text NOT NULL,
    temperature_c numeric,
    humidity_percent numeric,
    wind_speed_mps numeric,
    rain_mm numeric,
    pop_percent numeric,
    uv_index numeric,
    cloudiness_percent numeric,
    pressure_hpa numeric,
    sunrise timestamp with time zone,
    sunset timestamp with time zone,
    forecast_rain_24h_mm numeric,
    forecast_pop_max_percent numeric,
    forecast_temp_max_c numeric,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    wind_deg numeric
);


--
-- Name: weather_observation_id_seq; Type: SEQUENCE; Schema: hc; Owner: -
--

CREATE SEQUENCE hc.weather_observation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: weather_observation_id_seq; Type: SEQUENCE OWNED BY; Schema: hc; Owner: -
--

ALTER SEQUENCE hc.weather_observation_id_seq OWNED BY hc.weather_observation.id;


--
-- Name: x10_map; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.x10_map (
    entity_id bigint NOT NULL,
    map_id integer NOT NULL,
    name text NOT NULL,
    png text,
    md5 text,
    is_current boolean DEFAULT false NOT NULL,
    has_room_data boolean DEFAULT false NOT NULL,
    source text DEFAULT 'seed'::text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: x10_room; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.x10_room (
    entity_id bigint NOT NULL,
    map_id integer NOT NULL,
    segment_id integer NOT NULL,
    name text NOT NULL,
    room_id text,
    room_type integer,
    neighbors jsonb DEFAULT '[]'::jsonb NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    source text DEFAULT 'seed'::text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: x10_schedule; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.x10_schedule (
    entity_id bigint NOT NULL,
    task_id integer NOT NULL,
    is_enabled boolean DEFAULT false NOT NULL,
    start_time text NOT NULL,
    days text NOT NULL,
    clean_mode integer,
    map_id integer,
    suction integer,
    water_level integer,
    segments jsonb DEFAULT '[]'::jsonb NOT NULL,
    raw text,
    is_weekly boolean DEFAULT false NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_hc_owned boolean DEFAULT false NOT NULL
);


--
-- Name: x10_schedule_day; Type: TABLE; Schema: hc; Owner: -
--

CREATE TABLE hc.x10_schedule_day (
    entity_id bigint NOT NULL,
    task_id integer NOT NULL,
    day_index integer NOT NULL,
    day_name text NOT NULL,
    is_enabled boolean DEFAULT false NOT NULL,
    start_time text NOT NULL,
    clean_mode integer,
    map_id integer,
    suction integer,
    water_level integer,
    segments jsonb DEFAULT '[]'::jsonb NOT NULL,
    raw text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_hc_owned boolean DEFAULT true NOT NULL,
    CONSTRAINT x10_schedule_day_day_index_check CHECK (((day_index >= 0) AND (day_index <= 6)))
);


--
-- Name: ai_chat_audit id; Type: DEFAULT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.ai_chat_audit ALTER COLUMN id SET DEFAULT nextval('hc.ai_chat_audit_id_seq'::regclass);


--
-- Name: climate_schedule_rule id; Type: DEFAULT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.climate_schedule_rule ALTER COLUMN id SET DEFAULT nextval('hc.climate_schedule_rule_id_seq'::regclass);


--
-- Name: combustion_safety_event id; Type: DEFAULT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.combustion_safety_event ALTER COLUMN id SET DEFAULT nextval('hc.combustion_safety_event_id_seq'::regclass);


--
-- Name: command_outbox id; Type: DEFAULT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.command_outbox ALTER COLUMN id SET DEFAULT nextval('hc.command_outbox_id_seq'::regclass);


--
-- Name: device id; Type: DEFAULT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.device ALTER COLUMN id SET DEFAULT nextval('hc.device_id_seq'::regclass);


--
-- Name: entity id; Type: DEFAULT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.entity ALTER COLUMN id SET DEFAULT nextval('hc.entity_id_seq'::regclass);


--
-- Name: irrigation_manual_session id; Type: DEFAULT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.irrigation_manual_session ALTER COLUMN id SET DEFAULT nextval('hc.irrigation_manual_session_id_seq'::regclass);


--
-- Name: irrigation_pilot_decision id; Type: DEFAULT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.irrigation_pilot_decision ALTER COLUMN id SET DEFAULT nextval('hc.irrigation_pilot_decision_id_seq'::regclass);


--
-- Name: irrigation_schedule id; Type: DEFAULT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.irrigation_schedule ALTER COLUMN id SET DEFAULT nextval('hc.irrigation_schedule_id_seq'::regclass);


--
-- Name: irrigation_solar_pump_run id; Type: DEFAULT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.irrigation_solar_pump_run ALTER COLUMN id SET DEFAULT nextval('hc.irrigation_solar_pump_run_id_seq'::regclass);


--
-- Name: notes id; Type: DEFAULT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.notes ALTER COLUMN id SET DEFAULT nextval('hc.notes_id_seq'::regclass);


--
-- Name: page_usage_event id; Type: DEFAULT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.page_usage_event ALTER COLUMN id SET DEFAULT nextval('hc.page_usage_event_id_seq'::regclass);


--
-- Name: power_wall_schedule_session id; Type: DEFAULT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.power_wall_schedule_session ALTER COLUMN id SET DEFAULT nextval('hc.power_wall_schedule_session_id_seq'::regclass);


--
-- Name: scheduler_job id; Type: DEFAULT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.scheduler_job ALTER COLUMN id SET DEFAULT nextval('hc.scheduler_job_id_seq'::regclass);


--
-- Name: scheduler_run id; Type: DEFAULT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.scheduler_run ALTER COLUMN id SET DEFAULT nextval('hc.scheduler_run_id_seq'::regclass);


--
-- Name: weather_observation id; Type: DEFAULT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.weather_observation ALTER COLUMN id SET DEFAULT nextval('hc.weather_observation_id_seq'::regclass);


--
-- Name: ai_chat_audit ai_chat_audit_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.ai_chat_audit
    ADD CONSTRAINT ai_chat_audit_pkey PRIMARY KEY (id);


--
-- Name: climate_schedule_rule climate_schedule_rule_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.climate_schedule_rule
    ADD CONSTRAINT climate_schedule_rule_pkey PRIMARY KEY (id);


--
-- Name: climate_window_guard climate_window_guard_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.climate_window_guard
    ADD CONSTRAINT climate_window_guard_pkey PRIMARY KEY (id);


--
-- Name: combustion_safety_config combustion_safety_config_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.combustion_safety_config
    ADD CONSTRAINT combustion_safety_config_pkey PRIMARY KEY (singleton);


--
-- Name: combustion_safety_event combustion_safety_event_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.combustion_safety_event
    ADD CONSTRAINT combustion_safety_event_pkey PRIMARY KEY (id);


--
-- Name: combustion_safety_runtime combustion_safety_runtime_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.combustion_safety_runtime
    ADD CONSTRAINT combustion_safety_runtime_pkey PRIMARY KEY (singleton);


--
-- Name: command_outbox command_outbox_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.command_outbox
    ADD CONSTRAINT command_outbox_pkey PRIMARY KEY (id);


--
-- Name: device device_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.device
    ADD CONSTRAINT device_pkey PRIMARY KEY (id);


--
-- Name: device device_platform_ext_id_key; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.device
    ADD CONSTRAINT device_platform_ext_id_key UNIQUE (platform, ext_id);


--
-- Name: domain_season_active domain_season_active_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.domain_season_active
    ADD CONSTRAINT domain_season_active_pkey PRIMARY KEY (domain);


--
-- Name: domain_season_profile domain_season_profile_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.domain_season_profile
    ADD CONSTRAINT domain_season_profile_pkey PRIMARY KEY (domain, profile);


--
-- Name: entity entity_device_id_name_key; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.entity
    ADD CONSTRAINT entity_device_id_name_key UNIQUE (device_id, name);


--
-- Name: entity_metric entity_metric_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.entity_metric
    ADD CONSTRAINT entity_metric_pkey PRIMARY KEY (entity_id, metric_key);


--
-- Name: entity entity_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.entity
    ADD CONSTRAINT entity_pkey PRIMARY KEY (id);


--
-- Name: entity_presence entity_presence_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.entity_presence
    ADD CONSTRAINT entity_presence_pkey PRIMARY KEY (entity_id);


--
-- Name: entity_state entity_state_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.entity_state
    ADD CONSTRAINT entity_state_pkey PRIMARY KEY (entity_id, key);


--
-- Name: event event_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.event
    ADD CONSTRAINT event_pkey PRIMARY KEY (id);


--
-- Name: execution execution_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.execution
    ADD CONSTRAINT execution_pkey PRIMARY KEY (id);


--
-- Name: irrigation_controller_temp_daily_summary irrigation_controller_temp_daily_summary_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.irrigation_controller_temp_daily_summary
    ADD CONSTRAINT irrigation_controller_temp_daily_summary_pkey PRIMARY KEY (day);


--
-- Name: irrigation_daily_energy_summary irrigation_daily_energy_summary_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.irrigation_daily_energy_summary
    ADD CONSTRAINT irrigation_daily_energy_summary_pkey PRIMARY KEY (day);


--
-- Name: irrigation_manual_session irrigation_manual_session_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.irrigation_manual_session
    ADD CONSTRAINT irrigation_manual_session_pkey PRIMARY KEY (id);


--
-- Name: irrigation_pilot_config irrigation_pilot_config_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.irrigation_pilot_config
    ADD CONSTRAINT irrigation_pilot_config_pkey PRIMARY KEY (id);


--
-- Name: irrigation_pilot_decision irrigation_pilot_decision_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.irrigation_pilot_decision
    ADD CONSTRAINT irrigation_pilot_decision_pkey PRIMARY KEY (id);


--
-- Name: irrigation_pump_daily_summary irrigation_pump_daily_summary_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.irrigation_pump_daily_summary
    ADD CONSTRAINT irrigation_pump_daily_summary_pkey PRIMARY KEY (day);


--
-- Name: irrigation_schedule irrigation_schedule_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.irrigation_schedule
    ADD CONSTRAINT irrigation_schedule_pkey PRIMARY KEY (id);


--
-- Name: irrigation_solar_daily_summary irrigation_solar_daily_summary_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.irrigation_solar_daily_summary
    ADD CONSTRAINT irrigation_solar_daily_summary_pkey PRIMARY KEY (day);


--
-- Name: irrigation_solar_pump_config irrigation_solar_pump_config_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.irrigation_solar_pump_config
    ADD CONSTRAINT irrigation_solar_pump_config_pkey PRIMARY KEY (id);


--
-- Name: irrigation_solar_pump_run irrigation_solar_pump_run_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.irrigation_solar_pump_run
    ADD CONSTRAINT irrigation_solar_pump_run_pkey PRIMARY KEY (id);


--
-- Name: irrigation_tank_daily_summary irrigation_tank_daily_summary_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.irrigation_tank_daily_summary
    ADD CONSTRAINT irrigation_tank_daily_summary_pkey PRIMARY KEY (day);


--
-- Name: measurement measurement_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.measurement
    ADD CONSTRAINT measurement_pkey PRIMARY KEY (entity_id, ts, key);


--
-- Name: metric metric_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.metric
    ADD CONSTRAINT metric_pkey PRIMARY KEY (key);


--
-- Name: mower_firmware_artifact mower_firmware_artifact_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mower_firmware_artifact
    ADD CONSTRAINT mower_firmware_artifact_pkey PRIMARY KEY (artifact_id);


--
-- Name: mower_firmware_exit mower_firmware_exit_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mower_firmware_exit
    ADD CONSTRAINT mower_firmware_exit_pkey PRIMARY KEY (request_id);


--
-- Name: mower_firmware_exit mower_firmware_exit_session_request_id_key; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mower_firmware_exit
    ADD CONSTRAINT mower_firmware_exit_session_request_id_key UNIQUE (session_request_id);


--
-- Name: mower_firmware_job mower_firmware_job_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mower_firmware_job
    ADD CONSTRAINT mower_firmware_job_pkey PRIMARY KEY (hc_job_id);


--
-- Name: mower_firmware_job mower_firmware_job_request_id_key; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mower_firmware_job
    ADD CONSTRAINT mower_firmware_job_request_id_key UNIQUE (request_id);


--
-- Name: mower_firmware_operation mower_firmware_operation_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mower_firmware_operation
    ADD CONSTRAINT mower_firmware_operation_pkey PRIMARY KEY (request_id);


--
-- Name: mower_firmware_operation mower_firmware_operation_session_request_id_action_key; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mower_firmware_operation
    ADD CONSTRAINT mower_firmware_operation_session_request_id_action_key UNIQUE (session_request_id, action);


--
-- Name: mower_firmware_session mower_firmware_session_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mower_firmware_session
    ADD CONSTRAINT mower_firmware_session_pkey PRIMARY KEY (request_id);


--
-- Name: mower_firmware_session mower_firmware_session_update_id_key; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mower_firmware_session
    ADD CONSTRAINT mower_firmware_session_update_id_key UNIQUE (update_id);


--
-- Name: mower_parameter_revision mower_parameter_revision_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mower_parameter_revision
    ADD CONSTRAINT mower_parameter_revision_pkey PRIMARY KEY (rover_key, revision);


--
-- Name: mower_parameter_revision mower_parameter_revision_rover_key_request_id_key; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mower_parameter_revision
    ADD CONSTRAINT mower_parameter_revision_rover_key_request_id_key UNIQUE (rover_key, request_id);


--
-- Name: mqtt_flood_state mqtt_flood_state_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mqtt_flood_state
    ADD CONSTRAINT mqtt_flood_state_pkey PRIMARY KEY (topic_base);


--
-- Name: notes notes_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.notes
    ADD CONSTRAINT notes_pkey PRIMARY KEY (id);


--
-- Name: opening_sensor_policy opening_sensor_policy_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.opening_sensor_policy
    ADD CONSTRAINT opening_sensor_policy_pkey PRIMARY KEY (entity_id);


--
-- Name: page_usage_event page_usage_event_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.page_usage_event
    ADD CONSTRAINT page_usage_event_pkey PRIMARY KEY (id);


--
-- Name: plan plan_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.plan
    ADD CONSTRAINT plan_pkey PRIMARY KEY (id);


--
-- Name: power_wall_policy power_wall_policy_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.power_wall_policy
    ADD CONSTRAINT power_wall_policy_pkey PRIMARY KEY (entity_id);


--
-- Name: power_wall_schedule_session power_wall_schedule_session_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.power_wall_schedule_session
    ADD CONSTRAINT power_wall_schedule_session_pkey PRIMARY KEY (id);


--
-- Name: process_sensor_binding process_sensor_binding_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.process_sensor_binding
    ADD CONSTRAINT process_sensor_binding_pkey PRIMARY KEY (process_key);


--
-- Name: scheduler_config scheduler_config_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.scheduler_config
    ADD CONSTRAINT scheduler_config_pkey PRIMARY KEY (id);


--
-- Name: scheduler_job scheduler_job_domain_source_source_ref_key; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.scheduler_job
    ADD CONSTRAINT scheduler_job_domain_source_source_ref_key UNIQUE (domain, source, source_ref);


--
-- Name: scheduler_job scheduler_job_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.scheduler_job
    ADD CONSTRAINT scheduler_job_pkey PRIMARY KEY (id);


--
-- Name: scheduler_run scheduler_run_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.scheduler_run
    ADD CONSTRAINT scheduler_run_pkey PRIMARY KEY (id);


--
-- Name: temperature_sensor_policy temperature_sensor_policy_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.temperature_sensor_policy
    ADD CONSTRAINT temperature_sensor_policy_pkey PRIMARY KEY (entity_id);


--
-- Name: weather_observation weather_observation_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.weather_observation
    ADD CONSTRAINT weather_observation_pkey PRIMARY KEY (id);


--
-- Name: x10_map x10_map_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.x10_map
    ADD CONSTRAINT x10_map_pkey PRIMARY KEY (entity_id, map_id);


--
-- Name: x10_room x10_room_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.x10_room
    ADD CONSTRAINT x10_room_pkey PRIMARY KEY (entity_id, map_id, segment_id);


--
-- Name: x10_schedule_day x10_schedule_day_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.x10_schedule_day
    ADD CONSTRAINT x10_schedule_day_pkey PRIMARY KEY (entity_id, task_id, day_index);


--
-- Name: x10_schedule x10_schedule_pkey; Type: CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.x10_schedule
    ADD CONSTRAINT x10_schedule_pkey PRIMARY KEY (entity_id, task_id);


--
-- Name: brin_measurement_ts; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX brin_measurement_ts ON hc.measurement USING brin (ts);


--
-- Name: irrigation_solar_pump_run_started_idx; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX irrigation_solar_pump_run_started_idx ON hc.irrigation_solar_pump_run USING btree (started_at DESC);


--
-- Name: ix_ai_chat_audit_created_at; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_ai_chat_audit_created_at ON hc.ai_chat_audit USING btree (created_at DESC);


--
-- Name: ix_ai_chat_audit_data_sources; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_ai_chat_audit_data_sources ON hc.ai_chat_audit USING gin (data_sources);


--
-- Name: ix_ai_chat_audit_skills; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_ai_chat_audit_skills ON hc.ai_chat_audit USING gin (skills);


--
-- Name: ix_climate_schedule_rule_day_time; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_climate_schedule_rule_day_time ON hc.climate_schedule_rule USING btree (day_of_week, start_time);


--
-- Name: ix_climate_schedule_rule_profile_day_time; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_climate_schedule_rule_profile_day_time ON hc.climate_schedule_rule USING btree (season_profile, day_of_week, start_time);


--
-- Name: ix_combustion_safety_event_ts; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_combustion_safety_event_ts ON hc.combustion_safety_event USING btree (ts DESC);


--
-- Name: ix_command_outbox_scheduled; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_command_outbox_scheduled ON hc.command_outbox USING btree (scheduled_at) WHERE (scheduled_at IS NOT NULL);


--
-- Name: ix_command_outbox_status; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_command_outbox_status ON hc.command_outbox USING btree (status, created_at);


--
-- Name: ix_device_platform_name; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_device_platform_name ON hc.device USING btree (platform, name);


--
-- Name: ix_entity_device; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_entity_device ON hc.entity USING btree (device_id);


--
-- Name: ix_entity_metric_entity; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_entity_metric_entity ON hc.entity_metric USING btree (entity_id);


--
-- Name: ix_entity_metric_key; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_entity_metric_key ON hc.entity_metric USING btree (metric_key);


--
-- Name: ix_entity_presence_status; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_entity_presence_status ON hc.entity_presence USING btree (status);


--
-- Name: ix_entity_state_ts; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_entity_state_ts ON hc.entity_state USING btree (ts DESC);


--
-- Name: ix_event_correlation_id; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_event_correlation_id ON hc.event USING btree (correlation_id);


--
-- Name: ix_event_domain_occurred_at; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_event_domain_occurred_at ON hc.event USING btree (domain, occurred_at DESC);


--
-- Name: ix_event_entity_occurred_at; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_event_entity_occurred_at ON hc.event USING btree (entity_id, occurred_at DESC);


--
-- Name: ix_event_occurred_at; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_event_occurred_at ON hc.event USING btree (occurred_at DESC);


--
-- Name: ix_event_type_occurred_at; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_event_type_occurred_at ON hc.event USING btree (type, occurred_at DESC);


--
-- Name: ix_execution_correlation_id; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_execution_correlation_id ON hc.execution USING btree (correlation_id);


--
-- Name: ix_execution_created_at; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_execution_created_at ON hc.execution USING btree (created_at DESC);


--
-- Name: ix_execution_domain_status_created_at; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_execution_domain_status_created_at ON hc.execution USING btree (domain, status, created_at DESC);


--
-- Name: ix_execution_event_id; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_execution_event_id ON hc.execution USING btree (event_id);


--
-- Name: ix_execution_plan_id; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_execution_plan_id ON hc.execution USING btree (plan_id);


--
-- Name: ix_irrigation_manual_session_status_stop; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_irrigation_manual_session_status_stop ON hc.irrigation_manual_session USING btree (status, requested_stop_at);


--
-- Name: ix_irrigation_pilot_decision_timestamp; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_irrigation_pilot_decision_timestamp ON hc.irrigation_pilot_decision USING btree ("timestamp" DESC);


--
-- Name: ix_irrigation_schedule_day_start; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_irrigation_schedule_day_start ON hc.irrigation_schedule USING btree (day_of_week, start_time, id);


--
-- Name: ix_measurement_entity_key_ts; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_measurement_entity_key_ts ON hc.measurement USING btree (entity_id, key, ts DESC);


--
-- Name: ix_measurement_key_ts; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_measurement_key_ts ON hc.measurement USING btree (key, ts DESC);


--
-- Name: ix_mqtt_flood_state_active_updated; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_mqtt_flood_state_active_updated ON hc.mqtt_flood_state USING btree (active, updated_at DESC);


--
-- Name: ix_notes_created_at; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_notes_created_at ON hc.notes USING btree (created_at DESC);


--
-- Name: ix_notes_scope_status_created_at; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_notes_scope_status_created_at ON hc.notes USING btree (scope, status, created_at DESC);


--
-- Name: ix_notes_type_done_created_at; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_notes_type_done_created_at ON hc.notes USING btree (type, done, created_at DESC);


--
-- Name: ix_page_usage_event_client; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_page_usage_event_client ON hc.page_usage_event USING btree (client_id, created_at DESC);


--
-- Name: ix_page_usage_event_created_at; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_page_usage_event_created_at ON hc.page_usage_event USING btree (created_at DESC);


--
-- Name: ix_page_usage_event_page_device; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_page_usage_event_page_device ON hc.page_usage_event USING btree (page_id, device_class, created_at DESC);


--
-- Name: ix_plan_correlation_id; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_plan_correlation_id ON hc.plan USING btree (correlation_id);


--
-- Name: ix_plan_created_at; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_plan_created_at ON hc.plan USING btree (created_at DESC);


--
-- Name: ix_plan_domain_status_created_at; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_plan_domain_status_created_at ON hc.plan USING btree (domain, status, created_at DESC);


--
-- Name: ix_plan_entity_created_at; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_plan_entity_created_at ON hc.plan USING btree (entity_id, created_at DESC);


--
-- Name: ix_plan_event_id; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_plan_event_id ON hc.plan USING btree (event_id);


--
-- Name: ix_power_wall_policy_always_on; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_power_wall_policy_always_on ON hc.power_wall_policy USING btree (always_on, last_action_at);


--
-- Name: ix_power_wall_policy_auto_climate; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_power_wall_policy_auto_climate ON hc.power_wall_policy USING btree (auto_climate, last_action_at);


--
-- Name: ix_power_wall_policy_scheduler; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_power_wall_policy_scheduler ON hc.power_wall_policy USING btree (scheduler_enabled, updated_at);


--
-- Name: ix_power_wall_schedule_session_entity_status; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_power_wall_schedule_session_entity_status ON hc.power_wall_schedule_session USING btree (entity_id, status, planned_start_at DESC);


--
-- Name: ix_process_sensor_binding_entity; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_process_sensor_binding_entity ON hc.process_sensor_binding USING btree (entity_id);


--
-- Name: ix_scheduler_job_due; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_scheduler_job_due ON hc.scheduler_job USING btree (is_enabled, day_of_week, start_time);


--
-- Name: ix_scheduler_run_requested; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_scheduler_run_requested ON hc.scheduler_run USING btree (requested_at DESC);


--
-- Name: ix_weather_observation_ts; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX ix_weather_observation_ts ON hc.weather_observation USING btree (ts DESC);


--
-- Name: mower_firmware_one_active_session; Type: INDEX; Schema: hc; Owner: -
--

CREATE UNIQUE INDEX mower_firmware_one_active_session ON hc.mower_firmware_session USING btree (singleton) WHERE active;


--
-- Name: ux_event_idempotency_key; Type: INDEX; Schema: hc; Owner: -
--

CREATE UNIQUE INDEX ux_event_idempotency_key ON hc.event USING btree (idempotency_key) WHERE (idempotency_key IS NOT NULL);


--
-- Name: ux_execution_plan_id; Type: INDEX; Schema: hc; Owner: -
--

CREATE UNIQUE INDEX ux_execution_plan_id ON hc.execution USING btree (plan_id) WHERE (plan_id IS NOT NULL);


--
-- Name: ux_plan_event_id; Type: INDEX; Schema: hc; Owner: -
--

CREATE UNIQUE INDEX ux_plan_event_id ON hc.plan USING btree (event_id) WHERE (event_id IS NOT NULL);


--
-- Name: ux_scheduler_run_idempotency; Type: INDEX; Schema: hc; Owner: -
--

CREATE UNIQUE INDEX ux_scheduler_run_idempotency ON hc.scheduler_run USING btree (idempotency_key) WHERE (idempotency_key IS NOT NULL);


--
-- Name: x10_map_entity_name_idx; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX x10_map_entity_name_idx ON hc.x10_map USING btree (entity_id, name);


--
-- Name: x10_room_entity_map_name_idx; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX x10_room_entity_map_name_idx ON hc.x10_room USING btree (entity_id, map_id, name);


--
-- Name: x10_schedule_day_entity_day_idx; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX x10_schedule_day_entity_day_idx ON hc.x10_schedule_day USING btree (entity_id, day_index, start_time);


--
-- Name: x10_schedule_day_entity_owned_idx; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX x10_schedule_day_entity_owned_idx ON hc.x10_schedule_day USING btree (entity_id, is_hc_owned, day_index);


--
-- Name: x10_schedule_entity_owned_idx; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX x10_schedule_entity_owned_idx ON hc.x10_schedule USING btree (entity_id, is_hc_owned, task_id);


--
-- Name: x10_schedule_entity_weekly_idx; Type: INDEX; Schema: hc; Owner: -
--

CREATE INDEX x10_schedule_entity_weekly_idx ON hc.x10_schedule USING btree (entity_id, is_weekly, task_id);


--
-- Name: device trg_device_updated_at; Type: TRIGGER; Schema: hc; Owner: -
--

CREATE TRIGGER trg_device_updated_at BEFORE UPDATE ON hc.device FOR EACH ROW EXECUTE FUNCTION hc.tg_set_updated_at();


--
-- Name: measurement trg_touch_presence_measurement; Type: TRIGGER; Schema: hc; Owner: -
--

CREATE TRIGGER trg_touch_presence_measurement AFTER INSERT ON hc.measurement FOR EACH ROW EXECUTE FUNCTION hc.tg_touch_presence();

ALTER TABLE hc.measurement DISABLE TRIGGER trg_touch_presence_measurement;


--
-- Name: entity_state trg_touch_presence_state; Type: TRIGGER; Schema: hc; Owner: -
--

CREATE TRIGGER trg_touch_presence_state AFTER INSERT OR UPDATE ON hc.entity_state FOR EACH ROW EXECUTE FUNCTION hc.tg_touch_presence();

ALTER TABLE hc.entity_state DISABLE TRIGGER trg_touch_presence_state;


--
-- Name: entity_state trg_validate_entity_state; Type: TRIGGER; Schema: hc; Owner: -
--

CREATE TRIGGER trg_validate_entity_state BEFORE INSERT OR UPDATE ON hc.entity_state FOR EACH ROW EXECUTE FUNCTION hc.tg_validate_entity_state();


--
-- Name: measurement trg_validate_measurement; Type: TRIGGER; Schema: hc; Owner: -
--

CREATE TRIGGER trg_validate_measurement BEFORE INSERT ON hc.measurement FOR EACH ROW EXECUTE FUNCTION hc.tg_validate_measurement();


--
-- Name: command_outbox command_outbox_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.command_outbox
    ADD CONSTRAINT command_outbox_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE SET NULL;


--
-- Name: entity entity_device_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.entity
    ADD CONSTRAINT entity_device_id_fkey FOREIGN KEY (device_id) REFERENCES hc.device(id) ON DELETE CASCADE;


--
-- Name: entity_metric entity_metric_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.entity_metric
    ADD CONSTRAINT entity_metric_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE CASCADE;


--
-- Name: entity_presence entity_presence_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.entity_presence
    ADD CONSTRAINT entity_presence_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE CASCADE;


--
-- Name: entity_state entity_state_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.entity_state
    ADD CONSTRAINT entity_state_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE CASCADE;


--
-- Name: event event_causation_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.event
    ADD CONSTRAINT event_causation_id_fkey FOREIGN KEY (causation_id) REFERENCES hc.event(id) ON DELETE SET NULL;


--
-- Name: event event_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.event
    ADD CONSTRAINT event_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE SET NULL;


--
-- Name: execution execution_event_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.execution
    ADD CONSTRAINT execution_event_id_fkey FOREIGN KEY (event_id) REFERENCES hc.event(id) ON DELETE SET NULL;


--
-- Name: execution execution_plan_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.execution
    ADD CONSTRAINT execution_plan_id_fkey FOREIGN KEY (plan_id) REFERENCES hc.plan(id) ON DELETE SET NULL;


--
-- Name: measurement measurement_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.measurement
    ADD CONSTRAINT measurement_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE CASCADE;


--
-- Name: mower_firmware_exit mower_firmware_exit_session_request_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mower_firmware_exit
    ADD CONSTRAINT mower_firmware_exit_session_request_id_fkey FOREIGN KEY (session_request_id) REFERENCES hc.mower_firmware_session(request_id);


--
-- Name: mower_firmware_job mower_firmware_job_artifact_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mower_firmware_job
    ADD CONSTRAINT mower_firmware_job_artifact_id_fkey FOREIGN KEY (artifact_id) REFERENCES hc.mower_firmware_artifact(artifact_id);


--
-- Name: mower_firmware_operation mower_firmware_operation_session_request_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mower_firmware_operation
    ADD CONSTRAINT mower_firmware_operation_session_request_id_fkey FOREIGN KEY (session_request_id) REFERENCES hc.mower_firmware_session(request_id);


--
-- Name: mower_firmware_session mower_firmware_session_hc_job_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mower_firmware_session
    ADD CONSTRAINT mower_firmware_session_hc_job_id_fkey FOREIGN KEY (hc_job_id) REFERENCES hc.mower_firmware_job(hc_job_id);


--
-- Name: mqtt_flood_state mqtt_flood_state_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.mqtt_flood_state
    ADD CONSTRAINT mqtt_flood_state_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE SET NULL;


--
-- Name: opening_sensor_policy opening_sensor_policy_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.opening_sensor_policy
    ADD CONSTRAINT opening_sensor_policy_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE CASCADE;


--
-- Name: plan plan_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.plan
    ADD CONSTRAINT plan_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE SET NULL;


--
-- Name: plan plan_event_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.plan
    ADD CONSTRAINT plan_event_id_fkey FOREIGN KEY (event_id) REFERENCES hc.event(id) ON DELETE SET NULL;


--
-- Name: power_wall_policy power_wall_policy_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.power_wall_policy
    ADD CONSTRAINT power_wall_policy_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE CASCADE;


--
-- Name: power_wall_schedule_session power_wall_schedule_session_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.power_wall_schedule_session
    ADD CONSTRAINT power_wall_schedule_session_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE CASCADE;


--
-- Name: process_sensor_binding process_sensor_binding_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.process_sensor_binding
    ADD CONSTRAINT process_sensor_binding_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE SET NULL;


--
-- Name: scheduler_run scheduler_run_job_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.scheduler_run
    ADD CONSTRAINT scheduler_run_job_id_fkey FOREIGN KEY (job_id) REFERENCES hc.scheduler_job(id) ON DELETE SET NULL;


--
-- Name: temperature_sensor_policy temperature_sensor_policy_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.temperature_sensor_policy
    ADD CONSTRAINT temperature_sensor_policy_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE CASCADE;


--
-- Name: x10_map x10_map_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.x10_map
    ADD CONSTRAINT x10_map_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE CASCADE;


--
-- Name: x10_room x10_room_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.x10_room
    ADD CONSTRAINT x10_room_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE CASCADE;


--
-- Name: x10_room x10_room_entity_id_map_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.x10_room
    ADD CONSTRAINT x10_room_entity_id_map_id_fkey FOREIGN KEY (entity_id, map_id) REFERENCES hc.x10_map(entity_id, map_id) ON DELETE CASCADE;


--
-- Name: x10_schedule_day x10_schedule_day_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.x10_schedule_day
    ADD CONSTRAINT x10_schedule_day_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE CASCADE;


--
-- Name: x10_schedule x10_schedule_entity_id_fkey; Type: FK CONSTRAINT; Schema: hc; Owner: -
--

ALTER TABLE ONLY hc.x10_schedule
    ADD CONSTRAINT x10_schedule_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES hc.entity(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--


