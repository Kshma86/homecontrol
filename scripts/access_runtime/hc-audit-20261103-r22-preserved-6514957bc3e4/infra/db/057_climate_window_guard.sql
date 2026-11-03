create table if not exists hc.climate_window_guard (
 id integer primary key check(id=1),
 open_delay_seconds integer not null default 60,
 close_delay_seconds integer not null default 60,
 desired jsonb not null default '{}',
 suspended boolean not null default false
);
insert into hc.climate_window_guard(id) values(1) on conflict do nothing;
