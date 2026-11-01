begin;

create table if not exists hc.notes (
  id bigserial primary key,
  type text not null check (type in ('issues', 'requests')),
  text text not null check (length(trim(text)) > 0),
  comment text not null default '',
  done boolean not null default false,
  status text not null default 'open',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table hc.notes
  add column if not exists comment text not null default '';
alter table hc.notes
  add column if not exists status text not null default 'open';

update hc.notes
set status = case when done then 'tested' else 'open' end
where status is null or status = '' or (done = true and status = 'open');

create index if not exists ix_notes_type_done_created_at
  on hc.notes (type, done, created_at desc);

create index if not exists ix_notes_created_at
  on hc.notes (created_at desc);

commit;
