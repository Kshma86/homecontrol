begin;

alter table hc.notes
  add column if not exists scope text not null default 'general';

create index if not exists ix_notes_scope_status_created_at
  on hc.notes (scope, status, created_at desc);

commit;
