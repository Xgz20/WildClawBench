INSERT INTO properties(property_id, property_name) VALUES
    (1, 'Harbor House'),
    (2, 'Maple Court'),
    (3, 'Pine Studios'),
    (4, 'Riverside Empty');

INSERT INTO leases(lease_id, property_id, tenant_name) VALUES
    (101, 1, 'Acme'),
    (102, 1, 'Acme'),
    (103, 2, 'Beta');

INSERT INTO visits(visit_id, property_id, visited_at) VALUES
    (201, 1, '2026-08-01T09:00:00Z'),
    (202, 1, '2026-08-01T09:00:00Z'),
    (203, 1, '2026-08-02T10:00:00Z'),
    (204, 3, '2026-08-03T11:00:00Z');
