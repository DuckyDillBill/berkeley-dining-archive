"""Archive today's UC Berkeley dining menus and nutrition data.

Cal Dining publishes one XML file per location per day (the same data that
powers https://dining.berkeley.edu/menus/). This script downloads every
location's file for a given date and flattens it into a tidy CSV with one row per (location, meal period, menu item).

Usage:
    python scraper/archive.py              # today, Pacific time
    python scraper/archive.py --date 20261117
    python scraper/archive.py --from-dir tests/fixtures --date 20261117  # offline
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_URL = "https://dining.berkeley.edu/wp-content/uploads/menus-exportimport/{slug}_{date}.xml"
USER_AGENT = "berkeley-dining-archive (student research project; github.com/DuckyDillBill)"
PACIFIC = ZoneInfo("America/Los_Angeles")

# Location slugs as used in the menu page's filter. Not every location
# publishes every day (markets and cafes close on weekends and breaks).
LOCATIONS = [
    "Cafe_3",
    "Clark_Kerr_Campus",
    "Crossroads",
    "Foothill",
    "Golden_Bear_Cafe",
    "Eateries_at_the_Student_Union",
    "Browns_Cafe",
    "Bear_Market",
    "Cub_Market",
    "Local_x_Design",
    "Den",
    "Qualcomm_Cafe",
    "Gateway_Cafe",
]

# Short, analysis-friendly column names for the nutrient list in the XML.
NUTRIENT_COLUMNS = {
    "Calories (kcal)": "calories_kcal",
    "Total Lipid/Fat (g)": "fat_g",
    "Saturated fatty acid (g)": "sat_fat_g",
    "Trans Fat (g)": "trans_fat_g",
    "Cholesterol (mg)": "cholesterol_mg",
    "Sodium (mg)": "sodium_mg",
    "Carbohydrate (g)": "carbs_g",
    "Total Dietary Fiber (g)": "fiber_g",
    "Sugar (g)": "sugar_g",
    "Protein (g)": "protein_g",
    "Vitamin A (iu)": "vitamin_a_iu",
    "Vitamin C (mg)": "vitamin_c_mg",
    "Calcium (mg)": "calcium_mg",
    "Iron (mg)": "iron_mg",
    "Water (g)": "water_g",
    "Ash (g)": "ash_g",
    "Vitamin A (rae)": "vitamin_a_rae",
    "Potassium (mg)": "potassium_mg",
    "Vitamin D(iu)": "vitamin_d_iu",
    "Carbon Footprint (kg CO2)": "co2_kg",
}

ALLERGENS = ["Milk", "Egg", "Fish", "Shellfish", "Tree Nuts", "Wheat", "Peanuts",
             "Soybeans", "Gluten", "Alcohol", "Sesame", "Pork"]
DIETS = ["Vegan Option", "Vegetarian Option", "Halal", "Kosher"]


def slugify(label: str) -> str:
    return label.lower().replace(" option", "").replace(" ", "_")


FIELDS = (
    ["date", "location", "meal_period", "meal_start", "meal_end", "menu_id",
     "recipe_id", "name", "category", "serving_size", "serving_unit"]
    + list(NUTRIENT_COLUMNS.values())
    + [f"contains_{slugify(a)}" for a in ALLERGENS]
    + [f"is_{slugify(d)}" for d in DIETS]
    + ["ingredients"]
)


def fetch(slug: str, date: str, retries: int = 3) -> bytes | None:
    """Return the XML bytes for one location/date, or None if not published."""
    url = BASE_URL.format(slug=slug, date=date)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            err = e
        except urllib.error.URLError as e:
            err = e
        time.sleep(2 * attempt)
    print(f"  ! {slug}: gave up after {retries} tries ({err})", file=sys.stderr)
    return None


def to_float(value: str) -> float | str:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return ""


def parse(xml_bytes: bytes) -> list[dict]:
    """Flatten one location's XML into rows."""
    root = ET.fromstring(xml_bytes)
    rows = []
    for menu in root.iter("menu"):
        names_el = menu.find("nutrients")
        names = (names_el.text or "").strip().strip("|").split("|") if names_el is not None else []
        for recipe in menu.iter("recipe"):
            values = (recipe.get("nutrients") or "").strip().strip("|").split("|")
            nutrients = dict(zip(names, values))
            row = {
                "date": menu.get("servedate", ""),
                "location": menu.get("location", ""),
                "meal_period": menu.get("mealperiodname", ""),
                "meal_start": menu.get("mealstarttime", ""),
                "meal_end": menu.get("mealendtime", ""),
                "menu_id": menu.get("id", ""),
                "recipe_id": recipe.get("id", ""),
                "name": (recipe.get("shortName") or recipe.get("description") or "").strip(),
                "category": (recipe.get("category") or "").strip(),
                "serving_size": to_float(recipe.get("servingSize")),
                "serving_unit": recipe.get("servingSizeUnit", ""),
            }
            for label, col in NUTRIENT_COLUMNS.items():
                row[col] = to_float(nutrients.get(label))
            flags = {el.get("id"): (el.text or "").strip() == "Yes" for el in recipe.iter("allergen")}
            for a in ALLERGENS:
                row[f"contains_{slugify(a)}"] = int(flags.get(a, False))
            diets = {el.get("id"): (el.text or "").strip() == "Yes" for el in recipe.iter("dietaryChoice")}
            for d in DIETS:
                row[f"is_{slugify(d)}"] = int(diets.get(d, False))
            ing = recipe.find("ingredients")
            row["ingredients"] = " ".join((ing.text or "").split()) if ing is not None else ""
            rows.append(row)
    return rows


