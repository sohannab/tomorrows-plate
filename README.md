# Tomorrow's Plate

**Turn tonight's leftovers into tomorrow's plan.** A kitchen dashboard that shows what is about to go bad, what to run as a special, what to feed the staff, and what to stop over-prepping.

**[Try the live app]([TODO: paste your Streamlit link])**

[TODO: add a screenshot of the Home tab here, for example `![Home dashboard](assets/home.png)`]

## The problem

Restaurants prep ahead, so they close most nights with sauces, doughs and cooked items left over. Cooks usually know what is sitting in the walk-in, but that knowledge rarely turns into a decision. Items expire, and the same over-prep happens again the following week.

Tomorrow's Plate tracks leftovers at the component level, such as a lamb ragu or a pizza dough, not just finished dishes. One component often feeds several menu items, so that is where a kitchen has the most options for using it up.

## What it does

- **Daily special:** suggests dishes that use up items with more than 2 days left, and shows the menu sales each one could bring in.
- **Prep less:** finds items left over again and again, on the coming weekday or across the last 2 to 4 weeks, and recommends how much less to prep. A day-by-day strip shows the pattern behind each recommendation.
- **Going bad soon:** a table of everything with 1 to 2 days left, filterable by ingredient form.
- **Staff meal:** five options built from what is about to expire, with the portions each could make and what is still needed.
- **Menu:** every dish and its components, by menu section.
- **Leftovers:** current stock by ingredient form. Clicking an ingredient shows each batch, its days left and any note.
- **Log:** where cooks record leftovers at close, with amounts, made dates and notes. An ingredient can have several entries for batches made on different dates.

## How it works

The app is built on a dataset our team created from the Elio Volpe dinner menu: 35 dishes, 88 components and 179 ingredient lines, linked so that any leftover can be traced to the dishes it could go into.

| Feature | Logic |
|---|---|
| Days left | Made date plus the component's default shelf life, counted from the latest close. Expired batches drop off. |
| Staff meal and special | Each dish is scored by the items it would use up, and items with fewer days left count for more. A dish is only suggested if its main components are in stock, and portions are capped by the scarcest component. |
| Prep less | An item is flagged if it was left over on at least 75% of recent matching weekdays, or on at least 70% of all days. The suggested cut is the smallest amount left over in that period, so it stays conservative. |
| Menu sales | Listed menu price multiplied by the portions the dish could make. |

## Built with

Python, pandas and Streamlit, with custom HTML and CSS for the cards and the leftover strips.

## About the data

- **The history is simulated.** The Prep less stats use made-up close logs for Oct 1 to Nov 3, 2026, with patterns planted to show how the feature works. They are not real kitchen records.
- **Quantities are estimates.** Portion sizes, shelf lives and prep assumptions are based on the menu wording and common practice, not house recipes.
- **Sales are not profit.** The figures use listed menu prices. The dataset has no food costs, so the app cannot show margins or waste saved.
- **Recommendations are rule-based.** They match leftovers to existing menu dishes. No AI model runs in this version.

## How the project evolved

Tomorrow's Plate started as a prototype by Algorithm Avengers: a planning model that forecast demand using patterns from the Food Demand Forecasting dataset on Kaggle, then optimized prep quantities. That model is not part of this version. This app focuses on the day-to-day tool a cook would use, built around a more detailed component-level dataset.

## What I would build next

- Save logs to a database, so entries are kept permanently. They currently live in a file that the free host wipes on restart.
- Replace the simulated history with real close logs.
- Add food costs, so recommendations can show margin rather than sales.
- Use an AI model to write staff meal and special recipes, with the leftovers as constraints.
- Track what gets used or thrown away, so stock goes down as well as up.
- Share ingredients across suggestions, so two ideas never count the same stock.
- Add a staff count, so meals are sized to the team, and a login for each kitchen.

## Team

Built by **Algorithm Avengers**: Sohanna Bains, Chase Hudson and Jomana Eid.

**My role:** [TODO: one or two sentences on what you personally did]

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

It opens at http://localhost:8501. The app uses Vancouver time, which you can change with `KITCHEN_TIMEZONE` in `app.py`.

## Project files

| File | Job |
|---|---|
| `app.py` | The whole app |
| `tomorrows_plate_datasets/` | Menu, components and leftover logs, with their own README |
| `elio_volpe_dinner_ingredients.csv` | Listed menu prices for the sales figures |
| `requirements.txt` | Packages |

AI attribution: drafted with the assistance of Claude (Anthropic) and reviewed by the authors.
