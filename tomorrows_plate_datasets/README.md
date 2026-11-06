# Tomorrow's Plate — Elio Volpe dinner datasets

Built from the Elio Volpe dinner menu (eliovolpe.com/menu-dinner) to the ERD in the Leftover Map.
35 dishes → 40 dish/size rows, 179 ingredient lines, 88 components.

## Files and keys
| File | Grain | Key | Joins |
|---|---|---|---|
| elio_volpe_dinner_ingredients.csv | dish × size × ingredient | dish_id + ingredient | menu_setup.dish_id |
| menu_setup.csv | dish × size | dish_id | base_dish_id groups sizes |
| dish_components.csv | dish × component | dish_id + component_id | menu_setup, components |
| components.csv | anything that can be left over at close | component_id | hub table |
| ingredient_forms.csv | 1:1 with ingredient lines | dish_id + ingredient | ingredient lines, components (RAW-AT-SERVICE = used straight from stock) |
| leftover_log_template.csv | what cooks fill in at close | log_date + component_id | components |
| leftover_log_sample.csv | a sample close for 2026-11-04, for testing the agent | | components |

## IDs
- dish_id = base id + size: `D19-S` / `D19-L` (two prices on the menu), `D01-R` (one size).
- component_id is a readable slug, e.g. `C-LAMB-RAGU`.

## Value lists
- service_style: made_ahead, made_to_order, assembled_cold
- leftover_logged_as: finished_portions (made ahead) or components
- form / form_at_close: finished_portion, cooked, sauce_dressing, dough, raw_prepped, garnish; raw_at_service is used for the RAW-AT-SERVICE label
- storage: walk_in, freezer, dry_store, live_on_ice
- role: base, protein, sauce, dressing, side, topping, garnish, crunch, finish, spread, vehicle, dessert, seasoning, cooking_medium
- ingredient_category: meat, poultry, seafood, cured_meat, dairy, egg, produce, herb, grain, nut_seed, spice, pantry, oil_fat, sweetener, alcohol

## For the agent
- Leftover log: expires_on = made_on + default_shelf_life_days; days_until_expired = expires_on − log_date. Cooks fill in the first five columns; the last two are calculated. 1 = must be used at tomorrow's family meal; 0 or less = expired, discard. Use the lowest first.
- RAW-AT-SERVICE is a label, not a leftover: skip it when reading the leftover log.
- freezable = yes is an option for anything not used tomorrow.

## Assumptions to check with the kitchen
Quantities per portion, shelf lives and which items are prepped ahead are estimates based on the menu wording and common practice, not house recipes. Shelf lives are conservative defaults; replace them with your own policy.
