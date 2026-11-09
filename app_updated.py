"""Tomorrow's Plate - Streamlit app.

Run:  streamlit run app.py

An AI agent that plans tomorrow's prep around tonight's leftovers. The menu data lives in
tomorrows_plate_datasets/.
"""
from __future__ import annotations

import os
import base64
import datetime as dt
from gettext import install
import html
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd 
import streamlit as st
from urllib.parse import quote_plus

st.set_page_config(page_title="Tomorrow's Plate", layout="wide")
S = st.session_state

# Colours, customisations, etc
PATTERN_FILE = "assets/kitchen_pattern.jpg"
PATTERN_FADE = 0.68
PATTERN_TILE_PX = 520
PANEL_OPACITY = 0.88
CREAM = "250, 243, 234"

KITCHEN_TIMEZONE = ZoneInfo("America/Vancouver")
DATA_DIR = Path(__file__).parent / "tomorrows_plate_datasets"
LOG_FILE = DATA_DIR / "leftover_log.csv"   # what cooks submit on the Log tab
HISTORY_FILE = DATA_DIR / "leftover_log_history_sample.csv"   # simulated closes for the Home tab stats
LOG_FIELDS = ["log_date", "component_id", "amount", "unit", "made_on", "expires_on", "days_until_expired", "note"]
SECTION_NAMES = {
    "antipasti": "Antipasti", "insalata_e_verdure": "Insalata e Verdure", "pizza": "Pizza",
    "pasta_e_risotto": "Pasta e Risotto", "carne": "Carne", "mare": "Mare", "dolce": "Dolce", "gelato": "Gelato",
}
FORM_NAMES = {
    "finished_portion": "Finished Portions", "cooked": "Cooked", "sauce_dressing": "Sauces and Dressings",
    "dough": "Dough", "raw_prepped": "Raw Prepped", "garnish": "Garnishes",
}
PRICE_FILE = Path(__file__).parent / "elio_volpe_dinner_ingredients.csv"   # listed menu prices
PRICE_NAMES = {   # price file name -> current dish name
    "Baccala mantecato": "Baccalà 'mantecato'", "Margherita": "Margherita pizza", "Primavera": "Primavera pizza",
    "Roasted mushroom": "Roasted mushroom pizza", "Manila clam": "Manila clam pizza", "Pepperone": "Pepperone pizza",
    "Capocollo": "Capocollo pizza", "Risotto": "Risotto, lobster tail", "Stracci": "Stracci, lamb ragu",
    "Gelato, daily flavour": "Gelato (daily flavours)",
}
MAIN_ROLES = ["base", "protein", "dessert"]   # a dish cannot be suggested without these
URGENT_DAYS = 2      # at or below this many days left, an item is going bad soon
LEFTOVER_COLUMNS = [5, 1.5, 1.5, 4]   # ingredient, amount, shelf life, empty space
LOG_COLUMNS = [3.6, 0.8, 0.8, 1.5, 3.2, 1.1]   # ingredient, amount box, unit, made on, note, add or remove
MENU_CSS = """
<style>
.menu-table { width: 100%; table-layout: fixed; border-collapse: collapse; margin-bottom: 1.5rem; }
.menu-table th { text-align: left; font-size: 0.8rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
                 color: #8A4B2D; padding: 0.4rem 0.75rem; border-bottom: 2px solid #8A4B2D; }
.menu-table td { padding: 0.6rem 0.75rem; vertical-align: top; border-bottom: 1px solid #EBD9C6; }
.menu-table .id { width: 5.5rem; color: #8A4B2D; font-variant-numeric: tabular-nums; }
.menu-table .dish { width: 24%; font-weight: 600; }
.menu-chip { display: inline-block; background: #EBD9C6; border-radius: 999px; padding: 0.1rem 0.65rem;
             margin: 0.1rem 0.3rem 0.1rem 0; font-size: 0.875rem; }
.leftover-head { font-size: 0.8rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: #8A4B2D; }
[class*="st-key-leftover-head"] { border-bottom: 2px solid #8A4B2D; padding: 0.4rem 0.75rem; }
[class*="st-key-leftover-row"] { border-bottom: 1px solid #EBD9C6; padding: 0.45rem 0.75rem; }
[class*="st-key-leftover-row"] button { min-height: 0; padding: 0; justify-content: flex-start; text-align: left; }
[class*="st-key-leftover-row"] button p { font-size: 1rem; font-weight: 600; color: #8A4B2D; text-align: left; }
[class*="st-key-leftover-row"] button:hover p { text-decoration: underline; }
[class*="st-key-leftover-"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; }
[class*="st-key-leftover-"] [data-testid="stColumn"] { min-width: 0; }
[class*="st-key-leftover-row-log"] [data-testid="stNumberInputStepDown"],
[class*="st-key-leftover-row-log"] [data-testid="stNumberInputStepUp"] { display: none; }
.log-name { font-weight: 600; }
.menu-table .urgent { font-weight: 700; color: #8A4B2D; }
[class*="st-key-home-feature"] { background: rgba(255, 252, 247, 0.9); border: 1px solid #EBD9C6; border-radius: 16px;
                                 padding: 1.1rem 1.3rem; box-shadow: 0 2px 10px rgba(62, 42, 32, 0.08); }
.card-row { display: flex; gap: 0.9rem; overflow-x: auto; padding-bottom: 0.6rem; scroll-snap-type: x proximity; }
.card { flex: 0 0 min(310px, 88%); scroll-snap-align: start; border: 1px solid #EBD9C6; border-radius: 14px;
        padding: 0.9rem 1rem; background: rgba(255, 252, 247, 0.75); }
.card.special { background: #8A4B2D; border-color: #8A4B2D; color: #FAF3EA; }
.card.special .idea-label { color: #EBD9C6; }
.card.special .menu-chip { background: #FAF3EA; color: #3E2A20; }
.card-tag { display: inline-block; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
            color: #8A4B2D; margin-bottom: 0.2rem; }
.card-sales { font-size: 2.1rem; font-weight: 700; line-height: 1.15; margin-top: 0.3rem; }
.idea-title { font-size: 1.1rem; font-weight: 600; }
.idea-label { font-size: 0.8rem; font-weight: 600; color: #8A4B2D; margin-top: 0.45rem; }
.repeat-list { max-height: 380px; overflow-y: auto; }
.repeat { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem 1.2rem; padding: 0.55rem 0;
          border-bottom: 1px solid #EBD9C6; }
.repeat-text { flex: 1 1 230px; min-width: 0; }
.repeat-name { font-weight: 600; }
.repeat-cut { font-size: 1.35rem; font-weight: 700; color: #8A4B2D; line-height: 1.2; }
.repeat-why { font-size: 0.8rem; }
.strip { flex: 1 1 300px; display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; gap: 2px; }
.strip span, .strip-key span { height: 18px; border-radius: 3px; background: #F1E4D6; }
.strip .hit, .strip-key .hit { background: #CFA98F; }
.strip .focus, .strip-key .focus { background: #8A4B2D; }
.strip-key { display: flex; flex-wrap: wrap; align-items: center; gap: 0.3rem 0.9rem; font-size: 0.8rem; margin-bottom: 0.3rem; }
.strip-key span { display: inline-block; width: 12px; height: 12px; margin-right: 0.3rem; vertical-align: -1px; }
.scroll-table { max-height: 380px; overflow-y: auto; }
.scroll-table .menu-table { margin-bottom: 0; }
.scroll-table th { position: sticky; top: 0; z-index: 1; background: #FAF3EA; }
.menu-table .group td { font-weight: 600; background: #EBD9C6; padding: 0.3rem 0.75rem; }
[data-testid="stDialog"] > div { margin-top: auto; margin-bottom: auto; }
@media (max-width: 900px) {
    [class*="st-key-leftover-head-log"] { display: none; }
    [class*="st-key-leftover-row-log"] [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
    [class*="st-key-leftover-row-log"] [data-testid="stColumn"] { min-width: 8.5rem; }
    [class*="st-key-leftover-row-log"] [data-testid="stColumn"]:first-child { min-width: 100%; }
}
@media (max-width: 700px) {
    [class*="st-key-leftover-"]:not([class*="-log-"]) [data-testid="stColumn"]:last-child { display: none; }
}
</style>"""


