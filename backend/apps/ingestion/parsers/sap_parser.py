"""
SAP MB51 flat-file parser.

SAP transaction MB51 (Material Document List) produces a tab-delimited export
when users choose System > List > Save > Local File > Spreadsheet (unconverted).
This is the most common way a sustainability lead hands off SAP data — they run
MB51, filter for movement types 201/261 (goods issue to cost center / production
order), and email the export.

Real-world pain points handled:
- Dates in German format DD.MM.YYYY
- UoM in German SAP codes (L, M3, KG, GAL, STK)
- Plant codes (WERKS) that are opaque without a lookup table
- Material numbers (MATNR) that need mapping to fuel type
- Movement type filtering (only consumption movements, not goods receipts)
- Quantities with European decimal comma (1.234,56 → 1234.56)
- Column headers may vary slightly by SAP system configuration
"""

import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional


# Movement types that represent actual fuel/material consumption.
# 201: Goods Issue to Cost Center (most common for fuel draw-down)
# 261: Goods Issue to Production Order
# 551: Scrapping (sometimes used for disposal)
# We exclude 101 (Goods Receipt) and 301 (transfer postings).
CONSUMPTION_MOVEMENT_TYPES = {"201", "261", "551"}

# Plant code → human-readable facility name.
# In a real deployment this would be loaded from a client-provided lookup table
# or the SAP MARC/T001W tables. We hard-code a representative set.
PLANT_LOOKUP = {
    "WERK1": "Chicago Manufacturing Plant",
    "WERK2": "Austin Distribution Warehouse",
    "WERK3": "Dallas Regional Hub",
    "1000": "Chicago Manufacturing Plant",
    "2000": "Austin Distribution Warehouse",
}

# Material number → (fuel_type, canonical_description)
# In production this comes from SAP material master (MM60).
MATERIAL_LOOKUP = {
    "MAP001": ("diesel", "Ultra-Low Sulfur Diesel"),
    "MAP002": ("natural_gas", "Natural Gas (pipeline)"),
    "MAP003": ("gasoline", "Regular Unleaded Gasoline"),
    "MAP004": ("lpg", "Liquefied Petroleum Gas"),
    "100001": ("diesel", "Ultra-Low Sulfur Diesel"),
    "100002": ("natural_gas", "Natural Gas (pipeline)"),
}

# SAP German UoM codes → (canonical_unit, conversion_to_canonical)
# Canonical unit for fuel is liters (liquid) or m³ (gas).
UOM_MAP = {
    # Liquids → liters
    "L":   ("liters", Decimal("1")),
    "LTR": ("liters", Decimal("1")),
    "GAL": ("liters", Decimal("3.78541")),      # US gallon
    "GL":  ("liters", Decimal("3.78541")),
    "GLI": ("liters", Decimal("4.54609")),      # Imperial gallon
    # Gases → m³
    "M3":  ("m3", Decimal("1")),
    "KCF": ("m3", Decimal("28.3168")),          # thousand cubic feet
    "CF":  ("m3", Decimal("0.0283168")),        # cubic feet
    # Mass → kg (for LPG/coal, less common for fuel)
    "KG":  ("kg", Decimal("1")),
    "TO":  ("kg", Decimal("1000")),             # metric tonne
    "LB":  ("kg", Decimal("0.453592")),
    # Count (should be flagged as wrong unit for fuel)
    "STK": ("units", Decimal("1")),
    "EA":  ("units", Decimal("1")),
}

# Emission factors (kg CO2e per canonical unit)
# Sources: DEFRA GHG Conversion Factors 2023, EPA Emission Factors for GHG Inventories
EMISSION_FACTORS = {
    "diesel":       ("liters", Decimal("2.68"),  "DEFRA 2023 — diesel combustion, kg CO2e/L"),
    "gasoline":     ("liters", Decimal("2.31"),  "DEFRA 2023 — petrol combustion, kg CO2e/L"),
    "natural_gas":  ("m3",     Decimal("2.04"),  "EPA 2023 — natural gas combustion, kg CO2e/m³"),
    "lpg":          ("liters", Decimal("1.56"),  "DEFRA 2023 — LPG combustion, kg CO2e/L"),
}

