# Data Model

## Overview

The model has three layers: **ingestion** (what came in), **normalization** (what we computed), and **review** (what analysts did). They are deliberately separate tables so the source-of-truth is always preserved and auditable.

---

## Tables

### `organizations_organization`
Multi-tenancy root. Every other record is scoped to an organization.

| Field | Type | Notes |
|-------|------|-------|
| id | BigAutoField | |
| name | varchar(255) | Human-readable client name |
| slug | slug (unique) | URL-safe identifier, used for scoping |
| created_at | timestamp | |

**Why a separate org model instead of using Django's built-in auth groups?** Groups are ACL primitives, not business entities. We'll want org-level fields (industry, reporting year, default emission factor set) that don't belong on a group.

---

### `ingestion_dataingestion`
One row per file upload event. Immutable after creation.

| Field | Type | Notes |
|-------|------|-------|
| id | BigAutoField | |
| organization | FK → Organization | |
| source_type | enum: sap, utility, travel | |
| filename | varchar(255) | Original filename for display |
| file_hash | char(64) | SHA-256 of raw file bytes — prevents duplicate uploads |
| uploaded_by | FK → User (nullable) | Nullable because we might delete users |
| uploaded_at | timestamp | |
| status | enum: processing, done, failed | |
| row_count | int | Rows successfully parsed |
| error_count | int | Rows that failed to parse |
| error_summary | text | First 20 parser errors, human-readable |

**Why store `file_hash`?** Enterprise clients re-export the same file multiple times. A hash check prevents ingesting the same data twice and producing duplicate emission records. This is cheaper than trying to detect duplicates at the row level after the fact.

**Why not store the file?** Storing raw files adds complexity (S3, signed URLs, retention policy). For a prototype, the hash is enough to establish identity. In production, we'd add a `file_url` pointing to S3.

---

### `ingestion_rawrecord`
One row per row in the uploaded file. **Never modified after creation.** This is the source-of-truth for what the client sent us.

| Field | Type | Notes |
|-------|------|-------|
| id | BigAutoField | |
| ingestion | FK → DataIngestion | |
| row_number | int | 1-indexed row in the source file |
| raw_data | JSONField | Exact key-value pairs from the source, unmodified |
| parse_status | enum: ok, error | |
| parse_error | text | Human-readable parse failure reason |

**Why keep raw rows?** When an analyst asks "why does this number look wrong?", the answer lives in the raw data. If we only stored the normalized record, we'd lose the ability to trace a value back to its source. The `raw_data` JSON contains the exact column names and values as they appeared in the file — including the German date format, the leading-zero-padded material number, the European decimal comma.

**Why JSONField and not individual columns?** Each source has a different schema. We don't know in advance what columns SAP will export — they vary by system configuration. JSONField lets us store any shape without schema migrations for every new client.

---

### `emissions_activityrecord`
The normalized, analyst-editable record. One per discrete activity event: a fuel draw-down, a billing period, a trip segment.

| Field | Type | Notes |
|-------|------|-------|
| id | BigAutoField | |
| organization | FK → Organization | Denormalized for query efficiency |
| raw_record | OneToOne FK → RawRecord (nullable) | Links back to source; null = manually entered |
| source_type | enum: sap, utility, travel | |
| scope | enum: 1, 2, 3 | GHG Protocol scope |
| category | enum | fuel_combustion, electricity, flight, hotel, car_rental, rail, procurement |
| period_start | date | **Not a single timestamp** — billing periods straddle months |
| period_end | date | |
| quantity | Decimal(18,4) | As received after source-unit normalization |
| unit | varchar(20) | liters, kWh, km, nights — the canonical form of the source unit |
| quantity_normalized | Decimal(18,4) | Canonical quantity (same as quantity in this prototype; in prod, would differ if we applied further normalization) |
| unit_canonical | varchar(20) | |
| co2e_kg | Decimal(18,4) (nullable) | Null when emission factor can't be determined (unknown airport, unknown material) |
| emission_factor | Decimal(18,6) (nullable) | kg CO2e per unit_canonical |
| emission_factor_source | varchar(255) | "DEFRA 2023", "EPA eGRID 2022", etc. |
| description | varchar(500) | Human-readable activity description |
| location_ref | varchar(255) | Plant code, meter ID, or airport pair — source-specific |
| review_status | enum: pending, flagged, approved, locked | |
| flag_reason | text | Populated by parser (auto-flags) or analyst (manual flags) |
| reviewed_by | FK → User (nullable) | |
| reviewed_at | timestamp (nullable) | |
| created_at | timestamp | |
| updated_at | timestamp | |