def kitchen_today() -> dt.date:
    """Today in the kitchen's time zone. Hosted servers run on UTC, which is already tomorrow at a late close."""
    return dt.datetime.now(KITCHEN_TIMEZONE).date()


@st.cache_data
def background_css() -> str:
    path = Path(__file__).parent / PATTERN_FILE
    try:
        b64 = base64.b64encode(path.read_bytes()).decode()
    except OSError:
        return ""
    return f"""
    <style>
    .stApp {{
        background-image: linear-gradient(rgba({CREAM}, {PATTERN_FADE}), rgba({CREAM}, {PATTERN_FADE})),
                          url("data:image/jpeg;base64,{b64}");
        background-size: auto, {PATTERN_TILE_PX}px;
        background-repeat: repeat;
        background-attachment: fixed;
    }}
    [data-testid="stHeader"] {{ background: transparent; }}
    [data-testid="stMainBlockContainer"], .block-container {{
        background: rgba({CREAM}, {PANEL_OPACITY});
        border-radius: 18px;
        margin-top: 1rem;
        padding: 2rem 2.2rem 2.5rem;
        max-width: none;
    }}
    </style>"""


st.markdown(background_css(), unsafe_allow_html=True)


@st.cache_data
def menu_table() -> pd.DataFrame:
    """One row per dish and size, in menu order, with its components spelled out."""
    menu = pd.read_csv(DATA_DIR / "menu_setup.csv")
    links = pd.read_csv(DATA_DIR / "dish_components.csv")
    components = pd.read_csv(DATA_DIR / "components.csv").set_index("component_id").component_name
    names = links.component_id.map(components).groupby(links.dish_id, sort=False).agg(list)
    return menu.assign(components=menu.dish_id.map(names))


