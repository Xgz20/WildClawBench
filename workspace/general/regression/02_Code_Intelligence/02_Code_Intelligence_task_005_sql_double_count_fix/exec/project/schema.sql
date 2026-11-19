CREATE TABLE properties (
    property_id INTEGER PRIMARY KEY,
    property_name TEXT NOT NULL
);

CREATE TABLE leases (
    lease_id INTEGER PRIMARY KEY,
    property_id INTEGER NOT NULL REFERENCES properties(property_id),
    tenant_name TEXT NOT NULL
);

CREATE TABLE visits (
    visit_id INTEGER PRIMARY KEY,
    property_id INTEGER NOT NULL REFERENCES properties(property_id),
    visited_at TEXT NOT NULL
);