# Some items are published with whole-batch nutrition (e.g. a 241 oz "serving"
# of chicken salad). Keep them in the menu CSVs as published, but leave them
# out of the daily summary so one bad entry doesn't skew it.
MAX_PLAUSIBLE_SERVING_OZ = 32


def plausible(row: dict) -> bool:
    size = row["serving_size"]
    return not (row["serving_unit"] == "oz" and isinstance(size, float) and size > MAX_PLAUSIBLE_SERVING_OZ)


def update_log(log_path: Path, date: str, rows: list[dict], locations: list[str]) -> None:
    """Append (or replace) one summary line per day in data/daily_log.csv."""
    iso = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    good = [r for r in rows if plausible(r)]
    cals = [r["calories_kcal"] for r in good if isinstance(r["calories_kcal"], float)]
    top = max((r for r in good if isinstance(r["protein_g"], float)),
              key=lambda r: r["protein_g"], default=None)
    entry = {
        "date": iso,
        "locations_open": len(locations),
        "menu_rows": len(rows),
        "unique_items": len({r["name"] for r in rows}),
        "median_calories": round(sorted(cals)[len(cals) // 2], 1) if cals else "",
        "top_protein_item": f'{top["name"]} ({top["location"]}, {top["protein_g"]}g)' if top else "",
        "status": "ok" if rows else "no menus published",
    }
    existing = []
    if log_path.exists():
        with log_path.open(newline="") as f:
            existing = [r for r in csv.DictReader(f) if r["date"] != iso]
    existing.append(entry)
    existing.sort(key=lambda r: r["date"])
    with log_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(entry))
        w.writeheader()
        w.writerows(existing)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="YYYYMMDD (default: today in Pacific time)")
    ap.add_argument("--out", default="data", help="output folder (default: data)")
    ap.add_argument("--from-dir", help="read <slug>_<date>.xml files from this folder instead of the web")
    args = ap.parse_args()

    date = args.date or dt.datetime.now(PACIFIC).strftime("%Y%m%d")
    out = Path(args.out)
    menus_dir = out / "menus" / date[:4]
    menus_dir.mkdir(parents=True, exist_ok=True)

    print(f"Archiving Cal Dining menus for {date}")
    rows, opened = [], []
    for slug in LOCATIONS:
        if args.from_dir:
            p = Path(args.from_dir) / f"{slug}_{date}.xml"
            data = p.read_bytes() if p.exists() else None
        else:
            data = fetch(slug, date)
            time.sleep(0.5)  # be polite to the university's server
        if not data or b"<menu" not in data:
            print(f"  - {slug}: no menu")
            continue
        loc_rows = parse(data)
        print(f"  + {slug}: {len(loc_rows)} items")
        rows.extend(loc_rows)
        opened.append(slug)

    if rows:
        csv_path = menus_dir / f"{date[:4]}-{date[4:6]}-{date[6:]}.csv"
        with csv_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        print(f"Wrote {len(rows)} rows to {csv_path}")
    else:
        print("No menus published today (break, holiday, or the site changed).")

    update_log(out / "daily_log.csv", date, rows, opened)
    return 0


if __name__ == "__main__":
    sys.exit(main())
