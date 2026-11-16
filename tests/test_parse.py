from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
from archive import FIELDS, parse  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "Crossroads_20261117.xml"


def test_parse_fixture():
    rows = parse(FIXTURE.read_bytes())
    assert len(rows) == 2
    eggs, chicken = rows
    assert set(eggs) == set(FIELDS)
    assert eggs["name"] == "Scrambled Eggs"
    assert eggs["meal_period"] == "Fall - Breakfast"
    assert eggs["calories_kcal"] == 184.98
    assert eggs["protein_g"] == 13.92
    assert eggs["contains_egg"] == 1 and eggs["contains_milk"] == 0
    assert eggs["is_vegetarian"] == 1 and eggs["is_vegan"] == 0
    assert chicken["is_halal"] == 1
    assert chicken["protein_g"] == 25.17
    assert chicken["ingredients"].startswith("Chicken Breast")
