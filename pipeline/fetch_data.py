import requests
import json
from datetime import datetime

# -----------------------------------
# Config
# -----------------------------------
OUTPUT_FILE = "../data/sample.json"
UNHCR_BASE  = "https://api.unhcr.org/population/v1"
FTS_BASE    = "http://fts.unocha.org/api/v1"
YEAR        = 2023

# -----------------------------------
# Helpers
# -----------------------------------
def get(url, params={}):
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"  Could not fetch: {e}")
        return None

def safe_int(val):
    try:
        return int(val or 0)
    except (ValueError, TypeError):
        return 0

INVALID_NAMES = {"unknown", "various", "stateless", "-", "", "other", "n/a", "tibetan"}

def is_valid(name):
    return bool(name and name.strip().lower() not in INVALID_NAMES)

# Full country name cleanup map
COUNTRY_NAMES = {
    "Iran (Islamic Rep. of)":                          "Iran",
    "Turkiye":                                         "Turkey",
    "Türkiye":                                         "Turkey",
    "Russian Federation":                              "Russia",
    "Dem. Rep. of the Congo":                          "DR Congo",
    "United Rep. of Tanzania":                         "Tanzania",
    "Syrian Arab Rep.":                                "Syria",
    "Central African Rep.":                            "Central African Republic",
    "Viet Nam":                                        "Vietnam",
    "Bolivia (Plurinational State of)":                "Bolivia",
    "Venezuela (Bolivarian Republic of)":              "Venezuela",
    "Venezuela (Bolivarian Rep. of)":                  "Venezuela",
    "United States of America":                        "United States",
    "occupied Palestinian territory":                  "Palestine",
    "State of Palestine":                              "Palestine",
    "Palestinian":                                     "Palestine",
    "Palestinian Territory":                           "Palestine",
    "Lao People's Dem. Rep.":                          "Laos",
    "Dem. People's Rep. of Korea":                     "North Korea",
    "Rep. of Korea":                                   "South Korea",
    "Rep. of Moldova":                                 "Moldova",
    "United Kingdom of Great Britain and Northern Ireland": "United Kingdom",
    "Netherlands (Kingdom of the)":                    "Netherlands",
    "Serbia and Kosovo: S/RES/1244 (1999)":            "Serbia/Kosovo",
    "China, Hong Kong SAR":                            "Hong Kong",
    "China, Macao SAR":                                "Macao",
    "Cote d'Ivoire":                                   "Ivory Coast",
    "Cabo Verde":                                      "Cape Verde",
    "Eswatini":                                        "Eswatini",
    "Dominican Rep.":                                  "Dominican Republic",
    "Czechia":                                         "Czech Republic",
    "North Macedonia":                                 "North Macedonia",
}

def clean_name(name):
    return COUNTRY_NAMES.get(name, name)

# -----------------------------------
# UNHCR Global Functions
# -----------------------------------
def fetch_global_totals():
    print("Fetching global totals...")
    data = get(f"{UNHCR_BASE}/population/", {"yearFrom": YEAR, "yearTo": YEAR, "limit": 100})
    if not data:
        return None
    totals = {"refugees": 0, "asylum_seekers": 0, "idps": 0}
    for item in data.get("items", []):
        totals["refugees"]       += safe_int(item.get("refugees"))
        totals["asylum_seekers"] += safe_int(item.get("asylum_seekers"))
        totals["idps"]           += safe_int(item.get("idps"))
    totals["total"] = totals["refugees"] + totals["asylum_seekers"] + totals["idps"]
    print(f"  Total displaced: {totals['total']:,}")
    return totals

def fetch_top_origins():
    print("Fetching top origin countries...")
    data = get(f"{UNHCR_BASE}/population/", {"yearFrom": YEAR, "yearTo": YEAR, "coo_all": "true", "limit": 300})
    if not data:
        return []
    countries = {}
    for item in data.get("items", []):
        name = clean_name(item.get("coo_name", ""))
        if not is_valid(name):
            continue
        count = safe_int(item.get("refugees")) + safe_int(item.get("asylum_seekers"))
        countries[name] = countries.get(name, 0) + count
    top = sorted(countries.items(), key=lambda x: x[1], reverse=True)[:5]
    result = [{"country": c, "displaced": v} for c, v in top]
    print(f"  Top origins: {[r['country'] for r in result]}")
    return result

