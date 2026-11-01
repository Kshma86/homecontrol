create table if not exists hc.domain_season_profile (
  domain text not null check (domain in ('irrigation', 'climate')),
  profile text not null check (profile in ('summer', 'winter')),
  settings jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  primary key (domain, profile)
);

create table if not exists hc.domain_season_active (
  domain text primary key check (domain in ('irrigation', 'climate')),
  profile text not null check (profile in ('summer', 'winter')),
  activated_at timestamptz not null default now()
);

insert into hc.domain_season_profile (domain, profile, settings) values
  ('irrigation', 'summer', '{"control_enabled": true}'::jsonb),
  ('irrigation', 'winter', '{"control_enabled": false}'::jsonb),
  ('climate', 'summer', '{}'::jsonb),
  ('climate', 'winter', '{}'::jsonb)
on conflict (domain, profile) do nothing;

insert into hc.domain_season_active (domain, profile) values
  ('irrigation', 'summer'),
  ('climate', 'summer')
on conflict (domain) do nothing;
