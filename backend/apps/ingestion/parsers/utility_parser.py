"""
Utility portal CSV parser (Green Button / ESPI-compatible format).

Most US commercial utility portals offer a CSV export of interval or billing data.
Green Button is the EPA/DOE standard (ESPI) adopted by major utilities including
PG&E, ConEd, ComEd, and National Grid. Facilities teams download this monthly
and send it to sustainability teams.

Why CSV over PDF: PDF bill parsing requires layout-specific regex or OCR and
breaks whenever the utility redesigns their bill template. CSV exports are stable
and machine-readable. Why not real-time API: utility OAuth requires per-utility
integration and the client would need to grant access to each account — not
realistic on day 1 of an engagement.

Real-world pain points handled:
- Billing periods that don't align with calendar months (e.g., Jan 15 – Feb 14)
- Multiple meters per facility
- MWh vs kWh normalization (some portals export in MWh)
- Estimated vs actual readings (estimated → auto-flag)
- Rate class affects cost but not emission quantity (we track it, don't use it for EF)
- Demand (kW) tracked separately from consumption (kWh)
"""

import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

# Emission factor: US national grid average
# Source: EPA eGRID 2022 (USEPA, 2023), national annual average
# 0.386 kg CO2e per kWh = 386 g CO2e/kWh
# NOTE: In production, this should use the regional subgrid factor (e.g., WECC for
# California is ~0.27, while SERC Rockies is ~0.55). We flag this in TRADEOFFS.md.
GRID_EMISSION_FACTOR = Decimal("0.386")
GRID_EF_SOURCE = "EPA eGRID 2022 — US national annual average, kg CO2e/kWh"

COLUMN_ALIASES = {
    "meter_id": "meter_id",
    "meter id": "meter_id",
    "meterID": "meter_id",
    "Meter ID": "meter_id",
    "facility_name": "facility_name",
    "facility name": "facility_name",
    "Facility": "facility_name",
    "Facility Name": "facility_name",
    "service_address": "service_address",
    "service address": "service_address",
    "Service Address": "service_address",
    "billing_period_start": "period_start",
    "billing period start": "period_start",
    "Start Date": "period_start",
    "Period Start": "period_start",
    "billing_period_end": "period_end",
    "billing period end": "period_end",
    "End Date": "period_end",
    "Period End": "period_end",
    "usage_kwh": "usage_kwh",
    "usage kwh": "usage_kwh",
    "Usage (kWh)": "usage_kwh",
    "Consumption (kWh)": "usage_kwh",
    "kWh": "usage_kwh",
    "usage_mwh": "usage_mwh",
    "Usage (MWh)": "usage_mwh",
    "MWh": "usage_mwh",
    "demand_kw": "demand_kw",
    "demand kw": "demand_kw",
    "Peak Demand (kW)": "demand_kw",
    "Demand (kW)": "demand_kw",
    "estimated": "estimated",
    "Estimated": "estimated",
    "Is Estimated": "estimated",
    "estimated_flag": "estimated",
    "rate_class": "rate_class",
    "rate class": "rate_class",
    "Rate Class": "rate_class",
    "Tariff": "rate_class",
    "amount_usd": "amount_usd",
    "amount usd": "amount_usd",
    "Amount ($)": "amount_usd",
    "Bill Amount": "amount_usd",
    "Total ($)": "amount_usd",
}


def _parse_date(value: str) -> Optional[date]:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(value: str) -> Optional[Decimal]:
    value = value.strip().replace(",", "").replace("$", "").replace(" ", "")
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in ("true", "yes", "y", "1", "x", "estimated", "est")


def _normalize_headers(headers: list) -> dict:
    mapping = {}
    for i, h in enumerate(headers):
        h_stripped = h.strip()
        canonical = COLUMN_ALIASES.get(h_stripped)
        if canonical and canonical not in mapping:
            mapping[canonical] = i
    return mapping


