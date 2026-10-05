"""Deterministic synthetic tables (CSV / XLSX) for the seed corpus.

Fictional data created for the MarketSignal demo. All randomness flows from a
seeded random.Random; planted fact rows come from world_model.yaml.
"""

from __future__ import annotations

import random

from common import DISCLAIMER, fact_ws
from text_pools import (
    REVIEW_CLOSERS,
    REVIEW_CONTEXT,
    REVIEW_CUSTOM,
    REVIEW_MIXED,
    REVIEW_NEGATIVE,
    REVIEW_POSITIVE,
    SP_SURVEY_CORE,
    SP_SURVEY_TAILS,
    SURVEY_CONTEXT,
    SURVEY_CORE,
    SURVEY_TAIL_NEGATIVE,
    SURVEY_TAIL_NEUTRAL,
    SURVEY_TAIL_POSITIVE,
)

NOTICE = DISCLAIMER


def _planted(world: dict, ws: str, code: str) -> list[dict]:
    return [
        f
        for f in world["facts"]
        if fact_ws(f) == ws and f["src"] == code and isinstance(f.get("row"), dict)
    ]


def _expand(counts: dict) -> list:
    out: list = []
    for key, n in counts.items():
        out.extend([key] * int(n))
    return out


def _months(start: tuple[int, int], n: int) -> list[str]:
    y, m = start
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def _distribute(total: int, weights: list[float]) -> list[int]:
    """Split an integer total by weights with exact sum (largest remainder)."""
    s = sum(weights)
    raw = [total * w / s for w in weights]
    base = [int(x) for x in raw]
    rem = total - sum(base)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - base[i]), i))
    for i in order[:rem]:
        base[i] += 1
    return base


# ---------------------------------------------------------------------------
# Northstar survey
# ---------------------------------------------------------------------------
SEGMENT_AGE = {
    "Campus Competitors": {"18-21": 60, "22-24": 36},
    "Studio Social": {"18-21": 30, "22-24": 48, "25-27": 46},
    "Trail Starters": {"18-21": 22, "22-24": 26, "25-27": 28},
    "Value Seekers": {"18-21": 38, "22-24": 30, "25-27": 36},
}


def _nps_score(rng: random.Random, kind: str) -> int:
    if kind == "promoter":
        return rng.choice([9, 9, 10])
    if kind == "passive":
        return rng.choice([7, 8, 8])
    return rng.choice([2, 3, 4, 5, 5, 6, 6, 6])


def _survey_verbatim(rng: random.Random, pain: str, nps: int) -> str:
    core = rng.sample(SURVEY_CORE[pain], 2 if rng.random() < 0.3 else 1)
    if nps >= 9:
        tail_pool = SURVEY_TAIL_POSITIVE
    elif nps >= 7:
        tail_pool = SURVEY_TAIL_NEUTRAL
    else:
        tail_pool = SURVEY_TAIL_NEGATIVE
    parts = ([rng.choice(SURVEY_CONTEXT)] if rng.random() < 0.45 else []) + list(core)
    if rng.random() < 0.6:
        parts.append(rng.choice(tail_pool))
    return " ".join(parts)


def northstar_survey(world: dict, rng: random.Random) -> dict:
    sv = world["northstar"]["survey_2026"]
    records: list[dict] = []
    for group, seg_ages in (("gen_z", SEGMENT_AGE), ("older", None)):
        n = sv["gen_z_respondents"] if group == "gen_z" else sv["older_respondents"]
        if seg_ages:
            pairs = [
                (seg, age)
                for seg, ages in seg_ages.items()
                for age, c in ages.items()
                for _ in range(c)
            ]
        else:
            pairs = [("Established Active", age) for age in _expand(sv["age_groups_older"])]
        pains = _expand(sv["top_pain_point_counts"][group])
        nps_kinds = (
            ["promoter"] * sv["nps"][group]["promoters"]
            + ["passive"] * sv["nps"][group]["passives"]
            + ["detractor"] * sv["nps"][group]["detractors"]
        )
        price = _expand(sv["price_sensitivity_counts"][group])
        for lst in (pairs, pains, nps_kinds, price):
            assert len(lst) == n, (group, len(lst), n)
            rng.shuffle(lst)
        for (seg, age), pain, kind, ps in zip(pairs, pains, nps_kinds, price):
            records.append(
                {
                    "segment": seg,
                    "age_group": age,
                    "top_pain_point": pain,
                    "nps": _nps_score(rng, kind),
                    "price_sensitivity": int(ps),
                }
            )
    rng.shuffle(records)
    for i, rec in enumerate(records):
        rec["respondent_id"] = f"R{i + 1:04d}"
        rec["survey_date"] = f"2026-05-{rng.randint(4, 22):02d}"
        rec["region"] = rng.choices(sv["regions"], weights=[22, 20, 18, 16, 24])[0]
        rec["gender"] = rng.choices(sv["genders"], weights=[52, 42, 4, 2])[0]
        rec["purchase_frequency"] = rng.choices(sv["purchase_frequency"], weights=[18, 37, 30, 15])[
            0
        ]
        rec["verbatim"] = _survey_verbatim(rng, rec["top_pain_point"], rec["nps"])
    # plant fact rows: swap attribute bundles so the keyed respondent matches
    attr_keys = ["segment", "age_group", "top_pain_point", "nps", "price_sensitivity"]
    planted = _planted(world, "NORTHSTAR", "SURVEY-2026")
    planted_ids = {f["row"]["key_value"] for f in planted}
    by_id = {r["respondent_id"]: r for r in records}
    for f in planted:
        target = by_id[f["row"]["key_value"]]
        need = f.get("row_fields", {})
        if not all(target[k] == v for k, v in need.items()):
            donor = next(
                r
                for r in records
                if r["respondent_id"] not in planted_ids and all(r[k] == v for k, v in need.items())
            )
            for k in attr_keys:
                target[k], donor[k] = donor[k], target[k]
            donor["verbatim"] = _survey_verbatim(rng, donor["top_pain_point"], donor["nps"])
        target[f["row"]["value_column"]] = f["row"]["value"]
    cols = [
        "respondent_id",
        "survey_date",
        "age_group",
        "segment",
        "region",
        "gender",
        "purchase_frequency",
        "price_sensitivity",
        "nps",
        "top_pain_point",
        "verbatim",
        "data_notice",
    ]
    rows = [[r[c] for c in cols[:-1]] + [NOTICE] for r in records]
    return {"columns": cols, "rows": rows, "bom": True}