def section_html(dishes: pd.DataFrame) -> str:
    rows = ""
    for dish in dishes.itertuples():
        chips = "".join(f'<span class="menu-chip">{html.escape(name)}</span>' for name in dish.components)
        rows += (f'<tr><td class="id">{html.escape(dish.dish_id)}</td>'
                 f'<td class="dish">{html.escape(dish.dish_name)}</td><td>{chips}</td></tr>')
    return ('<table class="menu-table"><thead><tr><th class="id">ID</th><th class="dish">Dish</th>'
            f"<th>Components</th></tr></thead><tbody>{rows}</tbody></table>")


@st.cache_data
def components_table() -> pd.DataFrame:
    """Everything a cook can log. RAW-AT-SERVICE is a label, not a leftover."""
    components = pd.read_csv(DATA_DIR / "components.csv")
    return components[components.component_id != "RAW-AT-SERVICE"]


def leftovers_table() -> pd.DataFrame:
    """Unexpired batches from the sample log and the Log tab, counted from the latest close."""
    paths = [DATA_DIR / "leftover_log_sample.csv", LOG_FILE]
    logs = [pd.read_csv(path, na_filter=False).reindex(columns=LOG_FIELDS) for path in paths if path.exists()]
    log = pd.concat(logs, ignore_index=True).fillna({"note": ""})
    latest_close = pd.to_datetime(log.log_date).max()
    keys = ["component_id", "unit", "made_on", "expires_on", "note"]
    log = log.groupby(keys, as_index=False, sort=False).amount.sum()
    log["days_until_expired"] = (pd.to_datetime(log.expires_on) - latest_close).dt.days
    return log[log.days_until_expired > 0].merge(components_table(), on="component_id", how="left")


def save_log(entries: list) -> tuple[int, list]:
    """Add (component id, amount, made on, note) entries to the log.
    Returns how many were saved and the names of any that had already expired."""
    today = kitchen_today()
    components = components_table().set_index("component_id")
    rows, expired = [], []
    for component_id, amount, made_on, note in entries:
        item = components.loc[component_id]
        expires_on = made_on + dt.timedelta(days=int(item.default_shelf_life_days))
        if expires_on <= today:
            expired.append(item.component_name)
            continue
        rows.append({"log_date": today, "component_id": component_id, "amount": amount, "unit": item.count_unit,
                     "made_on": made_on, "expires_on": expires_on, "days_until_expired": (expires_on - today).days,
                     "note": note})
    if rows:
        pd.DataFrame(rows, columns=LOG_FIELDS).to_csv(LOG_FILE, mode="a", header=not LOG_FILE.exists(), index=False)
    return len(rows), expired


def day_count(days: float) -> str:
    return f'{int(days)} day{"" if days == 1 else "s"}'


def amount_text(amount: float, unit: str) -> str:
    plural = "s" if amount != 1 and unit in ("ball", "portion", "slice") else ""
    return f"{amount:,g} {unit}{plural}"


