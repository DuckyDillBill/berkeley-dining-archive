# Berkeley Dining Archive

A daily, machine-readable archive of UC Berkeley dining hall menus and nutrition data.

Cal Dining only shows menus for about a week at a time, and old menus are not kept. This repo saves a copy every morning, so over time it builds a history: what each dining hall served, when, and what was in it.

The data feeds [CalSwipes](https://apps.apple.com/app/id6815878177), an iOS app that helps Berkeley students plan meals around their calorie and macro goals.

## How it works

1. A GitHub Actions workflow runs every morning at about 5:30 AM Pacific.
2. `scraper/archive.py` downloads the menu file Cal Dining publishes for each location, including Café 3, Clark Kerr, Crossroads, Foothill and the campus cafes and markets.
3. Each menu item becomes one row in a CSV, with its nutrients, allergens and diet labels.
4. The workflow commits the new day's data to this repo.

The scraper only uses the Python standard library. It sends one request per location per day, with a pause between requests.

## The data

| Path | What's in it |
|---|---|
| `data/menus/YYYY/YYYY-MM-DD.csv` | Every menu item served that day: one row per location × meal period × item |
| `data/daily_log.csv` | One line per day: locations open, number of items, median calories, highest-protein item, and whether menus were published |

### Columns in the daily menu files

| Column | Meaning |
|---|---|
| `date`, `location`, `meal_period`, `meal_start`, `meal_end` | When and where the item was served |
| `recipe_id`, `name`, `category` | Cal Dining's item ID, display name and station (e.g. "Center Plate") |
| `serving_size`, `serving_unit` | Portion the nutrition values refer to |
| `calories_kcal`, `protein_g`, `carbs_g`, `fat_g`, `sat_fat_g`, `trans_fat_g`, `fiber_g`, `sugar_g`, `sodium_mg`, `cholesterol_mg`, … | Nutrition per serving |
| `co2_kg` | Cal Dining's estimated carbon footprint per serving |
| `contains_*` | Allergen flags (1 = contains): milk, egg, fish, shellfish, tree nuts, wheat, peanuts, soybeans, gluten, alcohol, sesame, pork |
| `is_vegan`, `is_vegetarian`, `is_halal`, `is_kosher` | Diet labels |
| `ingredients` | Full ingredient list |

## Questions this data can answer

- Which dining hall gives the most protein per calorie?
- How often does each dish come back, and can tomorrow's menu be predicted?
- How do menus change between weekdays and weekends, or between semesters?
- What does a day of high-protein, vegetarian or halal eating look like at each hall?

## Run it yourself

```bash
python scraper/archive.py                       # today's menus
python scraper/archive.py --date 20261117       # a specific day (only works while it's still posted)
python -m pytest -q tests                       # parser tests (offline)
```

## Notes

- Menu and nutrition data belongs to Cal Dining (UC Berkeley). Their disclaimer applies: values are estimates and can change because of sourcing, portion size and preparation. Don't rely on them for allergies; ask the dining staff or the Cal Dining dietitian.
- A few items are published with whole-batch nutrition, for example a 241 oz "serving" of chicken salad. The menu CSVs keep them exactly as Cal Dining published them. The daily summary skips any serving over 32 oz, so filter those out in your own analysis too.
- On days when dining halls are closed, such as breaks and holidays, the log records "no menus published."
- This is a student project and isn't affiliated with Cal Dining.

## License

Code: MIT. Data: © UC Berkeley Cal Dining, archived for research and personal use.