**Why `period_start` + `period_end` instead of a single date?**
Utility billing periods don't align with calendar months. A billing period might run January 15 – February 14. If we stored only a single date, we'd either lose the billing period boundary (making month-over-month comparison wrong) or force it into a month (introducing error). Both are unacceptable for an audited dataset.

**Why `quantity` + `unit` AND `quantity_normalized` + `unit_canonical`?**
The source unit is preserved for transparency ("the file said 1250 L"). The canonical unit enables cross-source aggregation ("how many liters total across all plants?"). In this prototype they're often equal, but they'd differ if we were doing, say, converting gallons to liters.

**Why nullable `co2e_kg`?**
We'd rather show a null and flag the record than show a wrong number. If we can't compute CO2e (unknown material, unknown airport code, car rental with no distance), we store null and mark the record flagged. The analyst can correct the input or accept the gap.

**Review status lifecycle:**
```
pending → approved (analyst sign-off)
pending → flagged  (analyst or auto-detection)
flagged → approved (after correction)
approved → locked  (audit freeze — no further changes)
approved → pending (if analyst edits a field — forces re-review)
```

Locked records cannot be modified. This models the real-world audit process where data is frozen once submitted to auditors.

---

### `emissions_auditevent`
Append-only audit log. One row per state change or field edit.

| Field | Type | Notes |
|-------|------|-------|
| id | BigAutoField | |
| activity_record | FK → ActivityRecord | |
| event_type | enum: ingested, status_change, field_edit | |
| field_name | varchar(100) | Which field changed (for field_edit) |
| from_value | text | Previous value as string |
| to_value | text | New value as string |
| actor | FK → User (nullable) | Null for system-generated events |
| timestamp | timestamp (auto) | |
| note | text | Analyst's free-text note |

**Why text instead of typed from/to values?** Typed fields would require separate columns for every editable field type (decimal, date, string). Text serialization is simpler and good enough for an audit log — the goal is human readability, not re-computation.

**Why never delete from this table?** An audit log that can be deleted isn't an audit log. Locked records need an immutable history for the auditor.

---

### `organizations_organizationmembership`
Links Django users to organizations. One user, one org in this prototype.

| Field | Type | Notes |
|-------|------|-------|
| id | BigAutoField | |
| user | OneToOne FK → User | |
| organization | FK → Organization | |
| role | varchar(50) | analyst (only role in prototype) |

---

## Key Design Decisions

### Scope assignment is done at parse time, not at query time
We assign Scope 1/2/3 when the record is created from the source data, not by looking it up from the category at query time. This means the scope is explicit in the database and auditable — an auditor can see exactly what scope we assigned and why.

### Emission factors are stored on each record, not just looked up from a table
In production, you'd have an `EmissionFactor` table with version history. For this prototype, the factor used for each record is stored directly on `ActivityRecord.emission_factor` + `emission_factor_source`. This means you can always trace "what factor did we use for this record on this date?" even if the factors are updated later.

### Multi-tenancy via FK, not row-level security
All queries are filtered by `organization = request.user.membership.organization`. This is simpler than PostgreSQL RLS and sufficient for a prototype with one organization per user. In production, you'd add RLS as a defense-in-depth layer.