@st.dialog("Leftover details", width="medium")
def leftover_details(name: str, batches: pd.DataFrame) -> None:
    """One line per batch, oldest first."""
    st.subheader(name)
    rows = ""
    for batch in batches.sort_values("made_on").itertuples():
        rows += (f"<tr><td>{pd.Timestamp(batch.made_on):%b %-d, %Y}</td>"
                 f"<td>{amount_text(batch.amount, batch.unit)}</td>"
                 f"<td>{day_count(batch.days_until_expired)}</td><td>{html.escape(batch.note)}</td></tr>")
    st.html('<table class="menu-table"><thead><tr><th>Date made</th><th>Amount left</th><th>Days left</th>'
            '<th>Note</th></tr></thead>'
            f"<tbody>{rows}</tbody></table>")


def leftover_rows(items: pd.DataFrame, form: str) -> None:
    """One row per ingredient, adding up its batches. Clicking the ingredient opens the batches."""
    with st.container(key=f"leftover-head-{form}"):
        for col, label in zip(st.columns(LEFTOVER_COLUMNS), ["Ingredient", "Amount", "Default shelf life"]):
            col.html(f'<div class="leftover-head">{label}</div>')
    for component_id, batches in items.groupby("component_id", sort=False):
        item = batches.iloc[0]
        with st.container(key=f"leftover-row-{component_id}"):
            name, amount, shelf, _ = st.columns(LEFTOVER_COLUMNS, vertical_alignment="center")
            if name.button(item.component_name, key=f"open-{component_id}", type="tertiary"):
                leftover_details(item.component_name, batches)
            amount.write(amount_text(batches.amount.sum(), item.unit))
            shelf.write(day_count(item.default_shelf_life_days))


def all_closes() -> pd.DataFrame:
    """Amount left of each component at every close: sample history, sample log and the Log tab."""
    paths = [HISTORY_FILE, DATA_DIR / "leftover_log_sample.csv", LOG_FILE]
    logs = [pd.read_csv(path, usecols=["log_date", "component_id", "amount", "unit"]) for path in paths if path.exists()]
    closes = pd.concat(logs, ignore_index=True).groupby(["log_date", "component_id", "unit"], as_index=False).amount.sum()
    return closes.assign(log_date=pd.to_datetime(closes.log_date))


def prep_less(closes: pd.DataFrame, weeks: int, service_day: pd.Timestamp) -> list:
    """Components left over again and again, on the service day's weekday or across the whole period."""
    latest = closes.log_date.max()
    window = closes[closes.log_date > latest - pd.Timedelta(weeks=weeks)]
    dates = window.log_date.drop_duplicates()
    same_day = dates[dates.dt.dayofweek == service_day.dayofweek]
    names = components_table().set_index("component_id").component_name
    calendar = pd.date_range(end=latest, periods=weeks * 7)
    day = f"{service_day:%A}s"
    rows = []
    for (component_id, unit), history in window.groupby(["component_id", "unit"]):
        on_day = history[history.log_date.dt.dayofweek == service_day.dayofweek]
        if len(same_day) >= 2 and len(on_day) / len(same_day) >= 0.75:
            seen, pattern, when = on_day, f"{len(on_day)} of the last {len(same_day)} {day}", f"on {day}"
            rate = 1 + len(on_day) / len(same_day)   # weekday patterns list first
        elif len(history) / len(dates) >= 0.7:
            seen, pattern, when = history, f"{len(history)} of the last {len(dates)} days", "each day"
            rate = len(history) / len(dates)
        else:
            continue
        least = seen.amount.min()   # always had at least this much spare
        cut = least // 50 * 50 if unit in ("g", "ml") and least >= 50 else least
        amounts = history.set_index("log_date").amount
        rows.append({"name": names[component_id], "pattern": pattern, "cut": amount_text(cut, unit), "when": when,
                     "typical": amount_text(round(seen.amount.median()), unit), "rate": rate,
                     "days": [(date, amount_text(amounts[date], unit) if date in amounts.index else None)
                              for date in calendar]})
    return sorted(rows, key=lambda row: row["rate"], reverse=True)


@st.cache_data
def dish_parts() -> pd.DataFrame:
    """Each dish's components and how much one portion uses. Two-size dishes use the large size."""
    menu = pd.read_csv(DATA_DIR / "menu_setup.csv").drop_duplicates("base_dish_id", keep="last")
    links = pd.read_csv(DATA_DIR / "dish_components.csv")
    lines = pd.read_csv(DATA_DIR / "elio_volpe_dinner_ingredients.csv").merge(
        pd.read_csv(DATA_DIR / "ingredient_forms.csv"), on=["dish_id", "ingredient"])
    lines = lines.merge(components_table()[["component_id", "count_unit"]], on="component_id")
    lines = lines[lines.unit == lines.count_unit]
    per_portion = lines.groupby(["dish_id", "component_id"], as_index=False).quantity_per_portion.sum()
    parts = menu.merge(links, on="dish_id").merge(per_portion, on=["dish_id", "component_id"], how="left")
    # No matching unit means the component is counted in portions, like 1 dough ball per pizza.
    return parts.assign(per_portion=parts.quantity_per_portion.fillna(1))