# ---------------------------------------------------------------------------
# Northstar product catalogue (shared by reviews and product performance)
# ---------------------------------------------------------------------------
CATALOG = [
    # sku, name, category, price, launch, base_units, return_rate, rating
    ("NS-KR2", "Knit Runner 2", "Running Footwear", 128, "2025-09-01", 61500, 16.8, 3.4),
    ("NS-KR1", "Knit Runner", "Running Footwear", 115, "2023-08-15", 38200, 13.1, 4.0),
    ("NS-SWT", "Switchback Trail", "Running Footwear", 118, "2025-03-01", 29800, 14.6, 3.8),
    ("NS-TMP", "Tempo Lite", "Running Footwear", 135, "2024-02-15", 33400, 10.9, 4.2),
    ("NS-CRU", "Cruise Daily Trainer", "Running Footwear", 104, "2024-09-01", 41200, 11.7, 4.1),
    ("NS-PVT", "Pivot Trainer", "Training Footwear", 98, "2024-05-01", 35600, 9.8, 4.0),
    ("NS-LFT", "Lift Flat", "Training Footwear", 89, "2023-11-01", 18300, 8.4, 4.3),
    ("NS-HIT", "Circuit HIIT Shoe", "Training Footwear", 109, "2025-06-01", 22100, 12.2, 3.9),
    ("NS-CCL", "Court Classic", "Court and Lifestyle Footwear", 92, "2022-03-01", 47800, 8.9, 4.4),
    (
        "NS-CCC",
        "Court Classic Custom",
        "Court and Lifestyle Footwear",
        118,
        "2026-04-06",
        6100,
        11.0,
        4.2,
    ),
    (
        "NS-RTR",
        "Retro Trainer 86",
        "Court and Lifestyle Footwear",
        96,
        "2024-10-01",
        30500,
        9.5,
        4.1,
    ),
    ("NS-SLD", "Slide Recovery", "Court and Lifestyle Footwear", 38, "2023-05-01", 52300, 5.2, 4.3),
    (
        "NS-SCL",
        "Studio Contour Legging",
        "Leggings and Bottoms",
        68,
        "2023-01-15",
        212400,
        9.1,
        4.6,
    ),
    ("NS-SCS", "Studio Contour Short", "Leggings and Bottoms", 48, "2024-04-01", 88900, 8.7, 4.4),
    ("NS-FLJ", "Flex Jogger", "Leggings and Bottoms", 72, "2023-09-01", 97200, 12.4, 4.1),
    ("NS-RSH", "Race Day Short", "Leggings and Bottoms", 44, "2024-03-01", 64800, 7.9, 4.3),
    ("NS-CRG", "Cargo Trail Pant", "Leggings and Bottoms", 84, "2025-08-01", 31700, 13.8, 3.9),
    (
        "NS-HFL",
        "High Rise Flare Legging",
        "Leggings and Bottoms",
        74,
        "2025-02-01",
        73600,
        11.2,
        4.2,
    ),
    ("NS-BTE", "Breeze Tee", "Tops and Tees", 34, "2022-06-01", 154300, 6.8, 4.3),
    ("NS-SBR", "Studio Sports Bra", "Tops and Tees", 52, "2023-02-01", 118700, 10.6, 4.2),
    ("NS-CRP", "Crop Training Tank", "Tops and Tees", 38, "2024-05-15", 86500, 9.3, 4.1),
    ("NS-LSL", "Long Sleeve Run Top", "Tops and Tees", 48, "2023-10-01", 58400, 7.4, 4.3),
    ("NS-GPH", "Graphic Campus Tee", "Tops and Tees", 32, "2025-08-15", 69200, 8.1, 4.0),
    ("NS-CHD", "Cloudweight Hoodie", "Outerwear and Hoodies", 88, "2023-09-15", 92600, 10.2, 4.4),
    ("NS-WBJ", "Windbreak Jacket", "Outerwear and Hoodies", 110, "2024-09-15", 27400, 11.9, 4.0),
    ("NS-QZP", "Quarter Zip Pullover", "Outerwear and Hoodies", 78, "2024-01-15", 48100, 9.0, 4.2),
    ("NS-PFV", "Puffer Vest", "Outerwear and Hoodies", 98, "2025-10-01", 19800, 12.8, 3.9),
    ("NS-CRW", "Crew Sock 3 Pack", "Accessories", 18, "2022-01-01", 176500, 2.1, 4.5),
    ("NS-CAP", "Run Cap", "Accessories", 28, "2023-04-01", 41800, 3.3, 4.4),
    ("NS-DUF", "Studio Duffel", "Accessories", 64, "2024-08-01", 16900, 4.6, 4.3),
    ("NS-BTL", "Insulated Bottle", "Accessories", 26, "2024-02-01", 38700, 2.8, 4.5),
    ("NS-BLT", "Run Belt", "Accessories", 30, "2025-04-01", 12400, 5.5, 4.0),
]
CAT_CODES = {
    "Running Footwear": "RUN",
    "Training Footwear": "TRN",
    "Court and Lifestyle Footwear": "CRT",
    "Leggings and Bottoms": "LEG",
    "Tops and Tees": "TOP",
    "Outerwear and Hoodies": "OUT",
    "Accessories": "ACC",
}


