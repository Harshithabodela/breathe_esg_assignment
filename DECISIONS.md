# Decisions

Every ambiguity resolved, what I chose, why, and what I'd ask the PM.

---

## SAP: Why flat file (MB51 ALV export), not IDoc, OData, or BAPI

**What I considered:**
- **IDoc (Intermediate Document):** SAP's native message format. XML/flat-file, highly structured, supports all transaction types. Requires an SAP middleware layer (PI/PO or Integration Suite) and configuration on the client's side. No enterprise client sends IDocs to a third-party ESG tool on day 1.
- **OData service (SAP NetWeaver Gateway):** REST-ish API over HTTP. Clean, JSON/XML. Requires the client to expose their SAP system to the internet (or set up a VPN) and grant API credentials. Security review alone takes weeks. Not realistic for initial engagement.
- **BAPI (Business API):** Remote Function Call (RFC) protocol. Requires SAP RFC library, a running SAP system accessible over the network, and a technical user with specific authorizations. Even more setup than OData.
- **Flat file from MB51/ALV:** The sustainability lead logs into SAP, runs transaction MB51 (Material Document List) filtered for consumption movement types (201, 261), and saves as a spreadsheet (tab-delimited). This takes 5 minutes. They email it. This is what actually happens.

**What I chose:** MB51 flat file (tab-delimited, from ALV list export).

**Justification:** The PM said the client "has fuel and procurement data sitting in SAP." "Sitting in SAP" means we don't have a live API integration. It means a person will export a file. MB51 is the standard transaction for material document lists. The ALV list export produces a tab-delimited file with SAP field codes as column headers. This is the shape of the data we will actually receive.

**Real-world pain points I handled:**
- Date format: DD.MM.YYYY (German locale) → parsed to ISO
- UoM codes: German SAP codes (L, M3, KG, GAL) → normalized to liters/m³/kg
- Movement type filtering: only 201 (GI to cost center) and 261 (GI to production order) represent consumption. 101 (Goods Receipt) would double-count.
- Material number lookup: SAP material numbers are opaque (MAP001 = diesel). Requires a mapping table.
- Plant code lookup: WERK1 means nothing without a client-provided lookup table.
- Leading zeros on material numbers: SAP pads material numbers with leading zeros (000000MAP001). Stripped before lookup.
- European decimal format: 1.250,00 = 1250.00 in German locale.
- Report header lines: MB51 exports include report title, filter criteria, and blank lines before the actual data. Parser skips them.

**What I ignored:**
- Procurement data (purchase orders, vendor invoices). SAP ME2M/ME2L exports PO data but Scope 3 procurement emissions require spend-based or activity-based calculations with supplier emission factors — a separate, much larger problem.
- Cost center hierarchy. The BKPF/BSEG tables link to cost centers, which would let us attribute fuel to departments. Skipped for now.

**What I'd ask the PM:**
1. Does the client have a material master export they can share? Without it, we're guessing which material numbers are diesel vs natural gas.
2. Which SAP plant codes represent which physical facilities? We need the lookup table.
3. What movement types does the client use for fuel consumption? Some companies use custom movement types.
4. Is this FY data or calendar year? SAP fiscal years often don't align with calendar years.

---

## Utility: Why portal CSV, not PDF or real-time API

