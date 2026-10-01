-- Step 4: could the intake form have warned the reporter? ({radius_m} and {days} filled in by spike.py)
-- At submission time only earlier cases are known. A new case is flagged when an earlier case of the same service and
-- subtype, within {radius_m} m and {days} days, was still open at that moment. Ground truth: cases closed as duplicates.
WITH pts AS (SELECT id, service, subtype, requested, closed, lat, lon,
                    floor(lat * 111000 / {radius_m})::BIGINT AS cy, floor(lon * 87800 / {radius_m})::BIGINT AS cx
               FROM cases WHERE lat IS NOT NULL AND subtype IS NOT NULL),
     earlier AS (SELECT p.*, p.cx + dx AS gx, p.cy + dy AS gy FROM pts p, range(-1, 2) a(dx), range(-1, 2) b(dy)),
     flagged AS (SELECT DISTINCT n.id
                   FROM closed n JOIN pts np USING (id)
                   JOIN earlier e ON e.service = n.service AND e.subtype = n.subtype AND e.gx = np.cx AND e.gy = np.cy
                  WHERE e.requested < n.requested AND e.requested >= n.requested - INTERVAL '{days} days'
                    AND (e.closed IS NULL OR e.closed > n.requested)
                    AND 2 * 6371000 * asin(sqrt(power(sin(radians(e.lat - np.lat) / 2), 2)
                        + cos(radians(np.lat)) * cos(radians(e.lat)) * power(sin(radians(e.lon - np.lon) / 2), 2))) <= {radius_m})
SELECT {radius_m} AS radius_m, {days} AS days, coalesce(c.service, 'All services') AS service,
       count(*) AS closed_with_location, count(*) FILTER (WHERE c.outcome = 'duplicate') AS closed_as_duplicate,
       count(f.id) AS flagged,
       count(f.id) FILTER (WHERE c.outcome = 'duplicate') AS flagged_and_duplicate,
       round(100.0 * count(f.id) FILTER (WHERE c.outcome = 'duplicate') / count(*) FILTER (WHERE c.outcome = 'duplicate'), 1) AS recall_pct,
       round(100.0 * count(f.id) FILTER (WHERE c.outcome = 'duplicate') / count(f.id), 1) AS flagged_closed_as_duplicate_pct,
       round(100.0 * count(f.id) / count(*), 1) AS flag_rate_pct
  FROM closed c JOIN pts USING (id) LEFT JOIN flagged f USING (id)
 GROUP BY GROUPING SETS ((), (c.service)) HAVING count(*) FILTER (WHERE c.outcome = 'duplicate') >= 1000
 ORDER BY c.service IS NOT NULL, recall_pct DESC;