def northstar_reviews(world: dict, rng: random.Random) -> dict:
    channels = ["Brand Site", "App", "Marketplace", "Social Shop"]
    weights = [n * (1.0 / max(r, 1)) for (_, _, _, _, _, n, r, _) in CATALOG]
    rows = []
    for i in range(1, 801):
        sku, name, cat, price, launch, _, _, mean_rating = rng.choices(CATALOG, weights=weights)[0]
        r = rng.gauss(mean_rating, 1.0)
        rating = max(1, min(5, int(round(r))))
        if name.endswith("Custom") or rng.random() < 0.03 and "Footwear" in cat:
            first = rng.choice(REVIEW_CUSTOM)
        elif rating >= 4:
            first = rng.choice(REVIEW_POSITIVE)
        elif rating == 3:
            first = rng.choice(REVIEW_MIXED)
        else:
            first = rng.choice(REVIEW_NEGATIVE)
        second_pool = (
            REVIEW_POSITIVE if rating >= 4 else REVIEW_NEGATIVE if rating <= 2 else REVIEW_MIXED
        )
        ctx = rng.choice(REVIEW_CONTEXT)
        parts = ([ctx] if ctx else []) + [first]
        if rng.random() < 0.55:
            second = rng.choice(second_pool)
            if second != first:
                parts.append(second)
        closer = rng.choice(REVIEW_CLOSERS)
        if closer:
            parts.append(closer)
        day = rng.randint(0, 364)
        y, m, d = _date_from_offset(2025, 10, 1, day)
        date = f"{y:04d}-{m:02d}-{d:02d}"
        if date < launch:
            date = launch
        rows.append(
            {
                "review_id": f"RV-{i:05d}",
                "product": name,
                "category": cat,
                "rating": rating,
                "date": date,
                "channel": rng.choices(channels, weights=[38, 27, 22, 13])[0],
                "review_text": " ".join(parts),
            }
        )
    by_id = {r["review_id"]: r for r in rows}
    cat_of = {c[1]: c[2] for c in CATALOG}
    for f in _planted(world, "NORTHSTAR", "REVIEWS"):
        rec = by_id[f["row"]["key_value"]]
        for k, v in (f.get("row_fields") or {}).items():
            rec[k] = v
        rec["category"] = cat_of[rec["product"]]
        rec[f["row"]["value_column"]] = f["row"]["value"]
    cols = [
        "review_id",
        "product",
        "category",
        "rating",
        "date",
        "channel",
        "review_text",
        "data_notice",
    ]
    return {"columns": cols, "rows": [[r[c] for c in cols[:-1]] + [NOTICE] for r in rows]}


def _date_from_offset(y: int, m: int, d: int, offset: int) -> tuple[int, int, int]:
    import datetime as dt

    t = dt.date(y, m, d) + dt.timedelta(days=offset)
    return t.year, t.month, t.day


