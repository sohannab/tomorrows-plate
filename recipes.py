"""Recipe ideas for leftovers.

Live search uses TheMealDB's free JSON API (test key "1"). If the network or the API is unavailable,
the app falls back to CURATED, a short list of leftover recipes saved from web searches.
No Streamlit imports, so this can be tested with a fake `fetch`.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

API = "https://www.themealdb.com/api/json/v1/1/"

# Dish -> search terms. The first term is the one sent to TheMealDB by default; the others are extra
# tags for the saved list. Terms TheMealDB does not know simply return nothing.
TERMS = {
    "Wild Salmon Bowl": ["salmon", "fish"],
    "Braised Short Rib": ["beef", "short rib"],
    "Roasted Veg Grain Bowl": ["carrots", "roasted vegetables"],
    "Dungeness Crab Chowder": ["crab", "chowder"],
    "Miso Ginger Chicken": ["chicken"],
    "Mushroom Risotto": ["mushrooms", "risotto"],
    "Kale Caesar": ["kale", "salad"],
    "Maple Pork Belly": ["pork", "pork belly"],
}

# (title, site, url, tags, note). Titles and links come from web searches; notes restate the title only.
CURATED = [
    ("Leftover Short Ribs That Taste Even Better", "reluctantgourmet.com", "https://reluctantgourmet.com/leftover-short-ribs/", ["short rib", "beef"], "Ideas for reheating and reusing leftover short ribs."),
    ("Make braised short ribs, then turn the leftovers into pasta sauce", "today.com", "https://www.today.com/today/amp/tdna243485", ["short rib", "beef", "pasta"], "Turns leftover braised short rib into a pasta sauce."),
    ("Short Rib Stew with Paprika Sour Cream", "williams-sonoma.com", "https://www.williams-sonoma.com/recipe/short-rib-stew.html?print=true", ["short rib", "beef", "stew"], "A stew built around short rib."),
    ("Leftover Salmon Cakes", "littlebroken.com", "https://www.littlebroken.com/salmon-quinoa-cakes/", ["salmon", "fish", "quinoa", "grain"], "Salmon and quinoa cakes made from cooked salmon."),
    ("Easy Salmon Cakes (With Leftover Salmon)", "feedingtinybellies.com", "https://feedingtinybellies.com/salmon-cakes/", ["salmon", "fish"], "Salmon cakes that start from leftover cooked salmon."),
    ("15 Best Leftover Salmon Recipes to Make Dinner Easy", "izzycooking.com", "https://izzycooking.com/?p=24642", ["salmon", "fish"], "A round-up of ways to use cooked salmon."),
    ("Arancini", "lovefoodhatewaste.com", "https://www.lovefoodhatewaste.com/recipe/arancini", ["risotto", "rice", "mushrooms"], "Arancini, a classic use for leftover risotto."),
    ("How to make arancini balls with leftover risotto", "myfoodbook.com.au", "https://myfoodbook.com.au/node/57226", ["risotto", "rice"], "Arancini balls from leftover risotto."),
    ("Leftover Risotto Arancini", "instantpot.com.au", "https://www.instantpot.com.au/blogs/recipes/leftover-risotto-arancini", ["risotto", "rice"], "A leftover risotto arancini recipe."),
    ("Roasted Vegetable Frittata", "nourishedbynutrition.com", "https://nourishedbynutrition.com/roasted-vegetable-frittata/", ["roasted vegetables", "carrots", "eggs"], "A frittata for leftover roasted vegetables."),
    ("7 Ways to Use Leftover Roasted Vegetables", "themom100.com", "https://themom100.com/leftover-roasted-vegetables", ["roasted vegetables", "carrots"], "Seven ideas for roasted vegetables."),
    ("Roasted Vegetable Grain Bowl", "bmc.org", "https://bmc.org/recipes/roasted-vegetable-grain-bowl", ["roasted vegetables", "carrots", "grain", "rice"], "A grain bowl built on roasted vegetables."),
    ("Leftovers Frittata", "purewow.com", "https://www.purewow.com/recipes/leftovers-frittata", ["eggs", "roasted vegetables", "cheese"], "A catch-all frittata for odds and ends."),
    ("Clean-out-the-fridge Grain Bowl", "kroger.com", "https://www.kroger.com/r/clean-out-fridge-grain-bowl-recipe/3c49d3fc-dd8a-47fd-a7d7-caf6f942f71a", ["grain", "rice", "carrots", "chicken"], "A grain bowl for whatever is in the fridge."),
    ("Pork Belly Fried Rice", "pinchandswirl.com", "https://pinchandswirl.com/pork-belly-fried-rice/", ["pork belly", "pork", "rice", "eggs"], "Fried rice using pork belly."),
    ("Pork Belly Fried Rice", "summeryule.com", "https://summeryule.com/pork-belly-fried-rice/", ["pork belly", "pork", "rice"], "Another take on pork belly fried rice."),
    ("Pork Belly Ramen", "taste.co.za", "https://taste.co.za/recipes/pork-belly-ramen/", ["pork belly", "pork", "noodles"], "Ramen topped with pork belly."),
    ("Leftover Chicken Recipes", "spendwithpennies.com", "https://www.spendwithpennies.com/leftover-chicken-recipes/", ["chicken"], "A collection of ways to use cooked chicken."),
    ("Quick and Easy Leftover Chicken Quesadillas", "gimmedelicious.com", "https://gimmedelicious.com/quick-and-easy-leftover-chicken-quesadillas/", ["chicken", "cheese"], "Quesadillas from cooked chicken."),
    ("Eight Ways to Use Up Leftover Chicken", "frugalfamily.co.uk", "https://www.frugalfamily.co.uk/eight-ways-to-use-up-leftover-chicken/", ["chicken"], "Eight ideas for cooked chicken."),
]

SEARCH_SITES = [
    ("AllRecipes", "https://www.allrecipes.com/search?q={q}"),
    ("Serious Eats", "https://www.seriouseats.com/search?q={q}"),
    ("Food Network", "https://www.foodnetwork.com/search/{q}-"),
    ("Epicurious", "https://www.epicurious.com/search?q={q}"),
]


class Offline(Exception):
    """The recipe API could not be reached."""


def _get(url: str, timeout: float = 6):
    req = urllib.request.Request(url, headers={"User-Agent": "TomorrowsPlate/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _norm(term: str) -> str:
    return re.sub(r"\s+", "_", term.strip().lower())


# ----------------------------------------------------------------------------- TheMealDB

def by_ingredient(term: str, fetch=_get) -> list[dict]:
    data = fetch(API + "filter.php?i=" + urllib.parse.quote(_norm(term)))
    meals = data.get("meals") if isinstance(data, dict) else None
    if not isinstance(meals, list):
        return []
    return [{"id": m.get("idMeal"), "title": m.get("strMeal", ""), "thumb": m.get("strMealThumb", "")}
            for m in meals if isinstance(m, dict) and m.get("idMeal")]


def detail(meal_id, fetch=_get) -> dict | None:
    data = fetch(API + "lookup.php?i=" + urllib.parse.quote(str(meal_id)))
    meals = data.get("meals") if isinstance(data, dict) else None
    if not isinstance(meals, list) or not meals or not isinstance(meals[0], dict):
        return None
    m = meals[0]
    ings = []
    for i in range(1, 21):
        name = (m.get(f"strIngredient{i}") or "").strip()
        if name:
            ings.append((name, (m.get(f"strMeasure{i}") or "").strip()))
    return {"title": m.get("strMeal", ""), "site": "TheMealDB", "url": (m.get("strSource") or "").strip(),
            "thumb": m.get("strMealThumb", ""), "note": " · ".join(x for x in (m.get("strArea"), m.get("strCategory")) if x),
            "ingredients": ings, "instructions": (m.get("strInstructions") or "").strip(),
            "video": (m.get("strYoutube") or "").strip()}


def search_live(terms, limit: int = 6, fetch=_get) -> list[dict]:
    """Meals that use the most of your leftover ingredients. Raises Offline if the API cannot be reached."""
    terms = [t for t in dict.fromkeys(t.strip().lower() for t in terms) if t][:6]
    hits: dict = {}
    answered = 0
    for t in terms:
        try:
            found = by_ingredient(t, fetch)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            if answered == 0:
                raise Offline("recipe API unreachable")
            continue
        answered += 1
        for m in found[:60]:
            h = hits.setdefault(m["id"], {"meal": m, "terms": set()})
            h["terms"].add(t)
    if terms and answered == 0:
        raise Offline("recipe API unreachable")
    ranked = sorted(hits.values(), key=lambda h: (-len(h["terms"]), h["meal"]["title"]))[:limit]
    out = []
    for h in ranked:
        try:
            d = detail(h["meal"]["id"], fetch)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            d = None
        d = d or {"title": h["meal"]["title"], "site": "TheMealDB", "url": "", "thumb": h["meal"]["thumb"],
                  "note": "", "ingredients": [], "instructions": "", "video": ""}
        names = [n.lower() for n, _ in d["ingredients"]]
        uses = set(h["terms"])
        for t in terms:
            if any(t in n or n in t for n in names):
                uses.add(t)
        d["uses"] = sorted(uses)
        out.append(d)
    out.sort(key=lambda r: -len(r["uses"]))
    return out


# ----------------------------------------------------------------------------- saved list

def search_curated(terms, limit: int = 6) -> list[dict]:
    terms = [t.strip().lower() for t in terms if t.strip()]
    scored = []
    for title, site, url, tags, note in CURATED:
        uses = sorted({t for t in terms for g in tags if t in g or g in t})
        if uses:
            scored.append((len(uses), title, {"title": title, "site": site, "url": url, "thumb": "", "note": note,
                                              "ingredients": [], "instructions": "", "video": "", "uses": uses}))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [s[2] for s in scored[:limit]]


def find_recipes(terms, limit: int = 6, fetch=_get) -> tuple[list[dict], str]:
    """-> (results, source). Source says where the results came from, so the UI can show it."""
    try:
        live = search_live(terms, limit, fetch)
        if live:
            return live, "TheMealDB"
        return search_curated(terms, limit), "saved list (TheMealDB had no match)"
    except Offline:
        return search_curated(terms, limit), "saved list (live search unavailable)"


# ----------------------------------------------------------------------------- helpers for the UI

def suggest_terms(staff_dishes, expiring_dishes, extras) -> list[str]:
    """Search terms in priority order: staff-meal dishes, then dishes that expire, then your own extras,
    then each dish's secondary tags."""
    out, secondary = [], []
    for name in list(staff_dishes) + list(expiring_dishes):
        ts = TERMS.get(name, [])
        if ts:
            out.append(ts[0]); secondary += ts[1:]
    out += [e.strip().lower() for e in extras if e.strip()]
    out += secondary
    return list(dict.fromkeys(out))


def search_links(terms) -> list[tuple[str, str]]:
    q = urllib.parse.quote_plus((" ".join(terms[:3]) or "staff meal") + " leftover recipe")
    return [(name, pat.format(q=q)) for name, pat in SEARCH_SITES]
