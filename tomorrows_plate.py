"""
Tomorrow's Plate - an AI agent that plans tomorrow's prep around tonight's leftovers.

Pipeline (one full cycle)
  1. Voice check-in text  -> structured leftover log            (parse_leftover_transcript)
  2. Demand forecast + uncertainty scenarios                    (DemandForecaster, scikit-learn)
  3. Two-stage stochastic MILP: prep quantities + staff meal    (optimize_plan, Gurobi or HiGHS)
  4. Plain-language explanation of every decision               (explain_plan, optional LLM polish)
  5. Chef change request -> re-plan -> diff of what changed     (parse_change_request, replan, diff_plans)
  6. Backtest: agent vs. usual par-level prep, by business type (backtest, run_sector_study)

Design rule for the LLM: it may NAME a staff meal, PARSE a free-text request and POLISH wording.
It never sets quantities or shelf life - the optimizer and food-safety rules own those numbers.

AI attribution: this code was drafted with the assistance of Claude (Anthropic) and reviewed/run by the author.
All data here is SIMULATED (patterns modelled on the Food Demand Forecasting dataset's drivers:
promotion email, homepage feature, price ratio). Use panel_from_food_demand() to plug in the real CSVs.

Usage:  python tomorrows_plate.py demo | backtest | sectors | all
"""
from __future__ import annotations

import contextlib
import difflib
import math
import os
import re
import sys
import warnings
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.ensemble import HistGradientBoostingRegressor

warnings.filterwarnings("ignore")

# --------------------------------------------------------------------------------------
# 1. Menu and parameters
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Dish:
    name: str
    price: float          # menu price per portion (CAD)
    cost: float           # ingredient cost per portion
    prep_min: float       # cook minutes per portion (batch labour)
    batch: int            # prep happens in multiples of this many portions
    shelf_life: int       # max age in days (0 = day prepped) at which it may still be served
    base_demand: float    # average portions/day
    rain_sens: float = 1.0  # multiplier on rainy days
    staff_ok: bool = True   # may be used in the staff meal


# Elio Volpe dinner menu (eliovolpe.com/menu-dinner). Names match elio_volpe_dinner_ingredients.csv.
# Only the names and listed prices are real. Everything else is a planning assumption to replace with
# kitchen and sales data: cost, cook minutes, batch size, shelf life, demand, rain effect, staff use.
FOOD_COST_SHARE = 0.30  # assumed ingredient cost as a share of menu price
SHELF_LIFE_DAYS = 1     # applied to every dish; replaces the shelf_life column in the table below

_ELIO_MENU = [
    # name, price, prep_min, batch, shelf_life, base_demand, rain_sens, staff_ok
    ("House baked puccia",               8.0, 0.8, 6, 1, 20, 1.00, True),
    ("Cerignola olives",                11.0, 0.2, 6, 5,  8, 1.00, True),
    ("Oyama fennel salami",             20.0, 0.5, 4, 3,  7, 1.00, True),
    ("Baccala mantecato",               24.0, 1.5, 4, 2,  7, 1.05, True),
    ("Scallop crudo",                   32.0, 1.2, 2, 0,  8, 0.90, False),
    ("Arancini",                        19.5, 1.5, 6, 2, 12, 1.10, True),   # average of 13 and 26
    ("Semolina parker house rolls",     18.0, 1.5, 6, 1,  9, 1.10, True),
    ("Meatballs",                       23.0, 1.8, 6, 3, 14, 1.15, True),
    ("Seared scallops",                 36.0, 1.5, 2, 0,  7, 1.00, False),
    ("Glorious greens",                 26.0, 0.8, 4, 0,  7, 0.90, True),
    ("Heirloom tomato",                 29.0, 0.8, 2, 0,  6, 0.85, True),
    ("Fall chicories",                  28.0, 1.0, 4, 1,  8, 1.00, True),
    ("Grilled broccolini",              18.0, 0.8, 4, 1,  9, 1.00, True),
    ("Margherita",                      23.0, 1.0, 6, 1, 14, 1.05, True),
    ("Primavera",                       30.0, 1.2, 4, 1,  9, 1.05, True),
    ("Roasted mushroom",                32.0, 1.3, 4, 1, 10, 1.10, True),
    ("Manila clam",                     30.0, 1.5, 2, 0,  6, 1.00, False),
    ("Pepperone",                       33.0, 1.1, 4, 1, 11, 1.10, True),
    ("Capocollo",                       31.0, 1.1, 4, 1,  8, 1.05, True),
    ("Spaghetti alle vongole",          41.5, 2.2, 2, 0,  9, 1.00, False),  # average of 35 and 48
    ("Calabreselli alla vodka",         35.5, 2.0, 4, 1, 13, 1.10, True),   # average of 29 and 42
    ("Rigatoni cacio e pepe",           35.5, 2.0, 4, 1, 12, 1.10, True),   # average of 29 and 42
    ("Risotto",                         66.5, 3.0, 2, 1,  7, 1.10, False),  # average of 54 and 79
    ("Stracci",                         49.0, 2.5, 4, 3,  9, 1.20, True),
    ("Iberico pork chop",               62.0, 2.5, 2, 1,  5, 1.05, False),  # market price: placeholder
    ("Pollo al mattone",                39.0, 2.5, 4, 2, 11, 1.10, True),
    ("Wagyu zabuton steak",             88.0, 2.5, 2, 1,  5, 1.05, False),  # market price: placeholder
    ("Chargrilled octopus",             38.0, 3.0, 2, 2,  7, 0.95, True),
    ("Whole branzino",                  58.0, 3.0, 2, 0,  6, 0.95, False),  # market price: placeholder
    ("Tiramisu cheesecake",             16.0, 1.0, 8, 3,  9, 1.00, True),
    ("Torta al cioccolato fondente",    16.0, 1.0, 8, 3,  8, 1.05, True),
    ("Cassis and blackberry semifreddo", 16.0, 1.0, 8, 5, 6, 0.95, True),
    ("Spiced apple torta",              16.0, 1.2, 8, 2,  6, 1.05, True),
    ("Gelato, daily flavour",           11.0, 0.5, 4, 5,  8, 0.85, True),
    ("Sole Mio",                        12.0, 0.5, 4, 5,  5, 0.85, True),
]

