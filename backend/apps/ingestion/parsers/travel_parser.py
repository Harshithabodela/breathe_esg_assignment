"""
Corporate travel CSV parser (Navan / Concur Trip Report format).

Navan (formerly TripActions) and Concur both offer "Trip Report" or
"Travel & Expense Report" exports to CSV/XLSX. Travel managers run these
monthly and send to the sustainability team. This is the realistic day-1
handoff — before any API integration is built.

Concur also has a "Standard Accounting Extract" (SAE) format, but that
mixes travel and expense in ways that require more client-specific mapping.
We handle the simpler trip report format.

Real-world pain points handled:
- distance_km is often blank for air travel (only booking cost is recorded)
  → compute great-circle distance from IATA airport codes
- Hotel category: destination is a city/hotel name, not airport code
  → quantity is nights (derived from check-in/check-out, or explicit)
- Car rental: distance rarely given → flag, use amount as proxy if needed
- Multiple currencies → we record amount_usd (Navan normalizes to USD)
- Cabin class affects emission factor (economy vs business vs first)
"""

import csv
import io
import math
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

# -------------------------------------------------------------------
# IATA airport code → (latitude, longitude)
# Covers the most common routes in a US-HQ'd enterprise travel program.
# Source: OurAirports database (public domain, ourairports.com)
# Unknown codes → flagged, co2e not computed.
# -------------------------------------------------------------------
AIRPORT_COORDS = {
    # North America
    "JFK": (40.6398, -73.7789),  "LGA": (40.7772, -73.8726),  "EWR": (40.6925, -74.1687),
    "BOS": (42.3643, -71.0052),  "ORD": (41.9742, -87.9073),  "MDW": (41.7868, -87.7522),
    "LAX": (33.9425, -118.4081), "SFO": (37.6213, -122.379),  "SJC": (37.3626, -121.929),
    "SEA": (47.4502, -122.3088), "DEN": (39.8561, -104.6737), "DFW": (32.8998, -97.0403),
    "IAH": (29.9844, -95.3414),  "ATL": (33.6407, -84.4277),  "MIA": (25.7959, -80.287),
    "MCO": (28.4294, -81.309),   "PHX": (33.4373, -112.0078), "LAS": (36.0840, -115.1537),
    "MSP": (44.8848, -93.2223),  "DTW": (42.2162, -83.3554),  "PHL": (39.8719, -75.2411),
    "CLT": (35.2140, -80.9431),  "DCA": (38.8521, -77.0377),  "IAD": (38.9531, -77.4565),
    "BWI": (39.1754, -76.6683),  "SLC": (40.7884, -111.9778), "PDX": (45.5898, -122.5951),
    "AUS": (30.1975, -97.6664),  "BNA": (36.1245, -86.6782),  "MCI": (39.2976, -94.7139),
    "STL": (38.7487, -90.3700),  "RDU": (35.8776, -78.7875),  "PIT": (40.4915, -80.2329),
    "IND": (39.7173, -86.2944),  "CMH": (39.9980, -82.8919),
    # International — Europe
    "LHR": (51.4775, -0.4614),   "LGW": (51.1537, -0.1821),   "STN": (51.8850, 0.2350),
    "CDG": (49.0097, 2.5479),    "ORY": (48.7233, 2.3794),    "AMS": (52.3086, 4.7639),
    "FRA": (50.0379, 8.5622),    "MUC": (48.3537, 11.7750),   "ZRH": (47.4647, 8.5492),
    "VIE": (48.1103, 16.5697),   "BRU": (50.9014, 4.4844),    "MAD": (40.4936, -3.5668),
    "BCN": (41.2971, 2.0785),    "FCO": (41.8003, 12.2389),   "MXP": (45.6306, 8.7281),
    "CPH": (55.6180, 12.6560),   "ARN": (59.6498, 17.9238),   "OSL": (60.1939, 11.1004),
    "HEL": (60.3172, 24.9633),   "DUB": (53.4213, -6.2701),   "LIS": (38.7756, -9.1354),
    "WAW": (52.1657, 20.9671),   "PRG": (50.1008, 14.2600),   "BUD": (47.4298, 19.2611),
    # International — Asia Pacific
    "NRT": (35.7647, 140.3864),  "HND": (35.5494, 139.7798),  "ICN": (37.4602, 126.4407),
    "PEK": (40.0799, 116.6031),  "PVG": (31.1434, 121.8052),  "HKG": (22.3080, 113.9185),
    "SIN": (1.3644, 103.9915),   "BKK": (13.6811, 100.7472),  "KUL": (2.7456, 101.7099),
    "DEL": (28.5562, 77.1000),   "BOM": (19.0896, 72.8656),   "SYD": (-33.9399, 151.1753),
    "MEL": (-37.6690, 144.8410), "AKL": (-37.0082, 174.7917),
    # Canada
    "YYZ": (43.6772, -79.6306),  "YVR": (49.1947, -123.1792), "YUL": (45.4706, -73.7408),
    "YYC": (51.1315, -114.0106), "YEG": (53.3097, -113.5792),
    # Middle East & Africa
    "DXB": (25.2532, 55.3657),   "DOH": (25.2731, 51.6080),   "AUH": (24.4330, 54.6511),
    "JNB": (-26.1392, 28.2460),  "NBO": (-1.3192, 36.9275),   "CAI": (30.1219, 31.4056),
    # Latin America
    "GRU": (-23.4356, -46.4731), "BOG": (4.7016, -74.1469),   "SCL": (-33.3930, -70.7858),
    "LIM": (-12.0219, -77.1143), "MEX": (19.4363, -99.0721),  "CUN": (21.0365, -86.8771),
}

