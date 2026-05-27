# Sources

For each of the three sources: what real-world format I researched, what I learned, what my sample data looks like and why, and what would break in a real deployment.

---

## 1. SAP — Fuel and Procurement Data

### What real-world format I researched

SAP stores material movements in the MSEG table (Material Document Segment), linked to MKPF (Material Document Header). The standard SAP transaction for reporting material movements is **MB51** (Material Document List). Users access it via the SAP GUI or Fiori launchpad.

SAP exports can take several forms:
- **IDoc (Intermediate Document):** SAP's native EDI format. Comes in flat-file (ASCII) or XML. Highly structured with segment and qualifier codes. Used for system-to-system integration.
- **BAPI/RFC:** Remote Function Call. `BAPI_GOODSMVT_GETITEMS` returns goods movements. Requires SAP RFC connectivity.
- **OData:** Via SAP NetWeaver Gateway. `API_MATERIAL_DOCUMENT_SRV` is the standard SAP API for material documents.
- **ALV list export (flat file):** When a user runs MB51 and selects System → List → Save → Local File → Spreadsheet (unconverted), SAP exports a tab-delimited file with the column headers from the ALV (Advanced List Viewer) report. This is what a sustainability lead actually emails.

I chose the ALV flat file because it's the zero-infrastructure option. The other methods require SAP system access.

### What I learned

1. **German date format by default.** SAP's date format follows the user's locale. German-language SAP instances use `DD.MM.YYYY`. Even English-language instances may export dates in this format depending on the user's profile settings. I've seen both in real exports.

2. **UoM codes are SAP internal codes, not ISO.** `L` = Liter, `M3` = Cubic Meter, `KG` = Kilogram, `STK` = Piece (Stück), `GAL` = US Gallon. These are SAP's internal codes from table T006. They overlap with ISO but aren't identical.

3. **Material numbers are padded with leading zeros.** SAP stores MATNR as an 18-character field, left-padded with zeros. `000000MAP001` means `MAP001`. The number of zeros varies by material number length.

4. **Movement type is critical for interpretation.** The same material can appear in MB51 for a goods receipt (101), a goods issue (201/261), a transfer posting (301), or a reversal (102, 202). Only consumption movements (201, 261) represent actual fuel usage for Scope 1. Failing to filter on movement type would double-count by including both the goods receipt and the goods issue.

5. **European decimal format.** In German SAP locales, quantities use period as thousands separator and comma as decimal point: `1.250,00` = 1250.

6. **Plant codes are client-specific.** WERK1, WERK2, etc. are defined by the client's SAP configuration. Without a lookup table from the client, they're opaque.

### What my sample data looks like and why

`sample_data/sap_mb51_export.txt` contains 57 rows:
- 4 report header lines (title, filter criteria) — realistic
- 1 blank line separator — realistic
- 1 column header row with SAP field names (BLDAT, BUDAT, WERKS, etc.) — realistic
- 46 valid consumption records (movement types 201/261)
- 1 GR record (movement type 101) — filtered out by parser
- 3 intentionally problematic rows:
  - Future date (15.06.2026) — auto-flagged
  - Zero quantity — auto-flagged
  - Wrong UoM (STK = piece, not a fuel unit) — auto-flagged

Two plants (WERK1=Chicago, WERK2=Austin, WERK3=Dallas), two main fuel types (MAP001=Diesel, MAP002=Natural Gas), with some gasoline (MAP003) and LPG (MAP004). Date range January–February 2025. Quantities use European decimal format.

### What would break in a real deployment

1. **Unknown material numbers.** Any material not in our lookup table returns `fuel_type=None` and `co2e=null`. Real deployments need a dynamic lookup table loaded from the client's SAP material master (MM60 export).

2. **Custom movement types.** Some companies define custom movement types (600s, 700s range). Our filter for 201/261 would miss these.

3. **Multiple SAP system languages.** A multinational client might have SAP instances in German, Spanish, and Japanese. Column headers would differ across exports.

4. **Fiscal year alignment.** SAP fiscal years don't always align with calendar years. A client with fiscal year April–March would have FY2025 spanning two calendar years.

