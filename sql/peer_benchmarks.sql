-- Exact continuous percentiles, not percentile_approx or percentile_disc.
-- Self-exclusion is by facility ID, so equal-valued OTHER hospitals remain peers.
WITH eligible AS (
    SELECT source_release, facility_id, state, hospital_type, measure_id,
           source_dataset_id, start_date, end_date, score_value,
           count(*) OVER (
               PARTITION BY source_release, source_dataset_id, state, hospital_type,
                            measure_id, start_date, end_date
           ) AS eligible_group_size
    FROM hospital_metrics
    WHERE comparison_eligible
), leave_one_out AS (
    SELECT t.source_release, t.source_dataset_id, t.facility_id, t.measure_id,
           t.start_date, t.end_date,
           count(p.facility_id) AS peer_count,
           max(p.eligible_group_size) AS eligible_group_size,
           percentile_cont(0.25) WITHIN GROUP (ORDER BY p.score_value) AS q1,
           percentile_cont(0.50) WITHIN GROUP (ORDER BY p.score_value) AS median_value,
           percentile_cont(0.75) WITHIN GROUP (ORDER BY p.score_value) AS q3
    FROM hospital_metrics t
    LEFT JOIN eligible p
      ON t.comparison_eligible
     AND t.source_release = p.source_release
     AND t.source_dataset_id = p.source_dataset_id
     AND t.state = p.state AND t.hospital_type = p.hospital_type
     AND t.measure_id = p.measure_id
     AND t.start_date = p.start_date AND t.end_date = p.end_date
     AND t.facility_id <> p.facility_id
    GROUP BY t.source_release, t.source_dataset_id, t.facility_id, t.measure_id,
             t.start_date, t.end_date
), evaluated AS (
    SELECT t.*, b.peer_count, b.eligible_group_size,
           CASE WHEN t.comparison_eligible AND b.peer_count >= 10 THEN 'comparable'
                WHEN NOT t.comparison_eligible THEN 'ineligible'
                ELSE 'insufficient_peers' END AS comparison_status,
           CASE WHEN t.comparison_eligible AND b.peer_count >= 10 THEN b.q1 END AS peer_q1,
           CASE WHEN t.comparison_eligible AND b.peer_count >= 10 THEN b.median_value END AS peer_median,
           CASE WHEN t.comparison_eligible AND b.peer_count >= 10 THEN b.q3 END AS peer_q3
    FROM hospital_metrics t
    INNER JOIN leave_one_out b
      ON t.source_release = b.source_release AND t.source_dataset_id = b.source_dataset_id
     AND t.facility_id = b.facility_id AND t.measure_id = b.measure_id
     AND t.start_date = b.start_date AND t.end_date = b.end_date
)
SELECT *,
       CASE WHEN comparison_status = 'comparable'
            THEN cast(score_value AS DOUBLE) - peer_median END AS gap_to_peer_median,
       CASE WHEN comparison_status = 'comparable'
            THEN CASE WHEN favorable_direction = 'lower' THEN score_value > peer_q3
                      ELSE score_value < peer_q1 END END AS unfavorable_signal,
       CASE WHEN unit = 'minutes' THEN 'minutes' ELSE 'percentage_points' END AS gap_unit
FROM evaluated