**What I considered:**
- **PDF bill:** Every utility has a different bill layout. PDF parsing requires layout-specific regex or OCR and breaks every time the utility redesigns their template. PG&E redesigned their commercial bill in 2022 and 2024. Brittle, high maintenance.
- **Real-time utility API (Green Button Connect):** Some utilities offer OAuth-based APIs using the ESPI (Energy Services Provider Interface) standard. Clean, automated. But requires: (1) the client to authorize access to each utility account, (2) per-utility API integration, (3) the utility to actually support the API (most US utilities don't for commercial accounts). Not day-1 realistic.
- **Portal CSV export (Green Button Download):** Every major US commercial utility portal (PG&E, ConEd, ComEd, National Grid, Eversource) offers a CSV download from the web interface. Facilities teams download this monthly. This is the realistic handoff for a new client engagement.

**What I chose:** CSV portal export, Green Button ESPI-inspired column format.

**Why Green Button format:** Green Button is the EPA/DOE standard for utility data interchange. The column names I use (`billing_period_start`, `billing_period_end`, `usage_kwh`, `meter_id`) are consistent with the ESPI schema used by Green Button Download implementations. Using a recognized standard means the format is defensible and clients in regulated industries may already produce it.

**Real-world pain points I handled:**
- Billing periods that straddle months (Jan 15 – Feb 14): stored as `period_start` + `period_end`, not a single date.
- MWh vs kWh: some portals export in MWh (e.g., ComEd for large commercial). Parser normalizes to kWh.
- Estimated readings: flagged automatically. Estimated readings should be resolved with the utility before being locked for audit.
- Multiple meters per facility: each meter is a separate row. Rollup to facility level can be done in the review UI.
- Rate class: tracked but not used for emission calculation (only affects cost, not kWh).

**Emission factor decision:** US national average from EPA eGRID 2022 (0.386 kg CO2e/kWh). This is the defensible default, but it's wrong for specific regions. A Chicago facility on the MISO grid is ~0.40; a San Francisco facility on WECC California is ~0.27. In a real deployment, we'd use the eGRID subregion factor based on the service address ZIP code.

**What I ignored:**
- Per-region emission factors (TRADEOFFS.md)
- Natural gas utility data (would require different handling — therms, not kWh)
- Renewable energy certificates (RECs): some clients use RECs to achieve "market-based" Scope 2 = 0. Not implemented.

**What I'd ask the PM:**
1. How many utility accounts does the client have? (Affects whether per-meter tracking is feasible)
2. Does the client operate in multiple states? (Affects which eGRID factor to use)
3. Does the client have any renewable supply agreements or RECs? (Affects Scope 2 methodology)

---

## Travel: Why CSV export, not Navan/Concur API

**What I considered:**
- **Navan API:** Navan has a GraphQL API and REST webhooks. Clean, real-time. But requires: (1) IT/procurement team to approve API credential generation, (2) client to grant OAuth access, (3) security review of our data handling. This takes 2-4 weeks minimum.
- **Concur API:** Similar story. Concur has a mature REST API but requires SAP Concur admin credentials and an approved OAuth app. Enterprise IT procurement approvals.
- **Concur SAE (Standard Accounting Extract):** A flat-file export that finance teams already produce for accounting. Very detailed but mixes travel and expense in a format that requires client-specific mapping.
- **Navan/Concur Trip Report CSV:** Travel managers run monthly "Trip Report" exports from the platform UI. This is what arrives in the sustainability team's inbox. The format is consistent across accounts within a platform.

**What I chose:** Monthly Trip Report CSV export (Navan-compatible format with Concur column aliases).

**Justification:** "Business travel data from a corporate travel platform" means we're receiving a report export, not building a real-time integration. The travel manager runs a report at month-end and sends it. This is the realistic shape of day-1 data.

**Real-world pain points I handled:**
- `distance_km` often blank for flights: computed great-circle distance from IATA airport codes using the haversine formula. Implemented for ~100 common airport codes (US domestic + major international). Unknown codes → auto-flagged, co2e = null.
- Cabin class affects emission factor significantly: business class is ~2x economy on short-haul, ~4x on long-haul. Used DEFRA 2023 cabin-class-specific factors.
- Haul distance matters: DEFRA 2023 uses different factors for short-haul (< 3,700 km) and long-haul flights.
- Hotel: nights sometimes explicit, sometimes derived from check-in/check-out dates.
- Car rental: distance rarely provided. Flag and leave co2e null rather than guessing.
- Airport codes: TRP-034 in sample data uses "XYZ" which doesn't exist → flagged.
- Scope: all travel = Scope 3, category 6 (Business Travel) under GHG Protocol.

**What I ignored:**
- Rail distances (provided for Amtrak routes in sample data, but international rail is harder)
- Taxi/rideshare (no distance or category available from travel platforms)
- Personal vehicle mileage reimbursements (different data source entirely — expense reports)

**What I'd ask the PM:**
1. Does the client use Navan, Concur, or something else? (Column names vary)
2. Do they track cabin class? (Critical for accurate flight emissions — without it, we default to economy)
3. Are international trips included? (Airport code coverage is the main gap)
4. Is this only employee travel, or also contractor/consultant travel?

---

## Review workflow: Why session auth, not JWT

JWT requires the frontend to store a token (localStorage = XSS risk, cookie = same as session). Django session auth with CSRF protection is well-understood, simpler, and appropriate for a web app where we control both frontend and backend. JWT would add value for a mobile app or third-party API consumers — not needed here.

## Review workflow: Why no separate "submit for audit" step

The lock action on individual records serves this purpose. In a real deployment, you'd want a "submit period" action that locks all approved records for a reporting period at once. Deliberately skipped (see TRADEOFFS.md).

## Emission factors: Why hardcoded, not a database table

For a prototype, hardcoded constants with named sources are clearer and easier to audit than a database table with no UI. Every factor in the code has its source cited (DEFRA 2023, EPA eGRID 2022) and is defensible. A database table adds complexity without adding auditability if there's no UI for managing factors.
