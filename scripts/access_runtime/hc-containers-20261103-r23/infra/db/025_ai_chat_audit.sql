create table if not exists hc.ai_chat_audit (
    id bigserial primary key,
    created_at timestamptz not null default now(),
    started_at timestamptz,
    question text not null,
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
    skills jsonb not null default '[]'::jsonb,
    data_sources jsonb not null default '[]'::jsonb,
    skill_timings jsonb not null default '[]'::jsonb,
    context_timings jsonb not null default '[]'::jsonb,
    upstream jsonb not null default '{}'::jsonb,
    request_meta jsonb not null default '{}'::jsonb
);

create index if not exists ix_ai_chat_audit_created_at on hc.ai_chat_audit (created_at desc);
create index if not exists ix_ai_chat_audit_skills on hc.ai_chat_audit using gin (skills);
create index if not exists ix_ai_chat_audit_data_sources on hc.ai_chat_audit using gin (data_sources);