MENU = [Dish(n, price, round(price * FOOD_COST_SHARE, 2), mins, batch, SHELF_LIFE_DAYS, demand, rain, staff)
        for n, price, mins, batch, _shelf, demand, rain, staff in _ELIO_MENU]

DOW_PROFILE = np.array([0.80, 0.85, 0.95, 1.05, 1.30, 1.35, 0.70])  # Mon..Sun, mean 1.0


@dataclass
class Config:
    n_scenarios: int = 100        # 100 keeps the MILP under Gurobi's free size-limited licence
    hold_frac: float = 0.10       # cost of carrying unsold fresh stock (risk it spoils later), x ingredient cost
    waste_pen: float = 0.25       # disposal/sustainability penalty on wasted portions, x ingredient cost
    lost_sale_pen: float = 2.0    # SERVICE-LEVEL DIAL: cost of an unmet order, x price (lost guest, reviews, repeat visits)
    staff_value: float = 7.0      # value of one staff-meal portion (replaces a bought/allowance meal)
    prep_cap_min: float = 1200.0  # total cook minutes available per day (chef can tighten it)
    baseline_par_buffer: float = 1.15  # "usual" par = 4-week same-weekday average x this buffer
    baseline_staff_recovery: float = 0.25  # share of expiring leftovers a normal kitchen uses ad hoc
    seed: int = 7


# --------------------------------------------------------------------------------------
# 2. Data: simulated panel modelled on the Food Demand Forecasting drivers
# --------------------------------------------------------------------------------------