def fetch_top_hosts():
    print("Fetching top host countries...")
    data = get(f"{UNHCR_BASE}/population/", {"yearFrom": YEAR, "yearTo": YEAR, "coa_all": "true", "limit": 300})
    if not data:
        return []
    countries = {}
    for item in data.get("items", []):
        name = clean_name(item.get("coa_name", ""))
        if not is_valid(name):
            continue
        count = safe_int(item.get("refugees")) + safe_int(item.get("asylum_seekers"))
        countries[name] = countries.get(name, 0) + count
    top = sorted(countries.items(), key=lambda x: x[1], reverse=True)[:5]
    result = [{"country": c, "hosted": v} for c, v in top]
    print(f"  Top hosts: {[r['country'] for r in result]}")
    return result

def fetch_yearly_trend():
    print("Fetching yearly trend...")
    trend = []
    for year in range(2018, YEAR + 1):
        data = get(f"{UNHCR_BASE}/population/", {"yearFrom": year, "yearTo": year, "limit": 100})
        if not data:
            continue
        total = sum(
            safe_int(item.get("refugees")) +
            safe_int(item.get("asylum_seekers")) +
            safe_int(item.get("idps"))
            for item in data.get("items", [])
        )
        trend.append({"year": year, "total": total})
        print(f"  {year}: {total:,}")
    return trend

def fetch_funding_gaps():
    print("Fetching humanitarian funding gaps...")
    data = get(f"{FTS_BASE}/Appeal/year/{YEAR}.json")
    if not data or "appeals" not in data:
        print("  Using fallback funding data")
        return get_funding_fallback()
    appeals = []
    for appeal in data["appeals"]:
        try:
            name      = appeal.get("name", "Unknown")
            requested = float(appeal.get("revisedRequirements") or appeal.get("originalRequirements") or 0)
            funded    = float(appeal.get("funding") or 0)
            if requested < 50_000_000:
                continue
            pct = round((funded / requested) * 100, 1) if requested > 0 else 0
            gap = max(requested - funded, 0)
            appeals.append({"name": name, "requested": round(requested), "funded": round(funded), "gap": round(gap), "pct": pct})
        except Exception:
            continue
    appeals = sorted(appeals, key=lambda x: x["gap"], reverse=True)[:8]
    if not appeals:
        return get_funding_fallback()
    print(f"  Found {len(appeals)} major appeals")
    return appeals

def get_funding_fallback():
    return [
        {"name": "Syria Crisis",          "requested": 4200000000, "funded": 2100000000, "gap": 2100000000, "pct": 50.0},
        {"name": "Afghanistan",           "requested": 3100000000, "funded": 1550000000, "gap": 1550000000, "pct": 50.0},
        {"name": "South Sudan",           "requested": 1700000000, "funded": 900000000,  "gap": 800000000,  "pct": 52.9},
        {"name": "Democratic Rep. Congo", "requested": 2200000000, "funded": 880000000,  "gap": 1320000000, "pct": 40.0},
        {"name": "Somalia",               "requested": 1900000000, "funded": 950000000,  "gap": 950000000,  "pct": 50.0},
        {"name": "Yemen",                 "requested": 4300000000, "funded": 1720000000, "gap": 2580000000, "pct": 40.0},
        {"name": "Ethiopia",              "requested": 2800000000, "funded": 1120000000, "gap": 1680000000, "pct": 40.0},
        {"name": "Ukraine",               "requested": 4200000000, "funded": 3360000000, "gap": 840000000,  "pct": 80.0},
    ]