# Column name aliases — SAP column headers vary by system language and ALV layout
COLUMN_ALIASES = {
    # Posting date
    "BUDAT": "posting_date",
    "Buchungsdatum": "posting_date",
    "Posting Date": "posting_date",
    "posting_date": "posting_date",
    # Document date
    "BLDAT": "doc_date",
    "Belegdatum": "doc_date",
    "Document Date": "doc_date",
    # Plant
    "WERKS": "plant",
    "Werk": "plant",
    "Plant": "plant",
    # Material number
    "MATNR": "material",
    "Materialnummer": "material",
    "Material": "material",
    # Quantity
    "MENGE": "quantity",
    "Menge": "quantity",
    "Quantity": "quantity",
    # UoM
    "MEINS": "uom",
    "Mengeneinheit": "uom",
    "Unit of Entry": "uom",
    "BUn": "uom",
    # Movement type
    "BWART": "movement_type",
    "Bewegungsart": "movement_type",
    "Mvt": "movement_type",
    "Move Type": "movement_type",
    # Amount
    "DMBTR": "amount",
    "Betrag in Hauswährung": "amount",
    "Amount in LC": "amount",
    # Currency
    "WAERS": "currency",
    "Währung": "currency",
    "Currency": "currency",
    # Material description
    "MAKTX": "material_desc",
    "Bezeichnung": "material_desc",
    "Material Description": "material_desc",
}


def _parse_sap_date(value: str) -> Optional[date]:
    """Parse SAP date in DD.MM.YYYY or YYYY-MM-DD format."""
    value = value.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_quantity(value: str) -> Optional[Decimal]:
    """
    Parse SAP quantity strings. SAP may use European number format (1.234,56)
    or standard (1234.56) depending on user locale settings.
    """
    value = value.strip().replace(" ", "")
    if not value:
        return None
    # European format: period as thousands separator, comma as decimal
    if "," in value and "." in value:
        if value.index(".") < value.index(","):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".")
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _normalize_columns(headers: list) -> dict:
    """Map raw column headers to canonical field names."""
    mapping = {}
    for i, h in enumerate(headers):
        h_stripped = h.strip()
        canonical = COLUMN_ALIASES.get(h_stripped)
        if canonical:
            mapping[canonical] = i
    return mapping