def simulate_panel(menu=MENU, start="2024-10-01", end="2026-11-03", noise=0.12,
                   scale=1.0, seed=7) -> pd.DataFrame:
    """Daily demand per dish. Drivers mirror the Kaggle dataset: weekly promo email, homepage
    feature, discount (price ratio). Adds weekday, season, trend, and Vancouver rain."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, end, freq="D")
    rain = rng.random(len(dates)) < np.where(dates.month.isin([10, 11, 12, 1, 2, 3]), 0.55, 0.25)
    rows = []
    weeks = dates.to_period("W-SUN")
    for d_i, dish in enumerate(menu):
        wk_promo = {w: rng.random() < 0.18 for w in weeks.unique()}
        wk_feat = {w: rng.random() < 0.15 for w in weeks.unique()}
        for t, dt in enumerate(dates):
            promo, feat = wk_promo[weeks[t]], wk_feat[weeks[t]]
            price_ratio = 0.90 if promo else 1.0
            season = 1 + 0.10 * math.sin(2 * math.pi * (dt.dayofyear - 80) / 365)
            trend = 1 + 0.00025 * t
            mu = (dish.base_demand * scale * DOW_PROFILE[dt.dayofweek] * season * trend
                  * (1.25 if promo else 1.0) * (1.15 if feat else 1.0) * price_ratio ** -1.5
                  * (dish.rain_sens if rain[t] else 1.0))
            mu *= rng.lognormal(0, noise)
            rows.append((dt, dish.name, d_i, rng.poisson(mu), int(promo), int(feat), price_ratio, int(rain[t])))
    df = pd.DataFrame(rows, columns=["date", "dish", "dish_id", "demand", "promo", "featured",
                                     "price_ratio", "rain"])
    return add_features(df)


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["dish_id", "date"]).copy()
    g = df.groupby("dish_id")["demand"]
    df["lag1"] = g.shift(1)
    df["lag7"] = g.shift(7)
    df["roll7"] = g.transform(lambda s: s.shift(1).rolling(7).mean())
    df["roll28"] = g.transform(lambda s: s.shift(1).rolling(28).mean())
    df["dow"] = df["date"].dt.dayofweek
    df["month"] = df["date"].dt.month
    return df.sort_values(["date", "dish_id"]).reset_index(drop=True)


def panel_from_food_demand(train_csv, meal_info_csv, center_id, menu=MENU,
                           start="2024-10-01", seed=7) -> pd.DataFrame:
    """Plug in the real Food Demand Forecasting CSVs (train.csv, meal_info.csv).
    Weekly num_orders for the `center_id`'s top meals are mapped onto our menu and spread to days
    with the weekday profile (the dataset is weekly; kitchens plan daily). Promo/feature/price
    ratio come straight from the data."""
    rng = np.random.default_rng(seed)
    tr = pd.read_csv(train_csv)
    tr = tr[tr.center_id == center_id]
    top = tr.groupby("meal_id").num_orders.sum().nlargest(len(menu)).index.tolist()
    tr = tr[tr.meal_id.isin(top)]
    mp = {m: menu[i] for i, m in enumerate(top)}
    scale = {m: mp[m].base_demand * 7 / tr[tr.meal_id == m].num_orders.mean() for m in top}
    t0 = pd.Timestamp(start)
    rows = []
    for r in tr.itertuples():
        wk0 = t0 + pd.Timedelta(weeks=int(r.week) - int(tr.week.min()))
        dish = mp[r.meal_id]
        tot = r.num_orders * scale[r.meal_id]
        split = rng.multinomial(max(int(round(tot)), 0), DOW_PROFILE / DOW_PROFILE.sum())
        for k in range(7):
            rows.append((wk0 + pd.Timedelta(days=k), dish.name, menu.index(dish), int(split[k]),
                         int(r.emailer_for_promotion), int(r.homepage_featured),
                         r.checkout_price / r.base_price, int(rng.random() < 0.4)))
    df = pd.DataFrame(rows, columns=["date", "dish", "dish_id", "demand", "promo", "featured",
                                     "price_ratio", "rain"])
    return add_features(df)


# --------------------------------------------------------------------------------------
# 3. Forecasting with uncertainty
# --------------------------------------------------------------------------------------

FEATS = ["dish_id", "dow", "month", "promo", "featured", "price_ratio", "rain",
         "lag1", "lag7", "roll7", "roll28"]


class DemandForecaster:
    """Gradient-boosted demand model + empirical relative-residual scenarios.
    Residuals come from a held-out recent window, so the spread is honest (not in-sample)."""

    def __init__(self, holdout_days=56, seed=7):
        self.holdout_days, self.seed = holdout_days, seed

    def _model(self):
        return HistGradientBoostingRegressor(max_iter=250, learning_rate=0.06, max_depth=5,
                                             categorical_features=[0], random_state=self.seed)

    def fit(self, panel: pd.DataFrame, cutoff) -> "DemandForecaster":
        cutoff = pd.Timestamp(cutoff)
        tr = panel[(panel.date < cutoff) & panel.demand.notna()].dropna(subset=FEATS)
        split = cutoff - pd.Timedelta(days=self.holdout_days)
        a, b = tr[tr.date < split], tr[tr.date >= split]
        m0 = self._model().fit(a[FEATS], a.demand)
        pred = np.maximum(m0.predict(b[FEATS]), 1.0)
        b = b.assign(rel=b.demand.values / pred - 1.0)
        self.resid = b.pivot(index="date", columns="dish_id", values="rel").dropna().values  # days x dishes
        self.model = self._model().fit(tr[FEATS], tr.demand)
        self.holdout_mape = float(np.mean(np.abs(b.demand.values - pred) / np.maximum(b.demand.values, 1)))
        return self

    def forecast(self, panel: pd.DataFrame, date) -> pd.DataFrame:
        day = panel[panel.date == pd.Timestamp(date)].sort_values("dish_id")
        out = day[["dish", "dish_id"]].copy()
        out["mean"] = np.maximum(self.model.predict(day[FEATS]), 0.0)
        return out.reset_index(drop=True)

    def scenarios(self, mean: np.ndarray, n: int, rng) -> np.ndarray:
        idx = rng.integers(0, len(self.resid), n)  # same day-shock across dishes -> correlated busy nights
        d = np.rint(mean[None, :] * (1 + self.resid[idx])).clip(0)
        return d


# --------------------------------------------------------------------------------------
# 4. Leftover log (voice check-in) and inventory helpers
# --------------------------------------------------------------------------------------

_NUM = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve "
                                   "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}


def _to_num(tok: str):
    tok = tok.lower()
    return int(tok) if tok.isdigit() else _NUM.get(tok)


def parse_leftover_transcript(text: str, menu=MENU) -> dict:
    """'Eight meatballs, six arancini from yesterday, three risotto.' -> inventory {dish: {age_tomorrow: qty}}.
    Anything logged tonight was prepped today (age 0 tonight -> 1 tomorrow); 'from yesterday' -> 2 tomorrow."""
    inv: dict = {}
    for clause in re.split(r"[,.;\n]| and then | also ", text):
        clause = clause.strip().lower()
        if not clause:
            continue
        qty = next((_to_num(t) for t in re.findall(r"[a-z0-9]+", clause) if _to_num(t) is not None), None)
        if qty is None:
            continue
        age = 1
        if "yesterday" in clause or "day before" in clause:
            age = 2
        m = re.search(r"(\w+) days? ago", clause)
        if m and _to_num(m.group(1)):
            age = 1 + _to_num(m.group(1))
        words = set(re.findall(r"[a-z]+", clause)) - {"portions", "portion", "of", "from", "yesterday", "left", "ago"}
        best, score = None, 0.0
        for d in menu:
            dw = set(re.findall(r"[a-z]+", d.name.lower()))
            s = len(words & dw) / len(dw) + max(
                (difflib.SequenceMatcher(None, w, x).ratio() for w in words for x in dw), default=0) * 0.25
            if s > score:
                best, score = d, s
        if best is not None and score >= 0.3:
            inv.setdefault(best.name, {})
            inv[best.name][age] = inv[best.name].get(age, 0) + qty
    return inv


def pools(inv_dish: dict | None, shelf_life: int):
    """-> (expiring_last_day, carry, already_expired). Ages are as of the service day."""
    inv_dish = inv_dish or {}
    E = sum(q for a, q in inv_dish.items() if a == shelf_life)
    C = sum(q for a, q in inv_dish.items() if a < shelf_life)
    X = sum(q for a, q in inv_dish.items() if a > shelf_life)
    return E, C, X


# --------------------------------------------------------------------------------------
# 5. The optimizer: two-stage stochastic MILP
# --------------------------------------------------------------------------------------


@dataclass
class Request:
    """A chef's change request, in structured form."""
    remove: set = field(default_factory=set)       # dish names 86'd for the day
    max_portions: dict = field(default_factory=dict)
    min_portions: dict = field(default_factory=dict)
    prep_cap_min: float | None = None
    staff_count: int | None = None
    text: str = ""


