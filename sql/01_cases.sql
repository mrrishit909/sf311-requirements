-- Step 2: one clean table of cases ({raw} and {rules} filled in by evidence.py).
-- Test cases and cases with no channel are dropped here and counted in results/exclusions.csv.
CREATE OR REPLACE TABLE raw AS SELECT * FROM read_parquet('{raw}');

CREATE OR REPLACE TABLE rules AS SELECT * FROM read_csv('{rules}', header = true, all_varchar = true);

CREATE OR REPLACE TABLE cases AS
SELECT service_request_id AS id,
       CAST(requested_datetime AS TIMESTAMP) AS requested,
       CAST(closed_date AS TIMESTAMP) AS closed,
       status_description AS status,
       nullif(trim(status_notes), '') AS notes,
       agency_responsible AS agency,
       service_name AS service, service_subtype AS subtype, service_details AS details,
       source AS channel,
       TRY_CAST(lat AS DOUBLE) AS lat, TRY_CAST(long AS DOUBLE) AS lon,
       media_url IS NOT NULL AS has_media_link,
       supervisor_district AS district, analysis_neighborhood AS neighborhood
  FROM raw
 WHERE source IS NOT NULL AND source <> 'Test';

-- First matching rule wins (rules are ordered); closed cases only, open statuses are not outcomes.
CREATE OR REPLACE TABLE outcome AS
SELECT c.id, coalesce(m.outcome, 'unclassified') AS outcome, coalesce(m."group", 'unclassified') AS outcome_group
  FROM cases c
  LEFT JOIN (SELECT c.id, arg_min(r.outcome, CAST(r."order" AS INTEGER)) AS outcome, arg_min(r."group", CAST(r."order" AS INTEGER)) AS "group"
               FROM cases c JOIN rules r ON regexp_matches(replace(lower(c.notes), '_', ' '), r.pattern)   -- 'unable_to_locate' = 'unable to locate'
              WHERE c.status = 'Closed' GROUP BY c.id) m USING (id)
 WHERE c.status = 'Closed';

-- For parking and encampment cases "Unable to Locate" means the car or the people had gone by the time staff arrived,
-- not that the reporter gave a bad location (37% and 24% of their closures); step 3 tests that against response time.
UPDATE outcome SET outcome = 'not_found_on_arrival', outcome_group = 'moved_on'
 WHERE outcome = 'cannot_locate' AND id IN (SELECT id FROM cases WHERE service IN ('Parking Enforcement', 'Encampment'));

CREATE OR REPLACE TABLE closed AS
SELECT c.*, o.outcome, o.outcome_group, (epoch(c.closed) - epoch(c.requested)) / 3600.0 AS hours_to_close   -- elapsed time (date_diff counts minute boundaries crossed)
  FROM cases c JOIN outcome o USING (id);