# -------------------------------------------------------------------
# Emission factors (kg CO2e per pkm or per night)
# Source: DEFRA Greenhouse Gas Conversion Factors for Company Reporting 2023
# -------------------------------------------------------------------
# Flights: haul-based factors (economy class, including radiative forcing)
FLIGHT_EF = {
    "economy": {
        "short":  Decimal("0.255"),  # < 3,700 km (domestic/regional)
        "long":   Decimal("0.195"),  # >= 3,700 km (international)
    },
    "business": {
        "short":  Decimal("0.510"),  # ~2x economy
        "long":   Decimal("0.429"),
    },
    "first": {
        "short":  Decimal("0.510"),
        "long":   Decimal("0.780"),  # ~4x economy long-haul
    },
    "unknown": {
        "short":  Decimal("0.255"),
        "long":   Decimal("0.195"),
    },
}
FLIGHT_EF_SOURCE = "DEFRA 2023 — passenger km, kg CO2e/pkm (incl. radiative forcing)"

# Hotels: per room-night
HOTEL_EF = Decimal("31.1")
HOTEL_EF_SOURCE = "DEFRA 2023 — hotel stay, kg CO2e/room night"

# Car rental: average petrol/gasoline car
CAR_EF = Decimal("0.192")
CAR_EF_SOURCE = "DEFRA 2023 — average car, kg CO2e/km"

# Rail: UK average (used as proxy for international; US Amtrak ~0.037, Eurostar ~0.006)
RAIL_EF = Decimal("0.041")
RAIL_EF_SOURCE = "DEFRA 2023 — national rail average, kg CO2e/km"

COLUMN_ALIASES = {
    "trip_id": "trip_id", "Trip ID": "trip_id", "tripID": "trip_id",
    "booking_date": "booking_date", "Booking Date": "booking_date",
    "travel_date": "travel_date", "Travel Date": "travel_date",
    "departure_date": "travel_date", "Departure Date": "travel_date",
    "check_in_date": "travel_date", "Check-In Date": "travel_date",
    "return_date": "return_date", "Return Date": "return_date",
    "check_out_date": "return_date", "Check-Out Date": "return_date",
    "traveler_email": "traveler_email", "Traveler Email": "traveler_email",
    "employee_email": "traveler_email", "Employee Email": "traveler_email",
    "category": "category", "Category": "category", "Type": "category",
    "Travel Type": "category",
    "origin": "origin", "Origin": "origin", "From": "origin",
    "Departure": "origin",
    "destination": "destination", "Destination": "destination", "To": "destination",
    "cabin_class": "cabin_class", "Cabin Class": "cabin_class", "Class": "cabin_class",
    "Service Class": "cabin_class",
    "amount_usd": "amount_usd", "Amount (USD)": "amount_usd", "Cost (USD)": "amount_usd",
    "Amount": "amount_usd",
    "currency": "currency", "Currency": "currency",
    "vendor": "vendor", "Vendor": "vendor", "Airline": "vendor", "Hotel": "vendor",
    "distance_km": "distance_km", "Distance (km)": "distance_km", "Distance": "distance_km",
    "nights": "nights", "Nights": "nights", "Number of Nights": "nights",
}