@contextlib.contextmanager
def _quiet():
    """Silence C-level stdout/stderr chatter from the solver library."""
    try:
        sys.stdout.flush(); sys.stderr.flush()
        o1, o2 = os.dup(1), os.dup(2)
        dn = os.open(os.devnull, os.O_WRONLY)
        os.dup2(dn, 1); os.dup2(dn, 2)
    except Exception:
        yield; return
    try:
        yield
    finally:
        os.dup2(o1, 1); os.dup2(o2, 2)
        for f in (o1, o2, dn): os.close(f)


def _solve(c, A, b, lb, ub, integrality):
    """Maximise c.x s.t. A x <= b. Gurobi if importable, else SciPy HiGHS."""
    try:
        import gurobipy as gp
        from gurobipy import GRB
        m = gp.Model()
        m.Params.OutputFlag = 0
        m.Params.TimeLimit = 20
        vt = np.where(integrality == 1, GRB.INTEGER, GRB.CONTINUOUS)
        x = m.addMVar(len(c), lb=lb, ub=ub, vtype=list(vt))
        m.addConstr(A @ x <= b)
        m.setObjective(c @ x, GRB.MAXIMIZE)
        m.optimize()
        if m.Status in (GRB.OPTIMAL, GRB.TIME_LIMIT) and m.SolCount:
            return x.X, m.ObjVal, "gurobi"
    except Exception:
        pass
    from scipy.optimize import Bounds, LinearConstraint, milp
    with _quiet():
        res = milp(-c, constraints=LinearConstraint(A, -np.inf, b), integrality=integrality,
                   bounds=Bounds(lb, ub), options={"time_limit": 20, "disp": False})
    if res.x is None:
        raise RuntimeError(f"MILP failed: {res.message}")
    return res.x, -res.fun, "highs"


@dataclass
class DishPlan:
    dish: Dish
    forecast: float
    p80: float
    usual_par: int
    prep: int
    expiring: int
    carry: int
    expired_on_arrival: int
    staff_expiring: int
    staff_carry: int
    exp_sales: float
    exp_waste: float
    p_stockout: float
    removed: bool = False
    driver: str = ""


@dataclass
class Plan:
    date: pd.Timestamp
    dishes: list
    staff_count: int
    prep_minutes: float
    objective: float
    solver: str
    request: Request | None = None
    staff_meal_name: str = ""

    def qty(self):
        return {d.dish.name: d.prep for d in self.dishes}


def usual_par(panel, dish_id, date, buffer, batch):
    h = panel[(panel.dish_id == dish_id) & (panel.date < date) & (panel.date.dt.dayofweek == date.dayofweek)
              & panel.demand.notna()].tail(4)
    base = h.demand.mean() if len(h) else 0
    return int(math.ceil(base * buffer / batch) * batch)


