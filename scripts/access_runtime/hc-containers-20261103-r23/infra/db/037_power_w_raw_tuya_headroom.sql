begin;

-- Some Tuya meters report power in deciwatts and are scaled for display by
-- domain services. Keep validation high enough so plausible AC loads are not
-- dropped before scaling.
update hc.metric
set max_num = 100000
where key = 'power_w'
  and coalesce(max_num, 0) < 100000;

commit;
