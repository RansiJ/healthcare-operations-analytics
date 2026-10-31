-- One row per hospital/measure/period in the approved cohort; never pivot periods together.
WITH cohort AS (
    SELECT * FROM dim_hospital WHERE in_cohort
), integrated AS (
    SELECT f.*, h.facility_name, h.state, h.hospital_type, h.hospital_ownership,
           h.emergency_services,
           NOT (trim(f.measure_facility_name_raw) <=> h.facility_name) AS source_name_mismatch,
           NOT (upper(trim(f.measure_state_raw)) <=> h.state) AS source_state_mismatch
    FROM fact_hospital_measure f
    INNER JOIN cohort h
      ON f.source_release = h.source_release AND f.facility_id = h.facility_id
)
SELECT * FROM integrated

