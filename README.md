# SufraEats — Expansion Dashboard

Interactive Streamlit dashboard built for the MAIB Python Final Group Capstone. It answers the
core business question:

> **Which Dubai zone should SufraEats choose for its expansion investment — and why?**

The dashboard's cleaning, merge, and revenue logic is identical to `SufraEats_Analysis.ipynb`, so
every number shown here matches the analysis notebook.

---

## 1. What's in this folder

| File | Purpose |
|---|---|
| `app.py` | The Streamlit dashboard. Run this. |
| `sufraeats_orders.csv` | Raw orders data (~48,000 rows). Required input — do not rename. |
| `sufraeats_restaurants.csv` | Raw restaurant data (~230 rows, zone/cuisine/commission). Required input — do not rename. |
| `requirements.txt` | Python packages needed to run the app. |
| `SufraEats_Analysis.ipynb` | The companion analysis notebook (Deliverable A) — not included in this package, keep it alongside if you have it. |

`app.py` loads the two CSVs directly and does its own cleaning at runtime — you do **not** need to
run the notebook first or produce a separate cleaned CSV.

---

## 2. How to run it

```bash
# 1. Install dependencies (once)
pip install -r requirements.txt

# 2. Make sure all files are in the same folder:
#    app.py, sufraeats_orders.csv, sufraeats_restaurants.csv

# 3. Launch
streamlit run app.py
```

This opens the dashboard in your browser, usually at `http://localhost:8501`. Closing the terminal
stops the app.

**Requirements:** Python 3.9+, and the packages in `requirements.txt` (`streamlit`, `pandas`,
`numpy`, `plotly`).

---

## 3. Data cleaning — what happens before you see a single chart

`app.py` re-applies the same documented cleaning steps as the analysis notebook, in this order:

1. **Strip whitespace** on every text column (fixes `'Marina '` vs `'Marina'` being read as two zones).
2. **Drop exact duplicate rows** (596 in the raw file).
3. **Drop re-logged duplicate `order_id`s**, keeping the first occurrence.
4. **Unify zone labels**: `JLT` → `Jumeirah Lake Towers`.
5. **Unify cuisine labels**: fix casing (`INDIAN`/`indian` → `Indian`) and merge `Healthy`/`healthy food`
   into one `Healthy Food` category.
6. **Merge orders → restaurants** on `restaurant_id`, `how="left"` — orders with no matching
   restaurant (~4% of rows) are kept in platform-wide totals but automatically excluded from any
   zone/cuisine breakdown, since they have no zone or cuisine to assign.
7. **Neutralise impossible values** (set to missing rather than silently deleting the row):
   - `delivery_time_min` negative or over 180 minutes for Delivery orders,
   - `basket_value` ≤ 0,
   - `discount_amount` capped at `basket_value` (a discount can't exceed the order it discounts).

The full list of issues found and decisions made is also shown live in the dashboard's
**🔍 Data Quality Notes** tab.

---

## 4. Realised revenue — the core metric

Gross `basket_value` is not what SufraEats actually keeps. The dashboard computes:

```
realised_revenue = commission_rate x (basket_value - discount_amount) + delivery_fee   [Delivered orders only]
realised_revenue = 0                                                                    [Cancelled / Refunded orders]
```

This is used instead of gross order value everywhere it matters, because a zone can look large on
gross value while quietly losing money to cancellations, refunds, discounts, and low restaurant
commission rates. The **Overview** tab shows this trap directly (a zone can top the gross-value chart
and not top the realised-revenue chart).

---

## 5. Dashboard structure

| Tab | What it covers |
|---|---|
| 📍 Overview & Recommendation | Gross value vs. realised revenue by zone, revenue-vs-cancellation bubble chart, full zone scorecard, revenue-leakage waterfall, order-outcome mix |
| 🏙️ Zone Deep-Dive | Cancellation/refund rates, delivery time (bar + box + violin), ratings, order volume, average basket value, normalised radar comparison |
| 🍽️ Cuisine | Revenue and volume by cuisine, cancellation rate, cuisine mix per zone, average basket value, revenue-vs-volume bubble chart |
| 📅 Time & Seasonality | Daily trend with Ramadan highlighted, monthly/hourly/day-of-week breakdowns, hour×zone and day×hour heatmaps, weekday vs. weekend, monthly revenue trend |
| 🏷️ Promotions | Promo vs. no-promo comparison, revenue by promo code, discount-given vs. revenue-earned scatter |
| 👥 Customer Behaviour | New vs. Repeat, channel, payment method, device platform, rating by customer type |
| 🏪 Restaurant Profile | Price tier, premium partner status, dark kitchens vs. seated restaurants, prep time vs. delivery time, restaurant tenure, top/bottom 10 restaurants by revenue |
| 🔍 Data Quality Notes | Issue/count/decision table, the realised-revenue formula, and a live preview of the filtered dataset |

**Sidebar filters** (zone, cuisine, order channel, order status, customer type, date range, promo
usage) apply live to every metric and chart on the page.

---

## 6. Known limitations / things to check before presenting

- Data covers 5 months (Jan–May 2025) and a single Ramadan cycle — seasonality conclusions are based
  on one occurrence, not a multi-year pattern.
- ~4% of orders reference a restaurant not in `sufraeats_restaurants.csv`; they're included in
  platform-wide totals but invisible to any zone/cuisine chart. Worth mentioning as a risk in the
  presentation.
- Delivery-time and basket-value sentinel values (999 min, AED 9999) were treated as data-entry
  errors and neutralised — reasonable, but an assumption worth stating out loud.
- The dashboard does not assert a final recommended zone — that judgment call belongs to your team,
  based on the evidence the Overview tab surfaces.

---

## 7. Credits

Built for the SufraEats MAIB Python Capstone — "Where Should We Grow Next?"
