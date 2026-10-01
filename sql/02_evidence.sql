-- Step 3: the evidence. evidence.py writes each block to results/<name>.csv; requirements.yaml cites them by name.

-- name: exclusions
SELECT 'test cases' AS dropped, count(*) AS cases FROM raw WHERE source = 'Test'
UNION ALL SELECT 'no channel recorded', count(*) FROM raw WHERE source IS NULL
UNION ALL SELECT 'kept', (SELECT count(*) FROM cases);

-- name: outcomes
-- How closed cases ended. "intake" outcomes are the ones a better front door could prevent.
SELECT outcome_group, outcome, count(*) AS cases, round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct_of_closed
  FROM closed GROUP BY ALL ORDER BY cases DESC;

-- name: taxonomy_quality
SELECT count(*) AS closed_cases, count(*) FILTER (WHERE outcome <> 'unclassified') AS classified,
       round(100.0 * count(*) FILTER (WHERE outcome <> 'unclassified') / count(*), 2) AS coverage_pct,
       count(*) FILTER (WHERE notes IS NULL) AS closed_without_note,
       count(DISTINCT notes) AS distinct_closure_notes,
       count(DISTINCT notes) FILTER (WHERE outcome = 'resolved') AS distinct_notes_meaning_resolved,
       count(DISTINCT notes) FILTER (WHERE outcome = 'duplicate') AS distinct_notes_meaning_duplicate,
       count(*) FILTER (WHERE closed < requested) AS closed_before_requested
  FROM closed;

-- name: channels
SELECT channel, count(*) AS cases, round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct,
       round(100.0 * count(*) FILTER (WHERE lat IS NULL) / count(*), 1) AS pct_no_coordinates
  FROM cases GROUP BY 1 ORDER BY 2 DESC;

-- name: intake_failure_by_channel
-- Raw rate, and the rate expected from the channel's own service mix (indirect standardisation): a channel that mostly
-- carries parking complaints would look bad on "not found" for reasons that have nothing to do with the channel.
WITH base AS (SELECT service, channel, outcome_group = 'intake' AS fail FROM closed WHERE channel IN ('Mobile', 'Web', 'Phone')),
     svc AS (SELECT service, avg(fail::int) AS svc_rate FROM base GROUP BY 1)
SELECT channel, count(*) AS closed_cases, round(100 * avg(fail::int), 1) AS intake_failure_pct,
       round(100 * avg(svc_rate), 1) AS expected_from_service_mix_pct,
       round(avg(fail::int) / avg(svc_rate), 2) AS observed_vs_expected
  FROM base JOIN svc USING (service) GROUP BY 1 ORDER BY 1;

-- name: intake_failures_by_service
SELECT service, count(*) AS closed_cases,
       count(*) FILTER (WHERE outcome = 'duplicate') AS duplicate, count(*) FILTER (WHERE outcome = 'cannot_locate') AS cannot_locate,
       count(*) FILTER (WHERE outcome = 'wrong_agency') AS wrong_agency, count(*) FILTER (WHERE outcome = 'insufficient_info') AS insufficient_info,
       count(*) FILTER (WHERE outcome = 'out_of_scope') AS out_of_scope,
       round(100.0 * count(*) FILTER (WHERE outcome_group = 'intake') / count(*), 1) AS intake_failure_pct
  FROM closed GROUP BY 1 HAVING count(*) >= 5000 ORDER BY intake_failure_pct DESC;

-- name: location_quality
-- Outside parking and encampments, does a case without map coordinates end "unable to locate" more often?
SELECT lat IS NOT NULL AS has_coordinates, count(*) AS closed_cases, count(*) FILTER (WHERE outcome = 'cannot_locate') AS cannot_locate,
       round(100.0 * count(*) FILTER (WHERE outcome = 'cannot_locate') / count(*), 2) AS cannot_locate_pct
  FROM closed WHERE service NOT IN ('Parking Enforcement', 'Encampment') GROUP BY 1 ORDER BY 1;

-- name: photo_effect
-- Mobile reports carry a direct photo link when the reporter attached one. Web links point to a form endpoint whose
-- contents are unknown, so only Mobile is compared. Expected rates come from each group's own service mix.
WITH m AS (SELECT service, regexp_matches(coalesce(media, ''), '\.(jpg|jpeg|png|heic)') AS has_photo, outcome
             FROM closed JOIN (SELECT service_request_id AS id, media_url AS media FROM raw) USING (id) WHERE channel = 'Mobile'),
     svc AS (SELECT service, avg((outcome = 'cannot_locate')::int) AS r_loc, avg((outcome = 'no_work_needed')::int) AS r_nwn FROM m GROUP BY 1)
