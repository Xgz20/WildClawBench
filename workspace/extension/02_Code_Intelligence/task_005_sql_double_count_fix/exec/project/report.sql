SELECT
    p.property_id,
    p.property_name,
    COUNT(l.lease_id) AS lease_count,
    COUNT(v.visit_id) AS visit_count
FROM properties AS p
LEFT JOIN leases AS l ON l.property_id = p.property_id
LEFT JOIN visits AS v ON v.property_id = p.property_id
GROUP BY p.property_id, p.property_name
ORDER BY p.property_id;