def dish_ideas(priority: pd.DataFrame, stock: pd.DataFrame, skip: tuple = ()) -> list:
    """Dishes that use up the priority items, most urgent first. Items with fewer days left count for more."""
    days_left = priority.groupby("component_id").days_until_expired.min()
    on_hand = stock.groupby("component_id").amount.sum()
    names = components_table().set_index("component_id").component_name
    ideas = []
    for dish, parts in dish_parts().groupby("dish_name", sort=False):
        used = parts[parts.component_id.isin(days_left.index)]
        have = parts[parts.component_id.isin(on_hand.index)]
        portions = int((have.component_id.map(on_hand) / have.per_portion).min()) if len(have) else 0
        mains = parts[parts.role.isin(MAIN_ROLES)]
        if dish in skip or used.empty or portions < 1 or not mains.component_id.isin(on_hand.index).all():
            continue
        ideas.append({
            "dish": dish, "portions": portions, "score": sum(1 / days_left[c] for c in used.component_id),
            "use": [f"{names[c]} · {day_count(days_left[c])}" for c in used.component_id],
            "also": [names[c] for c in have.component_id if c not in days_left.index],
            "need": [names[c] for c in parts.component_id if c not in on_hand.index]})
    return sorted(ideas, key=lambda idea: (idea["score"], idea["portions"]), reverse=True)


@st.cache_data
def dish_prices() -> pd.Series:
    """Listed price by dish, taking the large size. Market-price dishes have none."""
    prices = pd.read_csv(PRICE_FILE, encoding="utf-8-sig").groupby("dish_name").price_cad.max().dropna()
    return prices.rename(index=PRICE_NAMES)


def chips(names: list) -> str:
    return "".join(f'<span class="menu-chip">{html.escape(name)}</span>' for name in names)


def idea_card(idea: dict, tag: str = "", special: bool = False) -> str:
    portions = f'{idea["portions"]} portion{"" if idea["portions"] == 1 else "s"}'
    parts = [f'<div class="card{" special" if special else ""}">']
    if tag:
        parts.append(f'<div class="card-tag">{tag}</div>')
    parts.append(f'<div class="idea-title">{html.escape(idea["dish"])}</div>')
    price = dish_prices().get(idea["dish"])
    if special and price:
        parts.append(f'<div class="card-sales">${price * idea["portions"]:,.0f}</div>'
                     f'<div>in menu sales if all {portions} sell at ${price:g}</div>')
    else:
        parts.append(f"<div>Makes about {portions} from what is on hand</div>")
    for label, names in [("Uses up", idea["use"]), ("Also on hand", idea["also"]), ("Still needs", idea["need"])]:
        if names:
            parts.append(f'<div class="idea-label">{label}</div>{chips(names)}')
    return "".join(parts) + "</div>"


def repeats_html(repeats: list, service_day: pd.Timestamp) -> str:
    """Each item with its advice and a strip of squares, one per day of the period."""
    rows = ""
    for row in repeats:
        cells = ""
        for date, amount in row["days"]:
            kind = "" if amount is None else "focus" if date.dayofweek == service_day.dayofweek else "hit"
            cells += f'<span class="{kind}" title="{date:%a, %b %-d}: {amount or "nothing left"}"></span>'
        rows += (f'<div class="repeat"><div class="repeat-text"><div class="repeat-name">{html.escape(row["name"])}</div>'
                 f'<div class="repeat-cut">−{row["cut"]} {row["when"]}</div>'
                 f'<div class="repeat-why">Left over {row["pattern"]}, typically {row["typical"]}</div></div>'
                 f'<div class="strip">{cells}</div></div>')
    first, last = repeats[0]["days"][0][0], repeats[0]["days"][-1][0]
    key = (f'<div class="strip-key"><div>{first:%b %-d} to {last:%b %-d}, one square per day:</div>'
           f'<div><span class="focus"></span>Left over on a {service_day:%A}</div>'
           '<div><span class="hit"></span>Left over on another day</div><div><span></span>Nothing left</div></div>')
    return f'{key}<div class="repeat-list">{rows}</div>'