5. **Large files.** MB51 exports for a large plant over a full year can be 100,000+ rows. Our synchronous parser would need to become asynchronous with a Celery task.

6. **European decimal in amounts vs quantities.** Amount fields (DMBTR) use the same European decimal format but we don't currently parse them — only quantities. If we need to cross-reference cost data, this would need to be added.

---

## 2. Utility — Electricity Data

### What real-world format I researched

US commercial utility billing data is accessible via:

1. **PDF bills:** Paper or email bills as PDFs. Unstructured, layout-specific. PG&E, ConEd, and most utilities have 3-5 page commercial bills with usage summaries. Not parseable without OCR + layout-specific extraction logic.

2. **Portal CSV export (Green Button Download):** Most major US utilities have web portals where commercial customers can download their usage data as CSV. The **Green Button** standard (developed by the Department of Energy and NIST, based on the ESPI standard ANSI/CTA-2045) defines a standard XML format (`espi.xml`) for interval and billing data. Most utilities also offer a simplified CSV download.

3. **Green Button Connect (API):** An OAuth-based API extension of Green Button. The utility acts as an authorization server; the third party (us) requests access to the customer's data. The customer approves via the utility portal. Implemented by: PG&E (Share My Data), ComEd, SDG&E, Con Edison (Share My Data). Not implemented by many smaller utilities and not common for large commercial/industrial accounts.

4. **Utility-specific APIs:** Some large utilities (National Grid, Duke Energy) offer proprietary APIs for commercial customers with high-volume data. Require utility account manager approval and a data sharing agreement.

I chose the portal CSV because it requires no API credentials and is universally available across US utilities. The column names I use follow the Green Button Download CSV convention.

### What I learned

1. **Billing periods are utility-defined, not calendar months.** A commercial meter is typically read on a specific day each month determined by the utility's meter reading schedule. This means billing periods like December 18 – January 17 are normal.

2. **Estimated readings are common.** If a meter reader can't access the meter (building locked, weather), the utility estimates the reading based on historical usage. These are flagged as "estimated" in the export. Estimated readings should be resolved before being locked for audit.

3. **Multiple meters per facility.** A large facility might have separate meters for: office HVAC, manufacturing equipment, outdoor lighting, EV charging. Each meter is a separate row in the export, with its own billing schedule.

4. **Rate class matters for cost but not for emissions.** Commercial customers have different rate classes (time-of-use, demand, flat rate). The rate class affects the dollar amount of the bill but not the kWh consumption. For emission calculations, we care about kWh, not cost.

5. **Demand charges.** Commercial bills often separate energy charges (per kWh) from demand charges (per kW peak). We track `demand_kw` but don't use it for emission calculations — it's informational.

6. **MWh vs kWh.** Large commercial customers may receive bills in MWh. The parser handles both and normalizes to kWh.

### What my sample data looks like and why

`sample_data/utility_portal_export.csv` contains 18 rows: 3 meters across 3 facilities (Chicago, Austin, Dallas), 6 billing periods each, spanning approximately January–July 2025. Billing periods are intentionally non-calendar (e.g., UTL-001 starts Dec 18). Two rows are marked `estimated=true` (UTL-001 Feb-Mar, UTL-002 May-Jun).

Rate classes are real ComEd and Austin Energy tariff names (C-GS-TOU-5, GS-1, LGS-TOU).

### What would break in a real deployment

1. **Per-region emission factors.** See TRADEOFFS.md. Using the national average introduces significant error for California facilities.

2. **Utility-specific column names.** Our parser handles common column aliases, but a new utility portal might use column names we haven't seen. A mapping UI for analysts to define column mappings would be needed.

3. **Therms and MMBTU.** Natural gas utility data uses therms or MMBTU, not kWh. Some utilities bundle gas and electric on the same bill. We'd need a separate parser for gas utility data.

4. **Multi-year billing periods.** Some utilities bill annually for certain commercial customers. Our parser flags billing periods > 95 days, but doesn't reject them.

5. **Currency and international utilities.** This parser assumes USD. International utility data would need currency conversion.