def optimize_plan(date, fc: pd.DataFrame, scen: np.ndarray, inventory: dict, staff_count: int,
                  cfg: Config, panel: pd.DataFrame, menu=MENU, request: Request | None = None,
                  prep_scale: float = 1.0) -> Plan:
    request = request or Request()
    date = pd.Timestamp(date)
    D, N = len(menu), scen.shape[0]
    cap = request.prep_cap_min if request.prep_cap_min is not None else cfg.prep_cap_min
    staff = request.staff_count if request.staff_count is not None else staff_count
    p = 1.0 / N

    # variable layout: k[D] | mE[D] | mC[D] | s[N*D] | w[N*D]
    iK, iE, iC = 0, D, 2 * D
    iS, iW = 3 * D, 3 * D + N * D
    nv = 3 * D + 2 * N * D
    c = np.zeros(nv)
    lb, ub = np.zeros(nv), np.zeros(nv)
    integ = np.zeros(nv)
    Ed, Cd, Xd = [], [], []
    for i, d in enumerate(menu):
        E, C, X = pools(inventory.get(d.name), d.shelf_life)
        Ed.append(E); Cd.append(C); Xd.append(X)
        removed = d.name in request.remove
        kmax = 0 if removed else int(math.ceil(max(scen[:, i].max() * 1.3, 8) * prep_scale / d.batch))
        if d.name in request.max_portions:
            kmax = min(kmax, request.max_portions[d.name] // d.batch)
        kmin = 0 if removed else int(math.ceil(request.min_portions.get(d.name, 0) / d.batch))
        kmax = max(kmax, kmin)
        lb[iK + i], ub[iK + i], integ[iK + i] = kmin, kmax, 1
        c[iK + i] = -d.cost * d.batch * (1 + cfg.hold_frac)
        for off, avail in ((iE, E), (iC, C)):
            ub[off + i] = avail if d.staff_ok else 0
            integ[off + i] = 1
            c[off + i] = cfg.staff_value + cfg.hold_frac * d.cost
        for w in range(N):
            j = iS + w * D + i
            ub[j] = 0 if removed else scen[w, i]
            c[j] = p * (d.price * (1 + cfg.lost_sale_pen) + cfg.hold_frac * d.cost)
            c[iW + w * D + i] = p * (cfg.hold_frac * d.cost - cfg.waste_pen * d.cost)
            ub[iW + w * D + i] = max(E, 0)

    rows, cols, vals, b = [], [], [], []
    r = 0

    def add(entries, rhs):
        nonlocal r
        for j, v in entries:
            rows.append(r); cols.append(j); vals.append(v)
        b.append(rhs); r += 1

    add([(iE + i, 1) for i in range(D)] + [(iC + i, 1) for i in range(D)], staff)          # staff portions
    add([(iK + i, menu[i].prep_min * menu[i].batch) for i in range(D)], cap)               # cook minutes
    for w in range(N):
        for i, d in enumerate(menu):
            s, wv = iS + w * D + i, iW + w * D + i
            add([(s, 1), (iE + i, 1), (iC + i, 1), (iK + i, -d.batch)], Ed[i] + Cd[i])     # can't sell > have
            add([(wv, -1), (iE + i, -1), (s, -1)], -Ed[i])                                 # waste >= exp - sold
    A = sparse.csr_matrix((vals, (rows, cols)), shape=(r, nv))
    x, obj, solver = _solve(c, A, np.array(b, float), lb, ub, integ)

    plans = []
    mean = fc["mean"].values
    for i, d in enumerate(menu):
        k = int(round(x[iK + i])); prep = k * d.batch
        mE, mC = int(round(x[iE + i])), int(round(x[iC + i]))
        s = x[iS + i::D][:N] if False else np.array([x[iS + w * D + i] for w in range(N)])
        wv = np.array([x[iW + w * D + i] for w in range(N)])
        avail = prep + Ed[i] + Cd[i] - mE - mC
        removed = d.name in request.remove
        plans.append(DishPlan(
            dish=d, forecast=float(mean[i]), p80=float(np.percentile(scen[:, i], 80)),
            usual_par=usual_par(panel, i, date, cfg.baseline_par_buffer, d.batch), prep=prep,
            expiring=Ed[i], carry=Cd[i], expired_on_arrival=Xd[i], staff_expiring=mE, staff_carry=mC,
            exp_sales=float(s.mean()), exp_waste=float(wv.mean()),
            p_stockout=0.0 if removed else float((scen[:, i] > avail).mean()), removed=removed,
            driver=demand_driver(panel, i, date)))
    mins = sum(pl.prep * pl.dish.prep_min for pl in plans)
    plan = Plan(date, plans, staff, mins, obj, solver, request)
    plan.staff_meal_name = name_staff_meal(plan)
    return plan


# --------------------------------------------------------------------------------------
# 6. Explanations, optional LLM, change requests, diffs
# --------------------------------------------------------------------------------------


def demand_driver(panel, dish_id, date) -> str:
    row = panel[(panel.dish_id == dish_id) & (panel.date == date)].iloc[0]
    hist = panel[(panel.dish_id == dish_id) & (panel.date < date) & panel.demand.notna()].tail(180)
    dow_ratio = hist[hist.dow == date.dayofweek].demand.mean() / max(hist.demand.mean(), 1e-9) - 1
    bits = [f"{date.strftime('%A')}s run {abs(dow_ratio):.0%} {'above' if dow_ratio > 0 else 'below'} this dish's weekly average"]
    if row.promo: bits.append("a promotion email is running")
    if row.featured: bits.append("it is featured on the homepage")
    if row.rain: bits.append("rain is forecast")
    return "; ".join(bits)


def llm(prompt: str, system: str, max_tokens=250):
    """Optional Claude call. Returns None without a key so the whole pipeline works offline."""
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
        r = anthropic.Anthropic(api_key=key).messages.create(
            model=os.getenv("TP_MODEL", "claude-sonnet-5-5"), max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": prompt}])
        return r.content[0].text.strip()
    except Exception:
        return None


def staff_meal_lines(plan: Plan):
    return [(p.dish.name, p.staff_expiring + p.staff_carry) for p in plan.dishes
            if p.staff_expiring + p.staff_carry > 0]


def name_staff_meal(plan: Plan) -> str:
    lines = staff_meal_lines(plan)
    if not lines:
        return "No staff meal (nothing safe to repurpose)"
    items = ", ".join(f"{q} x {n}" for n, q in lines)
    named = llm(f"Leftover components for a staff meal for {plan.staff_count} cooks: {items}. "
                "Give ONE short appetising dish name (max 8 words). No quantities.",
                "You name restaurant staff meals. Reply with the name only.", 30)
    return named or "Leftover family-meal bowl"


def explain_plan(plan: Plan) -> list[str]:
    out = []
    for p in plan.dishes:
        n = p.dish.name
        if p.removed:
            out.append(f"{n}: removed at the chef's request. "
                       f"{p.expiring + p.carry} portion(s) on hand go to staff meal or are discarded when they expire.")
            continue
        have = p.expiring + p.carry
        diff = p.prep - p.usual_par
        s = f"{n}: prep {p.prep}"
        s += f" (usual {p.usual_par}, {'-' if diff < 0 else '+'}{abs(diff)})" if diff else f" (same as usual {p.usual_par})"
        s += f". Forecast {p.forecast:.0f} portions ({p.driver})."
        if have:
            s += f" Leftovers on hand: {have}"
            if p.expiring:
                s += f", {p.expiring} must be served tomorrow"
            s += "."
        if p.staff_expiring + p.staff_carry:
            s += f" {p.staff_expiring + p.staff_carry} go to the staff meal."
        if p.expired_on_arrival:
            s += f" {p.expired_on_arrival} are past shelf life and must be discarded."
        if diff < 0 and have:
            s += " Prepping less because leftovers cover part of demand."
        elif diff > 0:
            s += " Prepping more because demand is forecast above the usual level or the risk of selling out is high."
        s += f" Chance of selling out: {p.p_stockout:.0%}."
        out.append(s)
    out.append(f"Staff meal ({plan.staff_count} staff): {plan.staff_meal_name} - "
               + (", ".join(f"{q} x {n}" for n, q in staff_meal_lines(plan)) or "none") + ".")
    out.append(f"Total cook time: {plan.prep_minutes:.0f} min"
               + (f" (cap {plan.request.prep_cap_min:.0f})" if plan.request and plan.request.prep_cap_min else "") + ".")
    return out


def parse_change_request(text: str, menu=MENU) -> Request:
    """Free text -> Request. Tries the LLM for flexible phrasing (validated), falls back to rules."""
    req = Request(text=text)
    t = text.lower()

    def find_dish(frag):
        words = set(re.findall(r"[a-z]+", frag))
        sc = [(len(words & set(re.findall(r"[a-z]+", d.name.lower()))), d) for d in menu]
        best = max(sc, key=lambda x: x[0])
        return best[1] if best[0] else None

    for m in re.finditer(r"(?:remove|drop|no|86|take off|skip)\s+(?:the\s+)?([a-z ]+?)(?:[,.;]|$| and | but )", t):
        d = find_dish(m.group(1))
        if d: req.remove.add(d.name)
    m = re.search(r"(?:cap|limit|max(?:imum)?|under)\s+(?:prep(?:\s+time)?\s+)?(?:at|to)?\s*(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m)\b", t)
    if m:
        v = float(m.group(1)); req.prep_cap_min = v * 60 if m.group(2).startswith("h") else v
    for m in re.finditer(r"(?:max|at most|no more than)\s+(\d+)\s+(?:portions? of\s+)?([a-z ]+?)(?:[,.;]|$| and )", t):
        d = find_dish(m.group(2))
        if d: req.max_portions[d.name] = int(m.group(1))
    for m in re.finditer(r"(?:at least|min(?:imum)?)\s+(\d+)\s+(?:portions? of\s+)?([a-z ]+?)(?:[,.;]|$| and )", t):
        d = find_dish(m.group(2))
        if d: req.min_portions[d.name] = int(m.group(1))
    m = re.search(r"(\d+)\s+staff|staff(?: count)?(?: is| of)?\s+(\d+)", t)
    if m: req.staff_count = int(m.group(1) or m.group(2))
    return req


def diff_plans(old: Plan, new: Plan) -> list[str]:
    out = []
    for a, b in zip(old.dishes, new.dishes):
        if a.prep != b.prep:
            out.append(f"{a.dish.name}: prep {a.prep} -> {b.prep}")
        sa, sb = a.staff_expiring + a.staff_carry, b.staff_expiring + b.staff_carry
        if sa != sb:
            out.append(f"{a.dish.name}: staff portions {sa} -> {sb}")
    out.append(f"Cook time: {old.prep_minutes:.0f} -> {new.prep_minutes:.0f} min")
    out.append(f"Staff meal: {old.staff_meal_name} -> {new.staff_meal_name}")
    return out


def replan(plan, req, fc, scen, inventory, staff_count, cfg, panel, menu=MENU):
    new = optimize_plan(plan.date, fc, scen, inventory, staff_count, cfg, panel, menu, request=req)
    return new, diff_plans(plan, new)


# --------------------------------------------------------------------------------------
# 7. Backtest: the agent vs. the usual par-level kitchen
# --------------------------------------------------------------------------------------


def _staff_for(date, base):
    return int(round(base * (1.25 if date.dayofweek in (4, 5) else 1.0)))


def _run_day(inv, menu, demand, prep, staff_take, ):
    """One service day. inv ages are as of today. Returns metrics and the rolled-over inventory."""
    rev = food = lost_units = lost_rev = 0.0
    staff_units = waste_units = waste_cost = 0.0
    stockout = False
    for i, d in enumerate(menu):
        stock = inv.get(d.name, {})
        stock[0] = stock.get(0, 0) + prep[i]
        food += prep[i] * d.cost
        take = staff_take[i]
        for a in sorted(stock, reverse=True):          # staff eat the oldest first
            q = min(stock[a], take); stock[a] -= q; take -= q; staff_units += q
        need = demand[i]
        for a in sorted(stock, reverse=True):          # FIFO sales
            q = min(stock[a], need); stock[a] -= q; need -= q; rev += q * d.price
        if need > 0:
            lost_units += need; lost_rev += need * d.price; stockout = True
        new = {}
        for a, q in stock.items():
            if q <= 0: continue
            if a + 1 > d.shelf_life:
                waste_units += q; waste_cost += q * d.cost
            else:
                new[a + 1] = new.get(a + 1, 0) + q
        inv[d.name] = new
    return dict(revenue=rev, food_cost=food, lost_units=lost_units, lost_rev=lost_rev, staff_units=staff_units,
                waste_units=waste_units, waste_cost=waste_cost, stockout=stockout), inv


def backtest(panel, menu=MENU, cfg: Config = Config(), days=60, end="2026-11-01", staff_base=9,
             prep_cap=None, retrain_every=30, verbose=False) -> pd.DataFrame:
    """Three kitchens on identical simulated demand:
       agent  - Tomorrow's Plate (forecast + leftovers + optimizer + staff meal)
       usual  - par-level prep (4-wk same-weekday avg x buffer) that ignores leftovers
       netted - careful chef: par minus usable leftovers, rounded up to batch (a strong manual baseline)"""
    cfg = replace(cfg, prep_cap_min=prep_cap or cfg.prep_cap_min)
    rng = np.random.default_rng(cfg.seed)
    dates = pd.date_range(end=end, periods=days, freq="D")
    inv = {k: {d.name: {} for d in menu} for k in ("agent", "usual", "netted")}
    fcst, last_fit = None, None
    recs = []

    def baseline_take(inv_k, staff):
        left, take = staff, []
        for d in menu:
            E = pools(inv_k.get(d.name), d.shelf_life)[0]
            q = min(left, int(E * cfg.baseline_staff_recovery)); take.append(q); left -= q
        return take

    def record(name, m, date, prep, demand_total):
        m["staff_value"] = m["staff_units"] * cfg.staff_value
        m.update(policy=name, date=date, demand=demand_total,
                 prep_min=sum(prep[i] * d.prep_min for i, d in enumerate(menu)))
        recs.append(m)

    for t, date in enumerate(dates):
        if fcst is None or (date - last_fit).days >= retrain_every:
            fcst, last_fit = DemandForecaster(seed=cfg.seed).fit(panel, date), date
        actual = panel[panel.date == date].sort_values("dish_id").demand.values
        staff = _staff_for(date, staff_base)
        # --- agent
        fc = fcst.forecast(panel, date)
        scen = fcst.scenarios(fc["mean"].values, cfg.n_scenarios, rng)
        plan = optimize_plan(date, fc, scen, inv["agent"], staff, cfg, panel, menu)
        prep = [p.prep for p in plan.dishes]
        take = [p.staff_expiring + p.staff_carry for p in plan.dishes]
        m, inv["agent"] = _run_day(inv["agent"], menu, actual, prep, take)
        record("agent", m, date, prep, actual.sum())
        # --- usual par kitchen
        par = [usual_par(panel, i, date, cfg.baseline_par_buffer, d.batch) for i, d in enumerate(menu)]
        m, inv["usual"] = _run_day(inv["usual"], menu, actual, par, baseline_take(inv["usual"], staff))
        record("usual", m, date, par, actual.sum())
        # --- netted kitchen
        netp = []
        for i, d in enumerate(menu):
            E, C, _ = pools(inv["netted"].get(d.name), d.shelf_life)
            netp.append(int(math.ceil(max(par[i] - E - C, 0) / d.batch) * d.batch))
        m, inv["netted"] = _run_day(inv["netted"], menu, actual, netp, baseline_take(inv["netted"], staff))
        record("netted", m, date, netp, actual.sum())
        if verbose and t % 15 == 0:
            print(f"  backtest day {t + 1}/{days}")
    return pd.DataFrame(recs)


def summarize(bt: pd.DataFrame, cfg: Config = Config()) -> pd.DataFrame:
    g = bt.groupby("policy")
    s = pd.DataFrame({
        "waste_portions": g.waste_units.sum(),
        "waste_cost": g.waste_cost.sum(),
        "food_cost": g.food_cost.sum(),
        "revenue": g.revenue.sum(),
        "fill_rate_%": 100 * (1 - g.lost_units.sum() / g.demand.sum()),
        "lost_sales_units": g.lost_units.sum(),
        "stockout_days_%": g.stockout.mean() * 100,
        "staff_meals_served": g.staff_units.sum(),
        "worst_day_waste_cost": g.waste_cost.max(),
    })
    # neutral cash view: revenue - ingredient spend + value of staff meals recovered (no goodwill assumptions)
    s["net_contribution"] = g.revenue.sum() - g.food_cost.sum() + g.staff_value.sum()
    return s.round(1).loc[["usual", "netted", "agent"]]


SECTORS = {
    # name: scale, demand noise, staff count, prep minutes cap
    "Independent restaurant": dict(scale=1.0, noise=0.12, staff=9),
    "Hotel buffet / banquet": dict(scale=4.0, noise=0.20, staff=30),
    "Corporate / hospital cafeteria": dict(scale=3.0, noise=0.06, staff=22),
    "Cruise galley (manifest known)": dict(scale=8.0, noise=0.04, staff=50),
}


def run_sector_study(days=30, cfg: Config = Config()) -> pd.DataFrame:
    rows = []
    for name, sp in SECTORS.items():
        panel = simulate_panel(scale=sp["scale"], noise=sp["noise"], seed=cfg.seed)
        bt = backtest(panel, cfg=cfg, days=days, staff_base=sp["staff"], prep_cap=cfg.prep_cap_min * sp["scale"])
        s = summarize(bt, cfg)
        u, n, a = s.loc["usual"], s.loc["netted"], s.loc["agent"]
        rows.append({
            "sector": name,
            "waste_cut_vs_usual_%": 100 * (1 - a.waste_portions / max(u.waste_portions, 1)),
            "waste_cut_vs_netted_%": 100 * (1 - a.waste_portions / max(n.waste_portions, 1)),
            "fill_rate_usual_%": u["fill_rate_%"], "fill_rate_agent_%": a["fill_rate_%"],
            "gain_per_day_vs_usual": (a.net_contribution - u.net_contribution) / days,
            "gain_per_day_vs_netted": (a.net_contribution - n.net_contribution) / days,
            "gain_vs_usual_%": 100 * (a.net_contribution - u.net_contribution) / max(abs(u.net_contribution), 1),
        })
    return pd.DataFrame(rows).set_index("sector").round(1)


# --------------------------------------------------------------------------------------
# 8. Demo: one full cycle (voice check-in -> prep list -> chef change -> re-plan)
# --------------------------------------------------------------------------------------

VOICE = ("Closing check, Sunday. Eight meatballs, six arancini, five calabreselli, "
         "four risotto from yesterday, nine puccia, three tiramisu, two stracci.")


def demo(cfg: Config = Config(), staff_count=9):
    panel = simulate_panel(seed=cfg.seed)
    tomorrow = pd.Timestamp("2026-11-02")  # Monday
    rng = np.random.default_rng(cfg.seed)
    print("=== 1. End-of-night voice check-in ===")
    print(f'"{VOICE}"')
    inv = parse_leftover_transcript(VOICE)
    for k, v in inv.items():
        print(f"  logged: {k}: {v}  (age tomorrow -> qty)")
    fc_model = DemandForecaster(seed=cfg.seed).fit(panel, tomorrow)
    fc = fc_model.forecast(panel, tomorrow)
    scen = fc_model.scenarios(fc["mean"].values, cfg.n_scenarios, rng)
    print(f"\nForecast model holdout error (MAPE): {fc_model.holdout_mape:.0%}")
    plan = optimize_plan(tomorrow, fc, scen, inv, staff_count, cfg, panel)
    print(f"\n=== 2. Prep list for {tomorrow:%A %b %d} (solver: {plan.solver}) ===")
    for line in explain_plan(plan):
        print(" -", line)
    req = parse_change_request("Remove the meatballs, cap prep at 12 hours, max 8 portions of risotto")
    print("\n=== 3. Chef change request ===")
    print(f'  "{req.text}"\n  parsed -> remove={req.remove}, cap={req.prep_cap_min} min, max={req.max_portions}')
    new, diff = replan(plan, req, fc, scen, inv, staff_count, cfg, panel)
    print("\n=== 4. Agent re-plan: what changed ===")
    for d in diff:
        print(" -", d)
    print("\n=== Revised explanations ===")
    for line in explain_plan(new):
        print(" -", line)
    return plan, new


def main(argv):
    mode = argv[1] if len(argv) > 1 else "demo"
    cfg = Config()
    if mode in ("demo", "all"):
        demo(cfg)
    if mode in ("backtest", "all"):
        print("\n=== 60-day backtest: usual par-level kitchen vs Tomorrow's Plate (simulated restaurant) ===")
        panel = simulate_panel(seed=cfg.seed)
        bt = backtest(panel, cfg=cfg, days=60, verbose=True)
        s = summarize(bt, cfg)
        print(s.T.to_string())
        bt.to_csv("backtest_daily.csv", index=False)
        s.to_csv("backtest_summary.csv")
        u, n, a = s.loc["usual"], s.loc["netted"], s.loc["agent"]
        print(f"\nVs usual kitchen: waste portions {100 * (1 - a.waste_portions / u.waste_portions):.0f}% lower, "
              f"ingredient spend ${u.food_cost - a.food_cost:,.0f} lower, "
              f"cash contribution +${a.net_contribution - u.net_contribution:,.0f}, "
              f"fill rate {a['fill_rate_%']:.1f}% vs {u['fill_rate_%']:.1f}%.")
        print(f"Vs careful 'netted' chef: waste {a.waste_portions:.0f} vs {n.waste_portions:.0f} portions (both ~zero), "
              f"cash contribution +${a.net_contribution - n.net_contribution:,.0f}, "
              f"fill rate {a['fill_rate_%']:.1f}% vs {n['fill_rate_%']:.1f}%.")
    if mode in ("sectors", "all"):
        print("\n=== Value by business type (30-day backtests, simulated) ===")
        res = run_sector_study(cfg=cfg)
        print(res.to_string())
        res.to_csv("sector_study.csv")


if __name__ == "__main__":
    main(sys.argv)