def parse(file_content: bytes) -> tuple[list[dict], list[str]]:
    """
    Parse SAP MB51 flat file export.

    Returns:
        (records, errors)
        records: list of normalized dicts ready to become ActivityRecords
        errors: list of human-readable error strings
    """
    records = []
    errors = []

    # Detect encoding — SAP exports may be UTF-8 or Windows-1252
    for encoding in ("utf-8-sig", "windows-1252", "utf-8", "latin-1"):
        try:
            text = file_content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        errors.append("Could not decode file — unsupported encoding")
        return records, errors

    # SAP exports tab-delimited; some configurations use | or ;
    sniffer = csv.Sniffer()
    sample = text[:2000]
    try:
        dialect = sniffer.sniff(sample, delimiters="\t|;,")
    except csv.Error:
        dialect = csv.excel_tab

    reader = csv.reader(io.StringIO(text), dialect)
    rows = list(reader)

    if not rows:
        errors.append("File is empty")
        return records, errors

    # Skip SAP header lines (report title, blank lines, filter criteria).
    # The actual data header is the first multi-column row with recognized SAP column names.
    # We require at least 5 cells (tabs present) to distinguish the header from single-cell
    # report title lines that might incidentally contain words like "Material" or "Plant".
    header_row_idx = None
    for i, row in enumerate(rows):
        if len(row) < 5:
            continue  # single-cell report-title lines
        col_map_candidate = _normalize_columns(row)
        # At least 3 recognized columns must be present for this to be the header
        if len(col_map_candidate) >= 3:
            header_row_idx = i
            break

    if header_row_idx is None:
        errors.append("Could not find column headers — check file format")
        return records, errors

    col_map = _normalize_columns(rows[header_row_idx])
    required = {"posting_date", "plant", "material", "quantity", "uom", "movement_type"}
    missing = required - set(col_map.keys())
    if missing:
        errors.append(f"Missing required columns: {', '.join(sorted(missing))}")
        return records, errors

    for row_num, row in enumerate(rows[header_row_idx + 1:], start=header_row_idx + 2):
        if not any(cell.strip() for cell in row):
            continue  # skip blank rows (SAP often appends totals lines)

        def get(field):
            idx = col_map.get(field)
            return row[idx].strip() if idx is not None and idx < len(row) else ""

        # --- Movement type filter ---
        mvt = get("movement_type").lstrip("0")
        if mvt not in CONSUMPTION_MOVEMENT_TYPES:
            # Skip goods receipts, transfers, etc. — not fuel consumption
            continue

        # --- Date ---
        posting_date = _parse_sap_date(get("posting_date"))
        if posting_date is None:
            errors.append(f"Row {row_num}: invalid posting date '{get('posting_date')}'")
            records.append({
                "row_number": row_num,
                "raw_data": dict(zip([h.strip() for h in rows[header_row_idx]], row)),
                "parse_status": "error",
                "parse_error": f"Invalid date: '{get('posting_date')}'"
            })
            continue

        # --- Quantity ---
        raw_qty = get("quantity")
        quantity = _parse_quantity(raw_qty)
        if quantity is None:
            errors.append(f"Row {row_num}: invalid quantity '{raw_qty}'")
            records.append({
                "row_number": row_num,
                "raw_data": dict(zip([h.strip() for h in rows[header_row_idx]], row)),
                "parse_status": "error",
                "parse_error": f"Invalid quantity: '{raw_qty}'"
            })
            continue

        # --- UoM ---
        uom_raw = get("uom").upper().strip()
        uom_info = UOM_MAP.get(uom_raw)
        if uom_info is None:
            errors.append(f"Row {row_num}: unknown unit of measure '{uom_raw}'")
            records.append({
                "row_number": row_num,
                "raw_data": dict(zip([h.strip() for h in rows[header_row_idx]], row)),
                "parse_status": "error",
                "parse_error": f"Unknown UoM: '{uom_raw}'"
            })
            continue

        canonical_unit, conversion = uom_info
        quantity_normalized = quantity * conversion

        # --- Plant and material ---
        plant_code = get("plant")
        facility = PLANT_LOOKUP.get(plant_code, f"Unknown plant ({plant_code})")
        material_code = get("material").lstrip("0")  # SAP pads material numbers with leading zeros
        material_info = MATERIAL_LOOKUP.get(material_code, MATERIAL_LOOKUP.get(get("material")))
        fuel_type = material_info[0] if material_info else None
        material_desc = material_info[1] if material_info else get("material_desc") or f"Material {material_code}"

        # --- Emission factor ---
        co2e_kg = None
        ef_value = None
        ef_source = ""
        if fuel_type and fuel_type in EMISSION_FACTORS:
            ef_unit, ef, ef_src = EMISSION_FACTORS[fuel_type]
            if ef_unit == canonical_unit:
                co2e_kg = quantity_normalized * ef
                ef_value = ef
                ef_source = ef_src
            else:
                errors.append(
                    f"Row {row_num}: unit mismatch — emission factor for {fuel_type} uses {ef_unit}, "
                    f"but quantity is in {canonical_unit}; flagging for review"
                )

        # --- Suspicion flags ---
        flags = []
        from datetime import date as date_type
        today = date_type.today()
        if quantity <= 0:
            flags.append("Zero or negative quantity")
        if posting_date > today:
            flags.append(f"Posting date {posting_date} is in the future")
        if (today - posting_date).days > 730:
            flags.append(f"Posting date {posting_date} is more than 2 years ago")
        if canonical_unit == "units":
            flags.append(f"Unit '{uom_raw}' is not a fuel unit — likely wrong material")
        if fuel_type is None:
            flags.append(f"Material '{material_code}' not in fuel lookup table — co2e not computed")

        records.append({
            "row_number": row_num,
            "raw_data": dict(zip([h.strip() for h in rows[header_row_idx]], row)),
            "parse_status": "ok",
            # ActivityRecord fields
            "source_type": "sap",
            "scope": 1,
            "category": "fuel_combustion",
            "period_start": posting_date.isoformat(),
            "period_end": posting_date.isoformat(),
            "quantity": str(quantity),
            "unit": canonical_unit,
            "quantity_normalized": str(quantity_normalized),
            "unit_canonical": canonical_unit,
            "co2e_kg": str(co2e_kg) if co2e_kg is not None else None,
            "emission_factor": str(ef_value) if ef_value is not None else None,
            "emission_factor_source": ef_source,
            "description": f"{material_desc} — {mvt} movement",
            "location_ref": f"{plant_code} ({facility})",
            "flag_reason": "; ".join(flags) if flags else "",
            "review_status": "flagged" if flags else "pending",
        })

    return records, errors