def going_bad_html(items: pd.DataFrame) -> str:
    """Scrollable table, sectioned by form, soonest first within each section."""
    rows = ""
    for form, name in FORM_NAMES.items():
        section = items[items.form == form].sort_values("days_until_expired", kind="stable")
        if section.empty:
            continue
        rows += f'<tr class="group"><td colspan="3">{name}</td></tr>'
        for item in section.itertuples():
            rows += (f"<tr><td>{html.escape(item.component_name)}</td><td>{amount_text(item.amount, item.unit)}</td>"
                     f'<td class="{"urgent" if item.days_until_expired == 1 else ""}">'
                     f"{day_count(item.days_until_expired)}</td></tr>")
    return ('<div class="scroll-table"><table class="menu-table"><thead><tr><th>Ingredient</th><th>Amount</th>'
            f"<th>Days left</th></tr></thead><tbody>{rows}</tbody></table></div>")

def search_links(terms: list) -> list:
    """Recipe search pages for the chosen ingredients."""
    q = quote_plus(" ".join(terms))
    return [("Google", f"https://www.google.com/search?q={q}+recipe"),
            ("BBC Good Food", f"https://www.bbcgoodfood.com/search?q={q}"),
            ("Allrecipes", f"https://www.allrecipes.com/search?q={q}")]

def log_key(kind: str, component_id: str, line: int) -> str:
    """Widget key for one entry. A new version after each submit gives empty boxes."""
    return f"log-{kind}-{S['log_version']}-{component_id}-{line}"


def add_log_line(component_id: str) -> None:
    lines = S["log_lines"].setdefault(component_id, [0])
    lines.append(lines[-1] + 1)


def remove_log_line(component_id: str, line: int) -> None:
    S["log_lines"][component_id].remove(line)


def submit_log() -> None:
    entries, no_amount = [], []
    for item in components_table().itertuples():
        for line in S["log_lines"].get(item.component_id, [0]):
            amount = S.get(log_key("amount", item.component_id, line))
            note = (S.get(log_key("note", item.component_id, line)) or "").strip()
            if amount:
                entries.append((item.component_id, amount, S[log_key("made", item.component_id, line)], note))
            elif note:
                no_amount.append(item.component_name)
    if no_amount:   # keep everything on screen so the cook can fill in the amount
        S["log_status"] = [("warning", f"Add an amount for the note on: {', '.join(no_amount)}. Nothing was logged.")]
        return
    if not entries:
        S["log_status"] = [("warning", "Enter at least one amount before submitting.")]
        return
    saved, expired = save_log(entries)
    S["log_status"] = []
    if saved:
        S["log_status"].append(("success", f"Logged {saved} entr{'y' if saved == 1 else 'ies'}. The Leftovers tab is updated."))
    if expired:
        S["log_status"].append(("warning", f"Not logged, already past shelf life: {', '.join(expired)}."))
    S["log_version"] += 1
    S["log_lines"] = {}


def log_rows(items: pd.DataFrame, form: str) -> None:
    """One line per entry. An ingredient starts with one line and can add more for other dates."""
    with st.container(key=f"leftover-head-log-{form}"):
        labels = ["Ingredient", "Amount", "", "Made on", "Note", ""]
        for col, label in zip(st.columns(LOG_COLUMNS), labels):
            col.html(f'<div class="leftover-head">{label}</div>')
    today = kitchen_today()
    for item in items.itertuples():
        component_id = item.component_id
        lines = S["log_lines"].get(component_id, [0])
        with st.container(key=f"leftover-row-log-{component_id}"):
            for line in lines:
                name, box, unit, made, note, action = st.columns(LOG_COLUMNS, vertical_alignment="center")
                if line == lines[0]:
                    name.html(f'<div class="log-name">{html.escape(item.component_name)}</div>')
                    action.button("+ Add date", key=log_key("add", component_id, line), type="tertiary",
                                  on_click=add_log_line, args=(component_id,))
                else:
                    action.button("Remove", key=log_key("remove", component_id, line), type="tertiary",
                                  on_click=remove_log_line, args=(component_id, line))
                box.number_input(f"Amount of {item.component_name}", min_value=0, value=None, step=1,
                                 key=log_key("amount", component_id, line), label_visibility="collapsed")
                unit.write(item.count_unit)
                made.date_input(f"Date {item.component_name} was made", value=today, max_value=today,
                                key=log_key("made", component_id, line), label_visibility="collapsed")
                note.text_input(f"Note for {item.component_name}", placeholder="Add a note",
                                key=log_key("note", component_id, line), label_visibility="collapsed")