# ---------------------------------------------------------------------------
# Northstar channel performance (CSV)
# ---------------------------------------------------------------------------
CHANNEL_BASE = {
    # code: (name, sessions_genz, sessions_mill, conv_genz, conv_mill, aov_genz, aov_mill, ret_genz, ret_mill, growth)
    "SITE": ("Brand Site", 820000, 760000, 2.3, 2.9, 88.0, 104.0, 19.5, 15.8, 0.006),
    "APP": ("App", 410000, 260000, 3.6, 3.9, 93.0, 108.0, 14.2, 11.9, 0.012),
    "SOCIAL": ("Social Shop", 90000, 30000, 2.9, 1.9, 61.0, 66.0, 17.8, 14.6, 0.10),
    "MARKET": ("Marketplace", 520000, 610000, 4.1, 4.6, 72.0, 84.0, 16.1, 13.2, 0.004),
    "STORES": ("Stores", 380000, 450000, 18.5, 22.0, 79.0, 91.0, 8.4, 7.1, -0.004),
}


def northstar_channels(world: dict, rng: random.Random) -> dict:
    months = _months((2025, 10), 12)
    recs = []
    for mi, month in enumerate(months):
        season = 1.0 + 0.12 * (month[5:] in ("11", "12")) - 0.06 * (month[5:] in ("01", "02"))
        for code, (name, s_g, s_m, c_g, c_m, a_g, a_m, r_g, r_m, growth) in CHANNEL_BASE.items():
            for seg, segcode, s, c, a, r in (
                ("Gen Z", "GENZ", s_g, c_g, a_g, r_g),
                ("Millennial", "MILL", s_m, c_m, a_m, r_m),
            ):
                g = (1 + growth) ** mi
                if code == "SOCIAL" and seg == "Gen Z":
                    g = (1 + growth * 1.3) ** mi
                recs.append(
                    {
                        "record_id": f"CP-{month}-{code}-{segcode}",
                        "month": month,
                        "channel": name,
                        "segment": seg,
                        "sessions": int(round(s * g * season * rng.uniform(0.94, 1.06))),
                        "conversion_rate_pct": round(c * rng.uniform(0.92, 1.08), 1),
                        "aov_usd": round(a * rng.uniform(0.95, 1.05), 1),
                        "return_rate_pct": round(r * rng.uniform(0.92, 1.08), 1),
                    }
                )
    by_id = {r["record_id"]: r for r in recs}
    for f in _planted(world, "NORTHSTAR", "CHANNEL-PERF"):
        by_id[f["row"]["key_value"]][f["row"]["value_column"]] = f["row"]["value"]

    def recompute(r: dict) -> None:
        r["orders"] = int(round(r["sessions"] * r["conversion_rate_pct"] / 100))
        r["net_sales_usd"] = int(round(r["orders"] * r["aov_usd"]))

    for r in recs:
        recompute(r)
    # enforce Social Shop Q2-2026 vs Q1-2026 net sales growth (world model / Q3 review fact NS-085)
    target = 1 + world["northstar"]["social_shop_qoq_growth_q2_2026_pct"] / 100
    q1 = [
        r
        for r in recs
        if r["channel"] == "Social Shop" and r["month"] in ("2026-01", "2026-02", "2026-03")
    ]
    q2 = [
        r
        for r in recs
        if r["channel"] == "Social Shop" and r["month"] in ("2026-04", "2026-05", "2026-06")
    ]
    factor = target * sum(r["net_sales_usd"] for r in q1) / sum(r["net_sales_usd"] for r in q2)
    for r in q2:
        r["sessions"] = int(round(r["sessions"] * factor))
        recompute(r)
    growth = sum(r["net_sales_usd"] for r in q2) / sum(r["net_sales_usd"] for r in q1) - 1
    assert round(growth * 100) == world["northstar"]["social_shop_qoq_growth_q2_2026_pct"], growth
    cols = [
        "record_id",
        "month",
        "channel",
        "segment",
        "sessions",
        "orders",
        "conversion_rate_pct",
        "net_sales_usd",
        "aov_usd",
        "return_rate_pct",
        "data_notice",
    ]
    return {"columns": cols, "rows": [[r[c] for c in cols[:-1]] + [NOTICE] for r in recs]}


# ---------------------------------------------------------------------------
# Northstar product performance (XLSX)
# ---------------------------------------------------------------------------
RETURN_REASONS = {
    "FIT": "Fit - runs small",
    "FTL": "Fit - runs large",
    "DUR": "Durability - upper wear",
    "FAB": "Durability - fabric or seams",
    "CHG": "Changed mind",
    "COL": "Color not as shown",
    "LAT": "Arrived late",
}
RETURN_SKUS = {
    "NS-KR2": ["DUR", "FIT", "CHG"],
    "NS-KR1": ["FIT", "DUR", "CHG"],
    "NS-SWT": ["FIT", "FTL", "LAT"],
    "NS-TMP": ["FTL", "CHG", "COL"],
    "NS-PVT": ["FIT", "CHG", "LAT"],
    "NS-CCC": ["LAT", "COL", "FIT"],
    "NS-SCL": ["FTL", "FAB", "CHG"],
    "NS-FLJ": ["FIT", "FTL", "CHG"],
    "NS-SBR": ["FIT", "FAB", "COL"],
    "NS-CHD": ["FTL", "COL", "CHG"],
}