CATEGORY_MAP = {
    "air": "flight", "flight": "flight", "airline": "flight",
    "hotel": "hotel", "lodging": "hotel", "accommodation": "hotel",
    "car": "car_rental", "car rental": "car_rental", "rental car": "car_rental",
    "rail": "rail", "train": "rail", "amtrak": "rail",
    "ground": "car_rental",  # ground transport defaults to car
}


def _haversine_km(lat1, lon1, lat2, lon2) -> Decimal:
    """Great-circle distance between two points on Earth, in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return Decimal(str(round(2 * R * math.asin(math.sqrt(a)), 1)))


def _flight_distance(origin: str, destination: str) -> tuple[Optional[Decimal], str]:
    """
    Compute one-way great-circle distance from IATA codes.
    Returns (distance_km, status_note).
    """
    o = origin.strip().upper()
    d = destination.strip().upper()
    if o not in AIRPORT_COORDS:
        return None, f"Unknown origin airport code '{o}'"
    if d not in AIRPORT_COORDS:
        return None, f"Unknown destination airport code '{d}'"
    lat1, lon1 = AIRPORT_COORDS[o]
    lat2, lon2 = AIRPORT_COORDS[d]
    return _haversine_km(lat1, lon1, lat2, lon2), ""


def _parse_date(value: str) -> Optional[date]:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(value: str) -> Optional[Decimal]:
    v = value.strip().replace(",", "").replace("$", "").replace(" ", "")
    if not v:
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        return None


def _normalize_headers(headers: list) -> dict:
    mapping = {}
    for i, h in enumerate(headers):
        canonical = COLUMN_ALIASES.get(h.strip())
        if canonical and canonical not in mapping:
            mapping[canonical] = i
    return mapping


def parse(file_content: bytes) -> tuple[list[dict], list[str]]:
    records = []
    errors = []

    for encoding in ("utf-8-sig", "utf-8", "windows-1252", "latin-1"):
        try:
            text = file_content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        errors.append("Could not decode file")
        return records, errors

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        errors.append("File is empty")
        return records, errors

    header_row_idx = None
    for i, row in enumerate(rows[:5]):
        if any(COLUMN_ALIASES.get(cell.strip()) for cell in row):
            header_row_idx = i
            break
    if header_row_idx is None:
        errors.append("Could not identify column headers")
        return records, errors

    col_map = _normalize_headers(rows[header_row_idx])
    required = {"category", "travel_date"}
    missing = required - set(col_map.keys())
    if missing:
        errors.append(f"Missing required columns: {', '.join(sorted(missing))}")
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
        travel_date = _parse_date(get("travel_date"))
        if travel_date is None:
            errors.append(f"Row {row_num}: invalid travel date '{get('travel_date')}'")
            records.append({"row_number": row_num, "raw_data": raw_data,
                            "parse_status": "error", "parse_error": "Invalid travel date"})
            continue

        return_date = _parse_date(get("return_date")) if get("return_date") else None
        period_end = return_date or travel_date

        # --- Category ---
        raw_category = get("category", "").lower().strip()
        category = CATEGORY_MAP.get(raw_category)
        if category is None:
            # Try partial match
            for key, val in CATEGORY_MAP.items():
                if key in raw_category:
                    category = val
                    break
        if category is None:
            errors.append(f"Row {row_num}: unknown travel category '{get('category')}'")
            records.append({"row_number": row_num, "raw_data": raw_data,
                            "parse_status": "error",
                            "parse_error": f"Unknown category: '{get('category')}'"})
            continue

        origin = get("origin")
        destination = get("destination")
        flags = []

        # --- Category-specific calculation ---
        if category == "flight":
            cabin_raw = get("cabin_class", "unknown").lower()
            if "business" in cabin_raw:
                cabin = "business"
            elif "first" in cabin_raw:
                cabin = "first"
            elif "economy" in cabin_raw or "eco" in cabin_raw:
                cabin = "economy"
            else:
                cabin = "unknown"

            # Try explicit distance first, then compute from airport codes
            explicit_dist = _parse_decimal(get("distance_km"))
            if explicit_dist is not None:
                distance_km = explicit_dist
                dist_note = ""
            else:
                distance_km, dist_note = _flight_distance(origin, destination)

            if distance_km is None:
                flags.append(f"Could not compute distance: {dist_note}")
                co2e_kg = None
                ef_value = None
                ef_source = ""
            else:
                haul = "long" if distance_km >= 3700 else "short"
                ef_value = FLIGHT_EF[cabin][haul]
                co2e_kg = distance_km * ef_value
                ef_source = FLIGHT_EF_SOURCE

            quantity = distance_km
            unit = "km"
            quantity_normalized = distance_km
            description = (f"Flight {origin}→{destination} ({cabin})"
                           if origin and destination else f"Flight ({cabin})")
            location_ref = f"{origin}-{destination}" if origin and destination else ""

        elif category == "hotel":
            nights_raw = get("nights")
            if nights_raw:
                nights = _parse_decimal(nights_raw)
            elif return_date and travel_date:
                nights = Decimal(str((return_date - travel_date).days))
            else:
                nights = Decimal("1")
                flags.append("Number of nights not specified; defaulted to 1")

            co2e_kg = nights * HOTEL_EF if nights else None
            ef_value = HOTEL_EF
            ef_source = HOTEL_EF_SOURCE
            quantity = nights
            unit = "nights"
            quantity_normalized = nights
            description = f"Hotel stay — {destination or 'unknown'}"
            location_ref = destination or ""

        elif category == "car_rental":
            dist = _parse_decimal(get("distance_km"))
            if dist is not None:
                co2e_kg = dist * CAR_EF
                ef_value = CAR_EF
                ef_source = CAR_EF_SOURCE
                quantity = dist
            else:
                flags.append("Car rental distance not provided — co2e not computed")
                co2e_kg = None
                ef_value = None
                ef_source = ""
                quantity = None
            unit = "km"
            quantity_normalized = quantity
            description = f"Car rental — {destination or get('vendor', 'unknown')}"
            location_ref = destination or ""

        elif category == "rail":
            dist = _parse_decimal(get("distance_km"))
            if dist is not None:
                co2e_kg = dist * RAIL_EF
                ef_value = RAIL_EF
                ef_source = RAIL_EF_SOURCE
                quantity = dist
                quantity_normalized = dist
            else:
                flags.append("Rail distance not provided — co2e not computed")
                co2e_kg = None
                ef_value = None
                ef_source = ""
                quantity = None
                quantity_normalized = None
            unit = "km"
            description = f"Rail — {origin}→{destination}" if origin and destination else "Rail"
            location_ref = f"{origin}-{destination}" if origin and destination else ""

        else:
            continue  # unreachable

        # --- Common flags ---
        today = date.today()
        if travel_date > today:
            flags.append(f"Travel date {travel_date} is in the future")

        records.append({
            "row_number": row_num,
            "raw_data": raw_data,
            "parse_status": "ok",
            "source_type": "travel",
            "scope": 3,
            "category": category,
            "period_start": travel_date.isoformat(),
            "period_end": period_end.isoformat(),
            "quantity": str(quantity) if quantity is not None else None,
            "unit": unit,
            "quantity_normalized": str(quantity_normalized) if quantity_normalized is not None else None,
            "unit_canonical": unit,
            "co2e_kg": str(co2e_kg) if co2e_kg is not None else None,
            "emission_factor": str(ef_value) if ef_value is not None else None,
            "emission_factor_source": ef_source,
            "description": description,
            "location_ref": location_ref,
            "flag_reason": "; ".join(flags) if flags else "",
            "review_status": "flagged" if flags else "pending",
        })

    return records, errors