S.setdefault("log_version", 0)
S.setdefault("log_lines", {})
S.setdefault("recipe_hits", None)

st.markdown(MENU_CSS, unsafe_allow_html=True)
st.title("Tomorrow's Plate")

tab_home, tab_menu, tab_leftovers, tab_log, tab_recipes = st.tabs(["Home", "Menu", "Leftovers", "Log", "Recipes"])

with tab_home:
    stock = leftovers_table()
    closes = all_closes()
    latest_close = closes.log_date.max()
    service_day = latest_close + pd.Timedelta(days=1)
    st.caption(f"Based on the {latest_close:%A, %b %-d} close. Planning for {service_day:%A, %b %-d}.")

    urgent = stock[stock.days_until_expired <= URGENT_DAYS]
    later = stock[stock.days_until_expired > URGENT_DAYS]
    staff_meals = dish_ideas(urgent, stock)
    specials = dish_ideas(later, stock, skip=tuple(idea["dish"] for idea in staff_meals[:1]))
    specials.sort(key=lambda idea: (idea["score"], dish_prices().get(idea["dish"], 0) * idea["portions"]), reverse=True)

    special_col, prep_col = st.columns([5, 7], gap="medium")
    with special_col, st.container(key="home-feature-special"):
        st.subheader("Daily special")
        if specials:
            st.caption(f"Sell through items with more than {URGENT_DAYS} days left.")
            st.html('<div class="card-row">' + "".join(idea_card(idea, special=True) for idea in specials[:4]) + "</div>")
        else:
            st.info(f"Nothing with more than {URGENT_DAYS} days left suits a special.")

    with prep_col, st.container(key="home-feature-prep"):
        st.subheader("Prep less")
        weeks = st.selectbox("Look back", [2, 3, 4], index=2, format_func=lambda n: f"Last {n} weeks", width=200)
        repeats = prep_less(closes, weeks, service_day)[:6]
        if repeats:
            st.html(repeats_html(repeats, service_day))
        else:
            st.info("No item has been left over often enough to flag.")

    going_bad, staff_meal = st.columns([5, 7], gap="medium")
    with going_bad:
        st.subheader("Going bad soon")
        chosen = st.multiselect("Ingredient forms", list(FORM_NAMES), format_func=FORM_NAMES.get,
                                placeholder="All forms", width=320, key="home-forms")
        shown = urgent[urgent.form.isin(chosen)] if chosen else urgent
        if shown.empty:
            st.info(f"Nothing here has {URGENT_DAYS} days or fewer left.")
        else:
            st.html(going_bad_html(shown))

    with staff_meal:
        st.subheader("Staff meal")
        if staff_meals:
            st.caption(f"{len(staff_meals[:5])} options from what is going bad soon. Scroll sideways to compare.")
            st.html('<div class="card-row">' + "".join(
                idea_card(idea, tag="Best match" if rank == 0 else f"Option {rank + 1}")
                for rank, idea in enumerate(staff_meals[:5])) + "</div>")
        else:
            st.info("No dish can be made from what is going bad soon.")

    st.caption("History before Nov 4 is simulated sample data, not real kitchen records. Recommendations are rule-based "
               "from your menu and logs, and portions are estimates. Sales use listed menu prices, large size.")

with tab_menu:
    menu = menu_table()
    chosen = st.multiselect("Menu sections", list(SECTION_NAMES), format_func=SECTION_NAMES.get,
                            placeholder="All sections", width=320)
    for section, name in SECTION_NAMES.items():
        if chosen and section not in chosen:   # nothing chosen means show every section
            continue
        st.subheader(name)
        st.html(section_html(menu[menu.section == section]))

with tab_leftovers:
    leftovers = leftovers_table()
    chosen = st.multiselect("Ingredient forms", list(FORM_NAMES), format_func=FORM_NAMES.get,
                            placeholder="All forms", width=320)
    for form, name in FORM_NAMES.items():
        if chosen and form not in chosen:   # nothing chosen means show every form
            continue
        st.subheader(name)
        leftover_rows(leftovers[leftovers.form == form], form)