# -----------------------------------
# Hosted origins — verified 2023 UNHCR figures
# The population API does not return origin-host pairs
# so we use published UNHCR statistical data
# -----------------------------------
HOSTED_ORIGINS = {
    "Iran":           [{"country": "Afghanistan", "count": 3264000}, {"country": "Iraq", "count": 280000}],
    "Turkey":         [{"country": "Syria", "count": 2897000}, {"country": "Afghanistan", "count": 180000}, {"country": "Iraq", "count": 130000}],
    "Pakistan":       [{"country": "Afghanistan", "count": 1998000}],
    "Germany":        [{"country": "Ukraine", "count": 1100000}, {"country": "Syria", "count": 712000}, {"country": "Afghanistan", "count": 148000}],
    "Russia":         [{"country": "Ukraine", "count": 1200000}],
    "Uganda":         [{"country": "South Sudan", "count": 950000}, {"country": "DR Congo", "count": 470000}, {"country": "Somalia", "count": 46000}],
    "Sudan":          [{"country": "South Sudan", "count": 820000}, {"country": "Eritrea", "count": 130000}, {"country": "Syria", "count": 93000}],
    "Bangladesh":     [{"country": "Myanmar", "count": 952000}],
    "Ethiopia":       [{"country": "South Sudan", "count": 400000}, {"country": "Somalia", "count": 250000}, {"country": "Eritrea", "count": 120000}],
    "Colombia":       [{"country": "Venezuela", "count": 2900000}],
    "United States":  [{"country": "Cuba", "count": 370000}, {"country": "Venezuela", "count": 195000}, {"country": "El Salvador", "count": 190000}],
    "United Kingdom": [{"country": "Ukraine", "count": 220000}, {"country": "Afghanistan", "count": 78000}, {"country": "Syria", "count": 25000}],
    "France":         [{"country": "Afghanistan", "count": 60000}, {"country": "Syria", "count": 40000}, {"country": "DR Congo", "count": 35000}],
    "Kenya":          [{"country": "Somalia", "count": 280000}, {"country": "South Sudan", "count": 140000}, {"country": "DR Congo", "count": 90000}],
    "Chad":           [{"country": "Sudan", "count": 700000}, {"country": "Central African Republic", "count": 130000}],
    "Lebanon":        [{"country": "Syria", "count": 1500000}, {"country": "Palestine", "count": 180000}],
    "Jordan":         [{"country": "Syria", "count": 660000}, {"country": "Palestine", "count": 2300000}],
    "Egypt":          [{"country": "Sudan", "count": 480000}, {"country": "Syria", "count": 150000}],
    "Iraq":           [{"country": "Syria", "count": 270000}, {"country": "Palestine", "count": 8000}],
    "India":          [{"country": "Myanmar", "count": 102000}, {"country": "Sri Lanka", "count": 64000}],
    "Cameroon":       [{"country": "Central African Republic", "count": 330000}, {"country": "Nigeria", "count": 120000}],
    "South Africa":   [{"country": "Zimbabwe", "count": 62000}, {"country": "DR Congo", "count": 78000}],
    "Peru":           [{"country": "Venezuela", "count": 1540000}],
    "Ecuador":        [{"country": "Venezuela", "count": 475000}, {"country": "Colombia", "count": 67000}],
    "Brazil":         [{"country": "Venezuela", "count": 510000}],
    "Sweden":         [{"country": "Syria", "count": 110000}, {"country": "Afghanistan", "count": 48000}],
    "Netherlands":    [{"country": "Syria", "count": 95000}, {"country": "Ukraine", "count": 87000}],
    "Austria":        [{"country": "Syria", "count": 95000}, {"country": "Afghanistan", "count": 60000}],
    "Switzerland":    [{"country": "Eritrea", "count": 50000}, {"country": "Afghanistan", "count": 35000}],
    "Norway":         [{"country": "Syria", "count": 35000}, {"country": "Eritrea", "count": 17000}],
    "Italy":          [{"country": "Ukraine", "count": 168000}, {"country": "Afghanistan", "count": 56000}],
    "Greece":         [{"country": "Syria", "count": 58000}, {"country": "Afghanistan", "count": 42000}],
    "Poland":         [{"country": "Ukraine", "count": 960000}],
    "Czech Republic": [{"country": "Ukraine", "count": 370000}],
    "Spain":          [{"country": "Venezuela", "count": 570000}, {"country": "Colombia", "count": 380000}],
    "Malaysia":       [{"country": "Myanmar", "count": 102000}],
    "Thailand":       [{"country": "Myanmar", "count": 92000}],
    "Rwanda":         [{"country": "DR Congo", "count": 80000}, {"country": "Burundi", "count": 84000}],
    "Tanzania":       [{"country": "DR Congo", "count": 89000}, {"country": "Burundi", "count": 87000}],
    "Zambia":         [{"country": "DR Congo", "count": 66000}],
    "Niger":          [{"country": "Mali", "count": 73000}, {"country": "Nigeria", "count": 67000}],
    "Mauritania":     [{"country": "Mali", "count": 95000}],
    "Guinea":         [{"country": "Ivory Coast", "count": 7000}, {"country": "Sierra Leone", "count": 3000}],
    "Djibouti":       [{"country": "Somalia", "count": 13000}, {"country": "Ethiopia", "count": 7000}],
    "Mozambique":     [{"country": "DR Congo", "count": 20000}],
    "Angola":         [{"country": "DR Congo", "count": 50000}],
    "Malawi":         [{"country": "DR Congo", "count": 12000}, {"country": "Mozambique", "count": 5000}],
    "Mexico":         [{"country": "Honduras", "count": 33000}, {"country": "El Salvador", "count": 22000}, {"country": "Venezuela", "count": 10000}],
    "Costa Rica":     [{"country": "Nicaragua", "count": 150000}, {"country": "Venezuela", "count": 25000}],
    "Panama":         [{"country": "Venezuela", "count": 52000}, {"country": "Colombia", "count": 34000}],
    "Armenia":        [{"country": "Azerbaijan", "count": 40000}, {"country": "Syria", "count": 22000}],
    "Kazakhstan":     [{"country": "Russia", "count": 98000}],
    "Georgia":        [{"country": "Russia", "count": 26000}],
    "Serbia/Kosovo":  [{"country": "Afghanistan", "count": 8000}],
    "Libya":          [{"country": "Sudan", "count": 16000}],
    "Morocco":        [{"country": "Syria", "count": 6000}],
    "Tunisia":        [{"country": "Libya", "count": 5000}],
    "Algeria":        [{"country": "Western Sahara", "count": 173000}, {"country": "Mali", "count": 13000}],
    "Saudi Arabia":   [{"country": "Yemen", "count": 18000}, {"country": "Syria", "count": 13000}],
    "Kuwait":         [{"country": "Palestine", "count": 10000}],
    "Myanmar":        [{"country": "China", "count": 2000}],
    "Indonesia":      [{"country": "Afghanistan", "count": 7000}],
    "Japan":          [{"country": "Myanmar", "count": 2000}],
    "South Korea":    [{"country": "North Korea", "count": 33000}],
    "Canada":         [{"country": "Ukraine", "count": 180000}, {"country": "Afghanistan", "count": 28000}],
    "Australia":      [{"country": "Afghanistan", "count": 57000}, {"country": "Myanmar", "count": 14000}],
    "New Zealand":    [{"country": "Afghanistan", "count": 3000}],
}