---

## 3. Corporate Travel — Flights, Hotels, Ground Transport

### What real-world format I researched

Corporate travel data comes from:

1. **Navan (formerly TripActions):** GraphQL API with REST webhooks. Trip Report export via the Insights dashboard (CSV/XLSX). I reviewed the Navan API documentation and the exported trip report column names.

2. **Concur Travel & Expense:** REST API (`/api/v3.0/expense/reports`). Standard Accounting Extract (SAE) format for financial exports. "Trip Report" export from the Concur Travel UI (CSV). Concur's column names differ from Navan's — I've included both in the column alias table.

3. **Direct airline booking data (GDS feeds):** Global Distribution System data from Amadeus, Sabre, or Travelport. Highly detailed (booking class, actual routing vs. direct routing). Not accessible without GDS credentials.

I chose the monthly Trip Report CSV because it's what travel managers actually send. The API exists, but credential access requires IT procurement approval.

### What I learned

1. **Distance is rarely given for flights.** Travel platforms record the booking: origin airport, destination airport, amount paid. They don't compute or store great-circle distance. You have to derive it from the airport codes.

2. **Airport codes can be city codes, not airport codes.** "NYC" is a city code (not an airport) in GDS systems. The three New York airports are JFK, LGA, and EWR. Some platforms use city codes in their exports, not IATA airport codes.

3. **Cabin class is inconsistently recorded.** Some platforms record "Economy", others "Y" (GDS booking class code for full-fare economy), others "Coach". Mapping these requires handling many variants.

4. **Hotel "destination" is a city or hotel name, not an airport code.** Hotels are booked by city and property, not by geography. Hotel emission calculation uses a per-room-night factor, not distance.

5. **Car rental distance is almost never in the export.** Car rental bookings record the pickup location, vendor, and cost. Distance is only available if the client separately tracks mileage (expense reports). We flag and leave co2e null.

6. **Multi-leg trips appear as separate rows.** A business trip from Boston to London with a stopover in New York would appear as three rows: BOS→JFK, JFK→LHR, and the return. Our parser handles each leg independently, which is correct — each leg has its own departure airport and thus its own distance.

### What my sample data looks like and why

`sample_data/navan_trip_report.csv` contains 35 rows from 7 travelers across January–February 2025:
- **Air travel:** 24 rows including short-haul domestic (BOS-ORD, JFK-MIA), medium-haul (ORD-CDG, LAX-GRU), and long-haul international (ORD-LHR, LAX-DXB, SFO-NRT). Mix of economy and business class.
- **Hotels:** 8 rows with explicit night counts or check-in/check-out dates.
- **Car rental:** 2 rows — one with distance (580 km), one without.
- **Rail:** 2 rows with distance (Amtrak, 457 km each way).
- **Intentional edge cases:**
  - TRP-029: Car rental with no distance → flagged, co2e null
  - TRP-034: Unknown airport code "XYZ" → flagged, co2e null

Emission factors used: DEFRA 2023 Scope 3 conversion factors for business travel, cabin-class and haul-distance specific.

### What would break in a real deployment

1. **Airport code gaps.** Our lookup table covers ~100 airports. A client with unusual routes (e.g., Nairobi NBO to Lusaka LUN, or domestic India routes) would produce null co2e for those flights. We'd need to load the full OurAirports database (~10,000 airports).

2. **City codes vs airport codes.** If Navan exports "NYC" instead of "JFK/LGA/EWR", our airport lookup fails. We'd need a city-code-to-airport mapping.

3. **Radiative forcing.** DEFRA 2023 includes radiative forcing in flight emission factors (the non-CO2 warming effects of contrails and high-altitude emissions). Some clients prefer factors without radiative forcing (e.g., if they're reporting to CDP which allows both). We hardcoded the DEFRA with-RF factors. This is defensible but should be configurable.

4. **Mixed personal and business travel.** Corporate cards sometimes capture personal bookings. We have no way to filter these without booking purpose data from the expense system.

5. **Currency normalization.** International trips may be billed in local currency. Navan normalizes to USD in their export, but Concur may not.