with tab_log:
    components = components_table()
    chosen = st.multiselect("Ingredient forms", list(FORM_NAMES), format_func=FORM_NAMES.get,
                            placeholder="All forms", width=320, key="log-forms")
    st.button("Submit", type="primary", on_click=submit_log)
    for kind, message in S.pop("log_status", []):
        getattr(st, kind)(message)
    for form, name in FORM_NAMES.items():
        # Hidden, not skipped, so numbers already typed survive a change of filter.
        if chosen and form not in chosen:
            st.html(f"<style>.st-key-log-section-{form} {{ display: none; }}</style>")
        with st.container(key=f"log-section-{form}"):
            st.subheader(name)
            log_rows(components[components.form == form], form)

try:   # optional helpers from the earlier app; the Recipes tab works without them
    import recipes as rc
except ImportError:
    rc = None
try:
    import tomorrows_plate as tp   # only for the optional Claude call
except ImportError:
    tp = None

with tab_recipes:
    # What is logged and still within shelf life, the same data as the Leftovers tab
    on_hand = leftovers_table().sort_values(["days_until_expired", "component_name"], kind="stable")
    st.subheader("What is logged")
    if on_hand.empty:
        st.info("Nothing is logged yet. Add leftovers on the Log tab, then come back here.")
    else:
        st.caption("Everything logged and still within shelf life, soonest to expire first.")
        st.html(going_bad_html(on_hand))

    logged = on_hand.drop_duplicates("component_id").component_name.tolist()
    extras_text = st.text_input("Other leftover ingredients, comma separated", placeholder="cooked rice, roasted carrots",
                                help="For anything not on the Log tab. Used only for the recipe search.")
    extras = [x.strip() for x in extras_text.split(",") if x.strip()]
    cands = list(dict.fromkeys(logged + extras))

    st.markdown("#### Recipes for your leftovers")
    chosen = st.multiselect("Search using", cands, default=list(dict.fromkeys(logged[:3] + extras)),
                            key="recipe-terms-" + "|".join(cands),
                            help="Starts with the three logged items closest to expiring.")
    if rc is not None and st.button("Find recipes online", disabled=not chosen):
        with st.spinner("Searching..."):
            results, source_name = rc.find_recipes(chosen)
        S["recipe_hits"] = (tuple(chosen), results, source_name)

    hits = S["recipe_hits"]
    if hits:
        used, results, source_name = hits
        st.caption(f"Results for {', '.join(used)} · source: {source_name}")
        if not results:
            st.info("No recipes matched. Try other ingredients or the search links below.")
        for r in results:
            with st.container(border=True):
                ic, tc = st.columns([1, 3])
                if r.get("thumb"):
                    ic.image(r["thumb"])
                tc.markdown(f"**[{r['title']}]({r['url']})**" if r.get("url") else f"**{r['title']}**")
                tc.caption(" · ".join(x for x in (r.get("site"), r.get("note")) if x))
                if r.get("uses"):
                    tc.markdown("Uses: " + ", ".join(r["uses"]))
                if r.get("ingredients") or r.get("instructions"):
                    with tc.expander("Ingredients and method"):
                        for n, q in r.get("ingredients", []):
                            st.markdown(f"- {q} {n}".strip())
                        if r.get("instructions"):
                            st.write(r["instructions"])

    links = search_links(chosen or cands) if (chosen or cands) else []
    if links:
        st.markdown("#### Search more")
        for col, (name, url) in zip(st.columns(len(links)), links):
            col.link_button(name, url)
    st.caption("Check shelf life and reheat stored food to 74 °C (165 °F) before serving.")

    if tp is not None and os.getenv("ANTHROPIC_API_KEY") and not on_hand.empty:
        if st.button("Suggest staff meals with Claude"):
            totals = (on_hand.groupby(["component_name", "unit"], as_index=False)
                      .agg(amount=("amount", "sum"), days=("days_until_expired", "min")).sort_values("days"))
            lines = [f"{amount_text(t.amount, t.unit)} {t.component_name} ({day_count(t.days)} left)"
                     for t in totals.itertuples()]
            prompt = ("Suggest up to 3 staff-meal ideas for a restaurant kitchen team using only these logged leftovers "
                      f"plus basic pantry items: {'; '.join(lines)}. Other leftovers: {', '.join(extras) or 'none'}. "
                      "Use the items with the fewest days left first. For each idea give a short name, 3 or 4 lines "
                      "of method and the leftovers used. Mention reheating to 74 C. Plain text, under 220 words.")
            with st.spinner("Asking Claude..."):
                out = tp.llm(prompt, "You are a careful restaurant kitchen assistant.", 500)
            st.write(out or "Claude could not answer right now.")
            st.caption("Written by Claude from your logged leftovers. Not from a cookbook.")