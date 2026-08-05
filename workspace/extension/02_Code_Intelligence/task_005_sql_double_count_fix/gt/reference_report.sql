WITH lease_counts AS (
    SELECT property_id, COUNT(*) AS lease_count
    FROM leases
    GROUP BY property_id
),
visit_counts AS (
    SELECT property_id, COUNT(*) AS visit_count
    FROM visits
    GROUP BY property_id
)
SELECT
    p.property_id,
    p.property_name,
    COALESCE(l.lease_count, 0) AS lease_count,
    COALESCE(v.visit_count, 0) AS visit_count
FROM properties AS p
LEFT JOIN lease_counts AS l ON l.property_id = p.property_id
LEFT JOIN visit_counts AS v ON v.property_id = p.property_id
ORDER BY p.property_id;