def parse(file_content: bytes) -> tuple[list[dict], list[str]]:
    """
    Parse utility portal CSV export.

    Returns:
        (records, errors)
    """
    records = []
    errors = []

    for encoding in ("utf-8-sig", "utf-8", "windows-1252", "latin-1"):
        try:
            text = file_content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        errors.append("Could not decode file — unsupported encoding")
        return records, errors

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        errors.append("File is empty")
        return records, errors

    # Find header row (first row with recognizable column names)
    header_row_idx = None
    for i, row in enumerate(rows[:5]):  # headers are always in first 5 rows for utility exports
        if any(COLUMN_ALIASES.get(cell.strip()) for cell in row):
            header_row_idx = i
            break

    if header_row_idx is None:
        errors.append("Could not identify column headers")
        return records, errors

    col_map = _normalize_headers(rows[header_row_idx])

    # Need at least period dates and some usage column
    has_usage = "usage_kwh" in col_map or "usage_mwh" in col_map
    if not ("period_start" in col_map and "period_end" in col_map and has_usage):
        errors.append(
            f"Missing required columns. Found: {list(col_map.keys())}. "
            "Need: period_start, period_end, and either usage_kwh or usage_mwh"
        )
        return records, errors

    for row_num, row in enumerate(rows[header_row_idx + 1:], start=header_row_idx + 2):
        if not any(cell.strip() for cell in row):
            continue

        def get(field, default=""):
            idx = col_map.get(field)
            return row[idx].strip() if idx is not None and idx < len(row) else default

        raw_data = {rows[header_row_idx][i].strip(): cell.strip()
                    for i, cell in enumerate(row) if i < len(rows[header_row_idx])}

        # --- Dates ---
        period_start = _parse_date(get("period_start"))
        period_end = _parse_date(get("period_end"))
        if period_start is None or period_end is None:
            errors.append(f"Row {row_num}: invalid dates '{get('period_start')}' / '{get('period_end')}'")
            records.append({
                "row_number": row_num, "raw_data": raw_data,
                "parse_status": "error",
                "parse_error": f"Invalid dates: '{get('period_start')}' / '{get('period_end')}'"
            })
            continue

        if period_end <= period_start:
            errors.append(f"Row {row_num}: period_end must be after period_start")
            records.append({
                "row_number": row_num, "raw_data": raw_data,
                "parse_status": "error",
                "parse_error": "period_end is not after period_start"
            })
            continue

        # --- Usage (normalize to kWh) ---
        if "usage_kwh" in col_map:
            usage_kwh = _parse_decimal(get("usage_kwh"))
            raw_unit = "kWh"
        else:
            mwh = _parse_decimal(get("usage_mwh"))
            usage_kwh = mwh * 1000 if mwh is not None else None
            raw_unit = "MWh"

        if usage_kwh is None:
            errors.append(f"Row {row_num}: could not parse usage value")
            records.append({
                "row_number": row_num, "raw_data": raw_data,
                "parse_status": "error", "parse_error": "Could not parse usage"
            })
            continue

        # --- Emission calculation ---
        co2e_kg = usage_kwh * GRID_EMISSION_FACTOR

        # --- Metadata ---
        meter_id = get("meter_id", f"meter-row{row_num}")
        facility = get("facility_name", "Unknown Facility")
        is_estimated = _is_truthy(get("estimated", "false"))

        # --- Suspicion flags ---
        flags = []
        today = date.today()
        if usage_kwh <= 0:
            flags.append("Zero or negative usage")
        if period_start > today:
            flags.append("Billing period starts in the future")
        if (period_end - period_start).days > 95:
            flags.append(f"Billing period is unusually long ({(period_end - period_start).days} days)")
        if is_estimated:
            flags.append("Meter reading is estimated, not actual")

        records.append({
            "row_number": row_num,
            "raw_data": raw_data,
            "parse_status": "ok",
            "source_type": "utility",
            "scope": 2,
            "category": "electricity",
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "quantity": str(usage_kwh),
            "unit": "kWh",
            "quantity_normalized": str(usage_kwh),
            "unit_canonical": "kWh",
            "co2e_kg": str(co2e_kg),
            "emission_factor": str(GRID_EMISSION_FACTOR),
            "emission_factor_source": GRID_EF_SOURCE,
            "description": f"Electricity — {facility} (Meter {meter_id})",
            "location_ref": meter_id,
            "flag_reason": "; ".join(flags) if flags else "",
            "review_status": "flagged" if flags else "pending",
        })

    return records, errors