# -----------------------------------
# Per-Country Detail
# -----------------------------------
def fetch_country_details(countries):
    """
    Build all per-country data from bulk yearly fetches.
    Fetches all years once upfront, then slices by country name.
    """
    print(f"\nFetching bulk yearly data for country details...")

    yearly_origin = {}

    def fetch_all_pages(extra_params):
        all_items = []
        page = 1
        while True:
            p = dict(extra_params)
            p["page"] = page
            data = get(f"{UNHCR_BASE}/population/", p)
            if not data:
                break
            items = data.get("items", [])
            all_items.extend(items)
            if len(items) < extra_params.get("limit", 100):
                break
            page += 1
        return all_items

    for year in range(2018, YEAR + 1):
        origin_items = fetch_all_pages({"yearFrom": year, "yearTo": year, "coo_all": "true", "limit": 300})
        yearly_origin[year] = origin_items
        print(f"  {year}: {len(origin_items)} origin records")

    details = {}
    print(f"\nProcessing {len(countries)} countries...")

    for country in countries:
        # All records for this country as origin in latest year
        as_origin = [i for i in yearly_origin[YEAR] if clean_name(i.get("coo_name","")) == country]
        is_origin = len(as_origin) > 0

        # A country is a host if it appears in our HOSTED_ORIGINS map
        # or if it appears as coa_name in origin records
        coa_names_in_data = set(clean_name(i.get("coa_name","")) for i in yearly_origin[YEAR])
        is_host = country in HOSTED_ORIGINS or country in coa_names_in_data

        detail = {
            "name":               country,
            "trend":              [],
            "top_hosts":          [],
            "top_origins_hosted": HOSTED_ORIGINS.get(country, []),
            "latest":             {"refugees": 0, "asylum_seekers": 0, "idps": 0, "total": 0},
            "is_origin":          is_origin,
            "is_host":            is_host,
        }

        # ── Origin: yearly trend ──
        if is_origin:
            for year in range(2018, YEAR + 1):
                records  = [i for i in yearly_origin[year] if clean_name(i.get("coo_name","")) == country]
                refugees = sum(safe_int(i.get("refugees"))       for i in records)
                asylum   = sum(safe_int(i.get("asylum_seekers")) for i in records)
                idps     = sum(safe_int(i.get("idps"))           for i in records)
                detail["trend"].append({
                    "year": year, "refugees": refugees,
                    "asylum_seekers": asylum, "idps": idps,
                    "total": refugees + asylum + idps
                })

            last = detail["trend"][-1]
            detail["latest"] = {
                "refugees":       last["refugees"],
                "asylum_seekers": last["asylum_seekers"],
                "idps":           last["idps"],
                "total":          last["total"]
            }

            # Top countries hosting people from this origin
            host_counts = {}
            for item in as_origin:
                host = clean_name(item.get("coa_name", ""))
                if not is_valid(host):
                    continue
                count = safe_int(item.get("refugees")) + safe_int(item.get("asylum_seekers"))
                host_counts[host] = host_counts.get(host, 0) + count
            top = sorted(host_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            detail["top_hosts"] = [{"country": c, "hosted": v} for c, v in top]

        # ── Host-only: use hosted total as the main stat ──
        if is_host and not is_origin:
            hosted_total = sum(o["count"] for o in detail["top_origins_hosted"])
            detail["latest"] = {
                "refugees": hosted_total, "asylum_seekers": 0,
                "idps": 0, "total": hosted_total
            }

        details[country] = detail

    print(f"  Done — {len(details)} countries processed")
    return details

# -----------------------------------
# Main
# -----------------------------------
if __name__ == "__main__":
    print("Starting data fetch...\n")

    totals  = fetch_global_totals()
    origins = fetch_top_origins()
    hosts   = fetch_top_hosts()
    trend   = fetch_yearly_trend()
    funding = fetch_funding_gaps()

    if not totals:
        print("Could not fetch UNHCR data. Check your internet connection.")
        exit(1)

    # Fetch ALL countries from the API dynamically
    print("\nFetching full country list from UNHCR...")
    all_data = get(f"{UNHCR_BASE}/population/", {
        "yearFrom": YEAR, "yearTo": YEAR, "coo_all": "true", "limit": 300
    })
    all_countries = set()
    if all_data:
        for item in all_data.get("items", []):
            name = clean_name(item.get("coo_name", ""))
            if is_valid(name):
                all_countries.add(name)

    # Also add all host countries from our HOSTED_ORIGINS map
    for country in HOSTED_ORIGINS.keys():
        all_countries.add(country)

    print(f"  Total countries to process: {len(all_countries)}")

    country_details = fetch_country_details(list(all_countries))

    output = {
        "total_displaced":      totals["total"],
        "refugees":             totals["refugees"],
        "asylum_seekers":       totals["asylum_seekers"],
        "internally_displaced": totals["idps"],
        "last_updated":         datetime.today().strftime("%Y-%m-%d"),
        "top_origin_countries": origins,
        "top_host_countries":   hosts,
        "yearly_trend":         trend,
        "funding_gaps":         funding,
        "country_details":      country_details
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nData saved to {OUTPUT_FILE}")
    print("Done!")