def northstar_product(world: dict, rng: random.Random) -> dict:
    ns = world["northstar"]
    cats = ns["categories"]
    # --- Category_Monthly: quarter totals pinned to the world model
    cm_rows = []
    month_w = [0.31, 0.33, 0.36]
    for year, quarters in ns["company"]["quarterly_net_revenue_usd_m"].items():
        for q, total_m in quarters.items():
            if q.startswith("Q4_forecast"):
                continue
            qn = int(q[1])
            months = [f"{year}-{(qn - 1) * 3 + k + 1:02d}" for k in range(3)]
            per_month = _distribute(
                int(round(total_m * 1_000_000)), [w * rng.uniform(0.95, 1.05) for w in month_w]
            )
            for month, mtotal in zip(months, per_month):
                per_cat = _distribute(mtotal, [c["weight"] * rng.uniform(0.9, 1.1) for c in cats])
                for c, sales in zip(cats, per_cat):
                    avg_price = {
                        "RUN": 112,
                        "TRN": 96,
                        "CRT": 84,
                        "LEG": 64,
                        "TOP": 39,
                        "OUT": 86,
                        "ACC": 24,
                    }[c["code"]]
                    cm_rows.append(
                        {
                            "record_id": f"CM-{month}-{c['code']}",
                            "month": month,
                            "category": c["name"],
                            "net_sales_usd": sales,
                            "units": int(round(sales / (avg_price * rng.uniform(0.92, 1.0)))),
                            "gross_margin_pct": round(c["margin"] + rng.uniform(-1.5, 1.5), 1),
                            "sell_through_pct": round(rng.uniform(58, 82), 1),
                            "genz_share_pct": round(rng.uniform(16, 26), 1),
                        }
                    )
    # --- SKU_Performance
    sku_rows = []
    for sku, name, cat, price, launch, units, ret, rating in CATALOG:
        disc = rng.uniform(0.08, 0.2)
        sku_rows.append(
            {
                "sku": sku,
                "product_name": name,
                "category": cat,
                "launch_date": launch,
                "price_usd": price,
                "units_fy26_ytd": units,
                "net_sales_fy26_ytd_usd": int(round(units * price * (1 - disc))),
                "return_rate_pct": ret,
                "avg_rating": rating,
                "genz_share_pct": round(
                    rng.uniform(14, 34)
                    + (6 if cat in ("Leggings and Bottoms", "Tops and Tees") else 0),
                    1,
                ),
            }
        )
    # --- Returns
    sku_info = {r["sku"]: r for r in sku_rows}
    rt_rows = []
    quarters = ["2025-Q4", "2026-Q1", "2026-Q2", "2026-Q3"]
    pinned_totals = {"NS-KR2": [2050, 2500, 2832, 5000]}
    for sku, reasons in RETURN_SKUS.items():
        info = sku_info[sku]
        ytd_returns = int(round(info["units_fy26_ytd"] * info["return_rate_pct"] / 100))
        if sku in pinned_totals:
            totals = pinned_totals[sku]
            assert sum(totals[1:]) == ytd_returns, (sku, ytd_returns)
        else:
            q26 = _distribute(ytd_returns, [rng.uniform(0.8, 1.2) for _ in range(3)])
            totals = [int(round(q26[0] * rng.uniform(0.85, 1.1)))] + q26
        for q, total in zip(quarters, totals):
            shares = [rng.uniform(0.18, 0.4) for _ in reasons]
            for code, share in zip(reasons, shares):
                rid = f"RT-{q.replace('-', '')}-{sku[3:]}-{code}"
                rt_rows.append(
                    {
                        "record_id": rid,
                        "quarter": q,
                        "sku": sku,
                        "product_name": info["product_name"],
                        "reason": RETURN_REASONS[code],
                        "total_sku_returns": total,
                        "returns_count": int(round(total * share)),
                        "share_of_sku_returns_pct": None,
                    }
                )
    rt_by = {r["record_id"]: r for r in rt_rows}
    sku_by = {r["sku"]: r for r in sku_rows}
    cm_by = {r["record_id"]: r for r in cm_rows}
    for f in _planted(world, "NORTHSTAR", "PRODUCT-PERF"):
        row = f["row"]
        table = {"Returns": rt_by, "SKU_Performance": sku_by, "Category_Monthly": cm_by}[
            row["sheet"]
        ]
        rec = table[row["key_value"]]
        rec[row["value_column"]] = row["value"]
        if row["sheet"] == "Returns" and row["value_column"] == "share_of_sku_returns_pct":
            rec["returns_count"] = int(round(rec["total_sku_returns"] * row["value"] / 100))
    for r in rt_rows:
        r["share_of_sku_returns_pct"] = round(100 * r["returns_count"] / r["total_sku_returns"], 1)
    for f in _planted(world, "NORTHSTAR", "PRODUCT-PERF"):
        row = f["row"]
        if row["sheet"] == "Returns":
            assert rt_by[row["key_value"]][row["value_column"]] == row["value"], f["id"]
    assert max(r["units_fy26_ytd"] for r in sku_rows) == sku_by["NS-SCL"]["units_fy26_ytd"]

    def sheet(name: str, cols: list[str], recs: list[dict]) -> dict:
        return {
            "name": name,
            "columns": cols + ["data_notice"],
            "rows": [[r[c] for c in cols] + [NOTICE] for r in recs],
        }

    return {
        "title": "Northstar Product Performance",
        "sheets": [
            sheet(
                "Category_Monthly",
                [
                    "record_id",
                    "month",
                    "category",
                    "net_sales_usd",
                    "units",
                    "gross_margin_pct",
                    "sell_through_pct",
                    "genz_share_pct",
                ],
                cm_rows,
            ),
            sheet(
                "SKU_Performance",
                [
                    "sku",
                    "product_name",
                    "category",
                    "launch_date",
                    "price_usd",
                    "units_fy26_ytd",
                    "net_sales_fy26_ytd_usd",
                    "return_rate_pct",
                    "avg_rating",
                    "genz_share_pct",
                ],
                sku_rows,
            ),
            sheet(
                "Returns",
                [
                    "record_id",
                    "quarter",
                    "sku",
                    "product_name",
                    "reason",
                    "total_sku_returns",
                    "returns_count",
                    "share_of_sku_returns_pct",
                ],
                rt_rows,
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Northstar financial summary (XLSX)
# ---------------------------------------------------------------------------
def northstar_financials(world: dict) -> dict:
    ns = world["northstar"]["company"]
    rev25, rev26 = ns["fy25_net_revenue_usd_m"], ns["fy26_le_net_revenue_usd_m"]
    gm25, gm26 = 46.4, ns["fy26_le_gross_margin_pct"]
    gp25, gp26 = round(rev25 * gm25 / 100, 1), round(rev26 * gm26 / 100, 1)
    mkt25, mkt26 = 52.4, 58.1
    sga25, sga26 = 160.2, 168.9
    op25, op26 = round(gp25 - mkt25 - sga25, 1), round(gp26 - mkt26 - sga26, 1)

    def yoy(a: float, b: float) -> float:
        return round(100 * (b - a) / a, 1)

    pnl = [
        ("Net revenue", "USD m", rev25, rev26, yoy(rev25, rev26)),
        (
            "Cost of goods sold",
            "USD m",
            round(rev25 - gp25, 1),
            round(rev26 - gp26, 1),
            yoy(rev25 - gp25, rev26 - gp26),
        ),
        ("Gross profit", "USD m", gp25, gp26, yoy(gp25, gp26)),
        ("Gross margin %", "percent", gm25, gm26, None),
        ("Marketing expense", "USD m", mkt25, mkt26, yoy(mkt25, mkt26)),
        ("SG&A excluding marketing", "USD m", sga25, sga26, yoy(sga25, sga26)),
        ("Operating income", "USD m", op25, op26, yoy(op25, op26)),
        (
            "Operating margin %",
            "percent",
            round(100 * op25 / rev25, 1),
            round(100 * op26 / rev26, 1),
            None,
        ),
        ("DTC share of revenue %", "percent", 41.0, 44.5, None),
        ("Inventory at year end", "USD m", 118.4, 126.0, yoy(118.4, 126.0)),
    ]
    seg = [
        (
            "Gen Z (18-27)",
            "Customers aged 18 to 27 at time of purchase (finance definition)",
            110.8,
            126.1,
        ),
        ("Millennial (28-43)", "Customers aged 28 to 43", 251.2, 266.8),
        ("Gen X (44-59)", "Customers aged 44 to 59", 158.2, 165.2),
        ("Boomer and older (60+)", "Customers aged 60 and over", 50.8, 53.9),
    ]
    assert round(sum(s[2] for s in seg), 1) == rev25 and round(sum(s[3] for s in seg), 1) == rev26
    seg_rows = [
        [name, d, a, round(100 * a / rev25, 1), b, round(100 * b / rev26, 1), yoy(a, b), NOTICE]
        for name, d, a, b in seg
    ]
    seg_rows.append(
        ["Total", "All identified customers", rev25, 100.0, rev26, 100.0, yoy(rev25, rev26), NOTICE]
    )
    return {
        "title": "Northstar Financial Summary FY26",
        "sheets": [
            {
                "name": "PnL_Summary",
                "columns": [
                    "line_item",
                    "unit",
                    "fy25_actual",
                    "fy26_le",
                    "yoy_change_pct",
                    "data_notice",
                ],
                "rows": [list(r) + [NOTICE] for r in pnl],
            },
            {
                "name": "Segment_Revenue",
                "columns": [
                    "segment",
                    "definition",
                    "fy25_revenue_usd_m",
                    "fy25_share_pct",
                    "fy26_le_revenue_usd_m",
                    "fy26_le_share_pct",
                    "yoy_growth_pct",
                    "data_notice",
                ],
                "rows": seg_rows,
            },
        ],
    }


# ---------------------------------------------------------------------------
# Category sizing (XLSX)
# ---------------------------------------------------------------------------
def category_sizing(world: dict, rng: random.Random) -> dict:
    # anchor (gen, cat) -> (anchor year, value, annual growth)
    anchors = {
        ("GENZ", "FW"): (2026, 18.6, 0.071),
        ("GENZ", "AP"): (2025, 44.8, 0.052),
        ("GENZ", "PFW"): (2026, 1.1, 0.24),
        ("MILL", "FW"): (2026, 23.9, 0.028),
        ("MILL", "AP"): (2026, 58.3, 0.024),
        ("MILL", "PFW"): (2026, 0.9, 0.17),
        ("GENX", "FW"): (2026, 17.2, 0.009),
        ("GENX", "AP"): (2026, 39.6, 0.011),
        ("GENX", "PFW"): (2026, 0.4, 0.09),
    }
    gen_names = {"GENZ": "Gen Z", "MILL": "Millennial", "GENX": "Gen X and older"}
    cat_names = {
        "FW": "Athletic footwear",
        "AP": "Athletic apparel",
        "PFW": "Personalized athletic footwear",
    }
    rows = []
    for (gen, cat), (ay, av, g) in anchors.items():
        prev = None
        for year in range(2023, 2029):
            val = round(av * (1 + g) ** (year - ay), 1)
            basis = "Actual" if year <= 2024 else "Estimate" if year <= 2026 else "Forecast"
            rows.append(
                [
                    "US-%s-%s-%d" % (gen, cat, year),
                    "US",
                    gen_names[gen],
                    cat_names[cat],
                    year,
                    val,
                    None if prev is None else round(100 * (val - prev) / prev, 1),
                    basis,
                    "Cobalt Insight Partners model, September 2026 update",
                    NOTICE,
                ]
            )
            prev = val
    planted = {
        f["row"]["key_value"]: f["row"]["value"]
        for f in _planted(world, "NORTHSTAR", "CATEGORY-SIZING")
    }
    for r in rows:
        if r[0] in planted:
            assert r[5] == planted[r[0]], (r[0], r[5])
    assert (
        next(r[5] for r in rows if r[0] == "US-GENZ-AP-2025")
        == world["market"]["genz_trends"]["v2_2026"]["apparel_market_usd_bn_2025_restated"]
    )
    return {
        "title": "US Athletic Category Sizing",
        "sheets": [
            {
                "name": "Market_Sizing",
                "columns": [
                    "record_id",
                    "market",
                    "generation",
                    "category",
                    "year",
                    "value_usd_bn",
                    "yoy_growth_pct",
                    "basis",
                    "source_note",
                    "data_notice",
                ],
                "rows": rows,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Southpeak (decoy workspace)
# ---------------------------------------------------------------------------
def southpeak_survey(world: dict, rng: random.Random) -> dict:
    # shares match the Southpeak brand strategy / board deck (33/15/11/14/10/6/8, other 3)
    counts = {
        "fit_inconsistency": 99,
        "price_vs_value": 45,
        "durability": 33,
        "sustainability_transparency": 42,
        "delivery_speed": 30,
        "personalization": 18,
        "community": 24,
        "waterproofing": 9,
    }
    pains = _expand(counts)
    rng.shuffle(pains)
    segs = world["southpeak"]["segments"]
    seg_list = _expand(dict(zip(segs, [114, 51, 72, 63])))
    rng.shuffle(seg_list)
    rows = []
    for i, (pain, seg) in enumerate(zip(pains, seg_list), start=1):
        nps = rng.choice([3, 5, 6, 7, 8, 8, 9, 9, 10])
        text = rng.choice(SP_SURVEY_CORE[pain])
        tail = rng.choice(SP_SURVEY_TAILS)
        rows.append(
            {
                "respondent_id": f"SP-R{i:04d}",
                "survey_date": f"2026-04-{rng.randint(6, 24):02d}",
                "age_group": rng.choice(["18-24", "25-34", "35-44", "45-54", "55+"]),
                "segment": seg,
                "region": rng.choice(
                    ["Mountain West", "Pacific Northwest", "Northeast", "Midwest", "Southwest"]
                ),
                "primary_activity": rng.choice(
                    ["Day hiking", "Backpacking", "Trail running", "Camping", "Climbing"]
                ),
                "nps": nps,
                "top_pain_point": pain,
                "verbatim": (text + " " + tail).strip(),
            }
        )
    by_id = {r["respondent_id"]: r for r in rows}
    for f in _planted(world, "SOUTHPEAK", "SURVEY-2026"):
        rec = by_id[f["row"]["key_value"]]
        if (rec["top_pain_point"], rec["segment"]) != (
            f["row_fields"]["top_pain_point"],
            f["row_fields"]["segment"],
        ):
            donor = next(
                r
                for r in rows
                if r["top_pain_point"] == f["row_fields"]["top_pain_point"]
                and r["segment"] == f["row_fields"]["segment"]
                and r["respondent_id"] != rec["respondent_id"]
            )
            for k in ("top_pain_point", "segment"):
                donor[k], rec[k] = rec[k], donor[k]
            donor["verbatim"] = rng.choice(SP_SURVEY_CORE[donor["top_pain_point"]])
        rec[f["row"]["value_column"]] = f["row"]["value"]
    cols = [
        "respondent_id",
        "survey_date",
        "age_group",
        "segment",
        "region",
        "primary_activity",
        "nps",
        "top_pain_point",
        "verbatim",
        "data_notice",
    ]
    return {"columns": cols, "rows": [[r[c] for c in cols[:-1]] + [NOTICE] for r in rows]}


def southpeak_channels(world: dict, rng: random.Random) -> dict:
    base = {
        "SITE": ("Brand Site", 310000, 2.1, 142.0),
        "APP": ("App", 95000, 3.2, 151.0),
        "MARKET": ("Marketplace", 180000, 3.8, 118.0),
        "STORES": ("Stores", 140000, 19.0, 133.0),
        "OUTFIT": ("Outfitter Partners", 60000, 6.5, 127.0),
    }
    rows = []
    for mi, month in enumerate(_months((2025, 10), 12)):
        for code, (name, s, c, a) in base.items():
            sessions = int(round(s * (1.01**mi) * rng.uniform(0.9, 1.1)))
            conv = round(c * rng.uniform(0.9, 1.1), 1)
            aov = round(a * rng.uniform(0.95, 1.05), 1)
            rows.append(
                {
                    "record_id": f"SPC-{month}-{code}",
                    "month": month,
                    "channel": name,
                    "sessions": sessions,
                    "conversion_rate_pct": conv,
                    "aov_usd": aov,
                }
            )
    by_id = {r["record_id"]: r for r in rows}
    for f in _planted(world, "SOUTHPEAK", "CHANNEL-DATA"):
        by_id[f["row"]["key_value"]][f["row"]["value_column"]] = f["row"]["value"]
    for r in rows:
        r["orders"] = int(round(r["sessions"] * r["conversion_rate_pct"] / 100))
        r["net_sales_usd"] = int(round(r["orders"] * r["aov_usd"]))
    cols = [
        "record_id",
        "month",
        "channel",
        "sessions",
        "orders",
        "conversion_rate_pct",
        "aov_usd",
        "net_sales_usd",
    ]
    region = [
        ["Mountain West", 41.2],
        ["Pacific Northwest", 19.8],
        ["Northeast", 16.5],
        ["Midwest", 12.1],
        ["Southwest", 10.4],
    ]
    return {
        "title": "Southpeak Channel Data",
        "sheets": [
            {
                "name": "Channel_Monthly",
                "columns": cols + ["data_notice"],
                "rows": [[r[c] for c in cols] + [NOTICE] for r in rows],
            },
            {
                "name": "Region_Summary",
                "columns": ["region", "share_of_fy26_ytd_sales_pct", "data_notice"],
                "rows": [r + [NOTICE] for r in region],
            },
        ],
    }


def build_tables(world: dict) -> dict[tuple[str, str], dict]:
    """Return {(ws, source_code): table_or_book} for every tabular source."""
    seed = int(world["meta"]["seed"])

    def r(tag: str) -> random.Random:
        return random.Random(f"{seed}:{tag}")

    return {
        ("NORTHSTAR", "PRODUCT-PERF"): northstar_product(world, r("product")),
        ("NORTHSTAR", "CHANNEL-PERF"): northstar_channels(world, r("channel")),
        ("NORTHSTAR", "FIN-SUMMARY-FY26"): northstar_financials(world),
        ("NORTHSTAR", "SURVEY-2026"): northstar_survey(world, r("survey")),
        ("NORTHSTAR", "REVIEWS"): northstar_reviews(world, r("reviews")),
        ("NORTHSTAR", "CATEGORY-SIZING"): category_sizing(world, r("sizing")),
        ("SOUTHPEAK", "SURVEY-2026"): southpeak_survey(world, r("sp_survey")),
        ("SOUTHPEAK", "CHANNEL-DATA"): southpeak_channels(world, r("sp_channel")),
    }
