# Tradeoffs

Three things I deliberately did not build, and why.

---

## 1. Per-region electricity emission factors

**What I built instead:** US national average from EPA eGRID 2022 — 0.386 kg CO2e/kWh, applied uniformly to all utility records.

**What I didn't build:** Region-specific emission factors based on the eGRID subregion for each facility's service address.

**Why it matters:** The eGRID national average is wrong for every specific facility. A Chicago facility on the MISO Midwest subregion (MROE) is 0.409 kg/kWh. A San Francisco facility on WECC California (CAMX) is 0.271 kg/kWh. A Dallas facility on Texas RE (ERCT) is 0.422 kg/kWh. Using the national average understates emissions for coal-heavy grids and overstates them for renewable-heavy grids. For a client with facilities in multiple states, the aggregate error can be significant.

**Why I skipped it:** Implementing this correctly requires: (1) a lookup table mapping ZIP codes to eGRID subregions (published by EPA but requires parsing), (2) a table of per-subregion annual factors, (3) logic to handle the billing period spanning two years (factors change annually), and (4) a decision about how to handle the 2022 vs 2023 factor versions (EPA publishes with a ~2-year lag). This is 2-3 days of work by itself. It's also a data quality problem: if the service address in the utility export is wrong or abbreviated, the lookup fails.

**What I'd do in production:** Load the EPA eGRID subregion mapping table. Add a `eGRID_subregion` field to `ActivityRecord`. Populate it from the service address on upload. Fall back to national average with a flag if the ZIP code isn't recognized.

---

## 2. Real-time SAP OData integration

**What I built instead:** File upload of MB51 flat-file exports.

**What I didn't build:** A live integration against SAP's OData services to pull material documents on demand.

**Why it matters:** The file upload workflow is manual and creates data latency. If a facility's fuel usage spikes mid-month, the sustainability team won't see it until someone runs MB51 and uploads the export. A real-time OData pull could catch anomalies faster. It would also eliminate the risk of someone uploading an outdated or filtered export by mistake.

**Why I skipped it:** Live OData requires: (1) the client to expose SAP to the internet or grant VPN access, (2) SAP NetWeaver Gateway configuration (a specialized SAP BASIS admin task), (3) OAuth or basic auth credential management, (4) handling SAP's OData pagination (top/skip), (5) dealing with SAP's various OData service versions (2.0, 4.0) and their different quirks. Most importantly, it requires a security review and procurement approval from the client's IT team. On day 1 of an engagement, none of this is available. The flat-file workflow is operational immediately.

**What I'd do in production:** Build the OData pull as a Phase 2 feature. Design the `DataIngestion` model to support both pull and push origins (add an `ingestion_method` field: file_upload | api_pull | api_push). The parser logic stays the same; only the ingestion trigger changes.

---

## 3. Batch period submission and audit lock

**What I built instead:** Per-record lock action via `POST /api/activity-records/{id}/lock/`.

**What I didn't build:** A reporting period model with a "submit period for audit" action that atomically locks all approved records for a given period.

**Why it matters:** In real ESG reporting, you don't lock individual records one by one. You define a reporting period (e.g., FY2024: Jan 1 – Dec 31), approve all records in that period, and then submit the period to the auditor. The lock is on the period, not the record. This means: (1) you can't accidentally lock some records but not others, (2) the auditor sees a clean period boundary, (3) re-opening a period for amendment is a deliberate, documented action.

**Why I skipped it:** Implementing a proper period model requires: (1) a `ReportingPeriod` table with start/end dates and a status (open, submitted, auditing, final), (2) logic to prevent records from spanning two periods (utility billing periods that cross Jan 1), (3) a period-level audit trail, (4) a UI for defining and submitting periods. This adds significant complexity to both the data model and the UX. For a prototype demonstrating ingestion and review, per-record locking is sufficient to show the concept.

**What I'd do in production:** Add a `ReportingPeriod` model with: `organization`, `name` (e.g., "FY2024"), `period_start`, `period_end`, `status` (open, submitted, auditing, final), `submitted_by`, `submitted_at`. Add a FK from `ActivityRecord` to `ReportingPeriod`. The submit action would check that all records in the period are approved, then atomically set the period status to `submitted` and lock all its records.