SELECT has_photo, count(*) AS closed_cases,
       round(100 * avg((outcome = 'cannot_locate')::int), 2) AS cannot_locate_pct, round(100 * avg(r_loc), 2) AS cannot_locate_expected_pct,
       round(100 * avg((outcome = 'no_work_needed')::int), 2) AS no_work_needed_pct, round(100 * avg(r_nwn), 2) AS no_work_needed_expected_pct
  FROM m JOIN svc USING (service) GROUP BY 1 ORDER BY 1;

-- name: parking_response
-- Time-sensitive parking complaints only (illegal parking, sidewalk, blocked driveway): abandoned vehicles follow a
-- 72-hour process, and double-parking and bike-lane reports are logged, not attended. "Gone" = any closure saying the
-- car had left (both wordings). Hours to close approximates response time; the data has no arrival time.
SELECT CASE WHEN hours_to_close < 1 THEN '1: under 1 h' WHEN hours_to_close < 2 THEN '2: 1-2 h' WHEN hours_to_close < 4 THEN '3: 2-4 h'
            WHEN hours_to_close < 8 THEN '4: 4-8 h' ELSE '5: 8 h or more' END AS time_to_close,
       count(*) AS closed_cases, round(100.0 * count(*) FILTER (WHERE outcome_group = 'moved_on') / count(*), 1) AS gone_pct
  FROM closed
 WHERE service = 'Parking Enforcement' AND hours_to_close >= 0
   AND subtype IN ('other_illegal_parking', 'parking_on_sidewalk', 'blocking_driveway_cite_only', 'blocking_driveway_cite_tow')
 GROUP BY 1 ORDER BY 1;

-- name: parking_response_summary
SELECT count(*) AS closed_cases, round(median(hours_to_close), 2) AS median_hours, round(quantile_cont(hours_to_close, 0.9), 2) AS p90_hours,
       round(100.0 * count(*) FILTER (WHERE hours_to_close < 1) / count(*), 1) AS pct_within_1h,
       count(*) FILTER (WHERE outcome_group = 'moved_on') AS gone
  FROM closed
 WHERE service = 'Parking Enforcement' AND hours_to_close >= 0
   AND subtype IN ('other_illegal_parking', 'parking_on_sidewalk', 'blocking_driveway_cite_only', 'blocking_driveway_cite_tow');

-- name: wrong_agency_destinations
-- Where "wrong agency" cases were sent; only standard, high-volume notes, trimmed to the destination.
SELECT CASE WHEN notes ILIKE '%PG&E%' OR notes ILIKE '%PG & E%' THEN 'PG&E (not a city agency)'
            WHEN notes ILIKE '%postal service%' OR notes ILIKE '%USPS%' THEN 'US Postal Service'
            WHEN notes ILIKE '%SFPD%' OR notes ILIKE '%police%' THEN 'Police (non-emergency)'
            WHEN notes ILIKE '%caltrans%' OR notes ILIKE '%state%' THEN 'State / Caltrans'
            WHEN notes ILIKE '%DPH%' OR notes ILIKE '%public health%' THEN 'Public Health'
            ELSE 'another city department' END AS sent_to, count(*) AS cases
  FROM closed WHERE outcome = 'wrong_agency' GROUP BY 1 ORDER BY 2 DESC;

-- name: load_profile
-- Capacity evidence: busiest minute, hour and day of new cases, and same-second bursts.
WITH m AS (SELECT date_trunc('minute', requested) AS t, count(*) AS n FROM cases GROUP BY 1),
     h AS (SELECT date_trunc('hour', requested) AS t, count(*) AS n FROM cases GROUP BY 1),
     d AS (SELECT date_trunc('day', requested) AS t, count(*) AS n FROM cases GROUP BY 1),
     s AS (SELECT requested, count(*) AS n FROM cases GROUP BY 1)
SELECT (SELECT max(n) FROM m) AS peak_per_minute, (SELECT max(n) FROM h) AS peak_per_hour,
       (SELECT round(quantile_cont(n, 0.99)) FROM h) AS p99_per_hour, (SELECT max(n) FROM d) AS peak_per_day,
       (SELECT round(avg(n)) FROM d) AS mean_per_day, (SELECT max(n) FROM s) AS max_same_second;

-- name: open_by_month
-- How many cases are still open, by month requested: recent months have not had time to close.
SELECT strftime(requested, '%Y-%m') AS month, count(*) AS cases, count(*) FILTER (WHERE status <> 'Closed') AS still_open,
       round(100.0 * count(*) FILTER (WHERE status <> 'Closed') / count(*), 1) AS pct_open
  FROM cases GROUP BY 1 ORDER BY 1;
