"""
SufraEats — Dubai Expansion Dashboard
======================================
Interactive Streamlit dashboard for SufraEats leadership.

Answers the core question: which Dubai zone should SufraEats choose for its
expansion investment — and why?

Cleaning, merge, and "realised revenue" logic below is IDENTICAL to
SufraEats_Analysis.ipynb, so every number here matches the analysis notebook.

Run with:
    streamlit run app.py
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# --------------------------------------------------------------------------
# Page setup
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="SufraEats — Expansion Dashboard",
    page_icon="🚚",
    layout="wide",
)

ACCENT = "#2f6f4f"      # realised revenue / "truth" green
GREY = "#c9c9c9"        # gross value / "surface" grey
WARN = "#b23b3b"        # cancellations / risk red
BLUE = "#3b6bb2"

px.defaults.template = "plotly_white"


# --------------------------------------------------------------------------
# Data loading & cleaning — mirrors SufraEats_Analysis.ipynb exactly
# --------------------------------------------------------------------------
@st.cache_data
def load_and_clean():
    orders = pd.read_csv("sufraeats_orders.csv")
    restaurants = pd.read_csv("sufraeats_restaurants.csv")

    notes = {}

    # 1. strip whitespace on every text column (fixes 'Marina ' vs 'Marina')
    for c in orders.select_dtypes(include="object").columns:
        orders[c] = orders[c].str.strip()
    for c in restaurants.select_dtypes(include="object").columns:
        restaurants[c] = restaurants[c].str.strip()

    # 2. drop exact duplicate rows
    before = len(orders)
    orders = orders.drop_duplicates()
    notes["exact_dupes_dropped"] = before - len(orders)

    # 3. drop re-logged duplicate order_ids, keep first
    before = len(orders)
    orders = orders.drop_duplicates(subset="order_id", keep="first")
    notes["relogged_dupes_dropped"] = before - len(orders)

    # 4. unify zone labels (JLT == Jumeirah Lake Towers)
    restaurants["zone"] = restaurants["zone"].replace({"JLT": "Jumeirah Lake Towers"})

    # 5. unify cuisine labels (casing + Healthy/healthy food)
    def clean_cuisine(c):
        c = c.strip().lower()
        if c in ("healthy", "healthy food"):
            return "Healthy Food"
        return c.title()

    restaurants["cuisine"] = restaurants["cuisine"].apply(clean_cuisine)

    # 6. merge orders -> restaurants, left join, track unmatched
    df = orders.merge(restaurants, on="restaurant_id", how="left", indicator=True)
    notes["unmatched_orders"] = int((df["_merge"] == "left_only").sum())
    notes["unmatched_pct"] = notes["unmatched_orders"] / len(df)
    df = df.drop(columns="_merge")

    # 7. neutralise impossible numeric values (set to NaN / cap, don't silently drop rows)
    bad_delivery = (df["order_channel"] == "Delivery") & (
        (df["delivery_time_min"] < 0) | (df["delivery_time_min"] > 180)
    )
    notes["delivery_time_neutralised"] = int(bad_delivery.sum())
    df.loc[bad_delivery, "delivery_time_min"] = np.nan

    bad_basket = df["basket_value"] <= 0
    notes["basket_value_neutralised"] = int(bad_basket.sum())
    df.loc[bad_basket, "basket_value"] = np.nan

    bad_discount = df["discount_amount"] > df["basket_value"]
    notes["discount_capped"] = int(bad_discount.sum())
    df.loc[bad_discount, "discount_amount"] = df.loc[bad_discount, "basket_value"]

    # 8. realised revenue = commission x net basket, delivery fee kept, Delivered only
    df["net_basket_value"] = df["basket_value"] - df["discount_amount"]
    avg_commission = df["commission_rate"].mean()
    df["commission_rate_filled"] = df["commission_rate"].fillna(avg_commission)
    df["platform_revenue"] = np.where(
        df["order_status"] == "Delivered",
        df["net_basket_value"] * df["commission_rate_filled"] + df["delivery_fee"],
        0.0,
    )

    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["day_of_week"] = df["date"].dt.day_name()
    df["had_promo"] = df["promo_code"].notna()

    notes["rows_final"] = len(df)
    notes["rows_raw"] = before  # rows before any order-level drop (post exact-dupe drop count is close enough for display)

    return df, notes


df, clean_notes = load_and_clean()

DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# --------------------------------------------------------------------------
# Sidebar filters
# --------------------------------------------------------------------------
st.sidebar.title("🚚 SufraEats")
st.sidebar.caption("Filters apply to every chart and metric on this page.")

zones = sorted(df["zone"].dropna().unique())
cuisines = sorted(df["cuisine"].dropna().unique())
channels = sorted(df["order_channel"].dropna().unique())
statuses = sorted(df["order_status"].dropna().unique())
cust_types = sorted(df["customer_type"].dropna().unique())

sel_zones = st.sidebar.multiselect("Zone", zones, default=zones)
sel_cuisines = st.sidebar.multiselect("Cuisine", cuisines, default=cuisines)
sel_channels = st.sidebar.multiselect("Order channel", channels, default=channels)
sel_statuses = st.sidebar.multiselect("Order status", statuses, default=statuses)
sel_cust = st.sidebar.multiselect("Customer type", cust_types, default=cust_types)

min_date, max_date = df["date"].min().date(), df["date"].max().date()
sel_dates = st.sidebar.date_input(
    "Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date
)
if isinstance(sel_dates, tuple) and len(sel_dates) == 2:
    start_date, end_date = sel_dates
else:
    start_date, end_date = min_date, max_date

promo_filter = st.sidebar.radio("Promo usage", ["All orders", "With promo only", "No promo only"])

st.sidebar.divider()
st.sidebar.caption(
    f"Cleaned dataset: {clean_notes['rows_final']:,} orders "
    f"({clean_notes['exact_dupes_dropped']} exact duplicates and "
    f"{clean_notes['relogged_dupes_dropped']} re-logged duplicates removed)."
)

# apply filters — note: zone/cuisine NaN rows (unmatched restaurants) are
# naturally excluded once a zone/cuisine multiselect is active, matching the
# notebook's documented handling of orphan orders.
mask = (
    df["zone"].isin(sel_zones)
    & df["cuisine"].isin(sel_cuisines)
    & df["order_channel"].isin(sel_channels)
    & df["order_status"].isin(sel_statuses)
    & df["customer_type"].isin(sel_cust)
    & (df["date"].dt.date >= start_date)
    & (df["date"].dt.date <= end_date)
)
fdf = df[mask].copy()
if promo_filter == "With promo only":
    fdf = fdf[fdf["had_promo"]]
elif promo_filter == "No promo only":
    fdf = fdf[~fdf["had_promo"]]

if fdf.empty:
    st.warning("No orders match the current filters. Widen your filter selection.")
    st.stop()

# --------------------------------------------------------------------------
# Header + headline KPIs
# --------------------------------------------------------------------------
st.title("SufraEats — Where Should We Expand?")
st.caption(
    "Which Dubai zone should SufraEats choose for its expansion investment — and why? "
    "Evidence-based, not gross-revenue-based."
)

total_orders = len(fdf)
gross_value = fdf["basket_value"].sum()
realised_revenue = fdf["platform_revenue"].sum()
cancel_rate = (fdf["order_status"] == "Cancelled").mean()
refund_rate = (fdf["order_status"] == "Refunded").mean()
avg_rating = fdf["rating"].mean()
avg_delivery = fdf.loc[fdf["order_channel"] == "Delivery", "delivery_time_min"].mean()

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Total orders", f"{total_orders:,}")
k2.metric("Gross order value", f"AED {gross_value:,.0f}")
k3.metric("Realised revenue", f"AED {realised_revenue:,.0f}",
          help="What SufraEats actually keeps: commission x (basket - discount) + delivery fee, Delivered orders only.")
k4.metric("Cancellation rate", f"{cancel_rate:.1%}")
k5.metric("Refund rate", f"{refund_rate:.1%}")
k6.metric("Avg rating", f"{avg_rating:.2f} / 5" if pd.notna(avg_rating) else "n/a")

st.divider()

# --------------------------------------------------------------------------
# Tabs
# --------------------------------------------------------------------------
tab_overview, tab_zone, tab_cuisine, tab_time, tab_promo, tab_customer, tab_restaurant, tab_quality = st.tabs(
    ["📍 Overview & Recommendation", "🏙️ Zone Deep-Dive", "🍽️ Cuisine", "📅 Time & Seasonality",
     "🏷️ Promotions", "👥 Customer Behaviour", "🏪 Restaurant Profile", "🔍 Data Quality Notes"]
)

# ---- Zone stats table used across tabs -----------------------------------
def zone_stats_table(data):
    z = data.dropna(subset=["zone"]).groupby("zone").agg(
        total_orders=("order_id", "count"),
        gross_value=("basket_value", "sum"),
        realised_revenue=("platform_revenue", "sum"),
        cancel_rate=("order_status", lambda s: (s == "Cancelled").mean()),
        refund_rate=("order_status", lambda s: (s == "Refunded").mean()),
        avg_delivery_time=("delivery_time_min", "mean"),
        avg_rating=("rating", "mean"),
    ).round(2)
    return z

zstats = zone_stats_table(fdf)

# ============================================================================
# TAB 1 — Overview & Recommendation
# ============================================================================
with tab_overview:
    if len(zstats) >= 1:
        top_gross_zone = zstats["gross_value"].idxmax()
        top_revenue_zone = zstats["realised_revenue"].idxmax()

        st.subheader("The core finding")
        colA, colB = st.columns(2)
        with colA:
            st.metric("Biggest zone by gross order value", top_gross_zone,
                      f"AED {zstats.loc[top_gross_zone, 'gross_value']:,.0f}")
        with colB:
            st.metric("Biggest zone by realised revenue", top_revenue_zone,
                      f"AED {zstats.loc[top_revenue_zone, 'realised_revenue']:,.0f}")

        if top_gross_zone != top_revenue_zone:
            st.error(
                f"⚠️ **{top_gross_zone}** looks biggest on the surface, but once cancellations, refunds and "
                f"commission are accounted for, **{top_revenue_zone}** is the zone that's actually healthiest. "
                f"{top_gross_zone}'s cancellation rate is **{zstats.loc[top_gross_zone,'cancel_rate']:.0%}** and "
                f"refund rate **{zstats.loc[top_gross_zone,'refund_rate']:.0%}**, versus "
                f"**{zstats.loc[top_revenue_zone,'cancel_rate']:.0%}** / **{zstats.loc[top_revenue_zone,'refund_rate']:.0%}** "
                f"in {top_revenue_zone}, and its average delivery time is "
                f"**{zstats.loc[top_gross_zone,'avg_delivery_time']:.1f} min** vs "
                f"**{zstats.loc[top_revenue_zone,'avg_delivery_time']:.1f} min**."
            )
        else:
            st.success(f"✅ **{top_gross_zone}** leads on both gross value and realised revenue — a consistent signal.")

        st.caption(
            "These figures update live with your sidebar filters — the values above reflect the *current* "
            "filter selection, not necessarily the full-dataset recommendation. Reset filters to see the "
            "full-dataset picture used for the final recommendation."
        )

    st.subheader("Gross value vs. realised revenue, by zone")
    st.caption("The chart on the left is the misleading number. The chart on the right is what the business actually keeps.")
    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(zstats.sort_values("gross_value", ascending=False).reset_index(),
                     x="zone", y="gross_value", color_discrete_sequence=[GREY],
                     title="Gross order value by zone", labels={"gross_value": "AED", "zone": ""})
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(zstats.sort_values("realised_revenue", ascending=False).reset_index(),
                     x="zone", y="realised_revenue", color_discrete_sequence=[ACCENT],
                     title="Realised revenue by zone (what SufraEats keeps)",
                     labels={"realised_revenue": "AED", "zone": ""})
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Zone health at a glance: revenue vs. cancellation rate")
    st.caption("Bubble size = order volume. Zones in the top-left (high revenue, low cancellations) are the strongest expansion candidates.")
    fig = px.scatter(
        zstats.reset_index(), x="cancel_rate", y="realised_revenue", size="total_orders",
        color="zone", text="zone", size_max=55,
        labels={"cancel_rate": "Cancellation rate", "realised_revenue": "Realised revenue (AED)"},
    )
    fig.update_traces(textposition="top center")
    fig.update_layout(xaxis_tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Full zone scorecard")
    st.dataframe(
        zstats.sort_values("realised_revenue", ascending=False).style.format({
            "gross_value": "AED {:,.0f}", "realised_revenue": "AED {:,.0f}",
            "cancel_rate": "{:.1%}", "refund_rate": "{:.1%}",
            "avg_delivery_time": "{:.1f} min", "avg_rating": "{:.2f}",
        }),
        use_container_width=True,
    )

    st.subheader("Where does the gross value actually go?")
    st.caption(
        "A waterfall from gross order value down to realised revenue — showing exactly how much is lost to "
        "cancelled orders, refunded orders, discounts, and commission, before delivery fees are added back."
    )
    delivered_mask = fdf["order_status"] == "Delivered"
    gross_all = fdf["basket_value"].sum()
    cancelled_value = fdf.loc[fdf["order_status"] == "Cancelled", "basket_value"].sum()
    refunded_value = fdf.loc[fdf["order_status"] == "Refunded", "basket_value"].sum()
    discount_on_delivered = fdf.loc[delivered_mask, "discount_amount"].sum()
    commission_kept = (fdf.loc[delivered_mask, "net_basket_value"] * fdf.loc[delivered_mask, "commission_rate_filled"]).sum()
    delivery_fees = fdf.loc[delivered_mask, "delivery_fee"].sum()
    lost_to_commission = fdf.loc[delivered_mask, "net_basket_value"].sum() - commission_kept

    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute", "relative", "relative", "relative", "relative", "relative", "total"],
        x=["Gross order value", "- Cancelled orders", "- Refunded orders", "- Discounts (Delivered)",
           "- Restaurant's share (non-commission)", "+ Delivery fees kept", "= Realised revenue"],
        y=[gross_all, -cancelled_value, -refunded_value, -discount_on_delivered,
           -lost_to_commission, delivery_fees, 0],
        decreasing={"marker": {"color": WARN}},
        increasing={"marker": {"color": ACCENT}},
        totals={"marker": {"color": BLUE}},
    ))
    fig.update_layout(yaxis_title="AED", showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Order outcome mix (city-wide)")
    c1, c2 = st.columns([1, 2])
    with c1:
        status_counts = fdf["order_status"].value_counts().reset_index()
        status_counts.columns = ["order_status", "orders"]
        fig = px.pie(status_counts, names="order_status", values="orders", hole=0.45,
                     color="order_status",
                     color_discrete_map={"Delivered": ACCENT, "Cancelled": WARN, "Refunded": "#e0a04b"})
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        yield_pct = (realised_revenue / gross_all) if gross_all else 0
        st.markdown(
            f"- **{(fdf['order_status']=='Delivered').mean():.1%}** of orders complete successfully.\n"
            f"- **{cancel_rate:.1%}** are cancelled, worth **AED {cancelled_value:,.0f}** in lost gross value.\n"
            f"- **{refund_rate:.1%}** are refunded after the fact, worth **AED {refunded_value:,.0f}**.\n"
            f"- Discounts on Delivered orders alone total **AED {discount_on_delivered:,.0f}**.\n"
            f"- Even successful orders only convert to **AED {realised_revenue:,.0f}** in realised revenue "
            f"after commission — a **{yield_pct:.1%}** yield on gross order value."
        )

# ============================================================================
# TAB 2 — Zone deep-dive
# ============================================================================
with tab_zone:
    st.subheader("Cancellation & refund rate by zone")
    zlong = zstats.reset_index().melt(id_vars="zone", value_vars=["cancel_rate", "refund_rate"],
                                       var_name="metric", value_name="rate")
    zlong["metric"] = zlong["metric"].map({"cancel_rate": "Cancelled", "refund_rate": "Refunded"})
    fig = px.bar(zlong, x="zone", y="rate", color="metric", barmode="group",
                 color_discrete_map={"Cancelled": WARN, "Refunded": "#e0a04b"},
                 labels={"rate": "Share of orders", "zone": ""})
    fig.update_layout(yaxis_tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Average delivery time by zone")
        fig = px.bar(zstats.sort_values("avg_delivery_time").reset_index(),
                     x="zone", y="avg_delivery_time", color_discrete_sequence=[BLUE],
                     labels={"avg_delivery_time": "Minutes", "zone": ""})
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Delivery time distribution by zone")
        st.caption("Box plot shows the spread, not just the average — a wide box means inconsistent delivery experience.")
        delivery_only = fdf[(fdf["order_channel"] == "Delivery") & fdf["delivery_time_min"].notna()]
        fig = px.box(delivery_only, x="zone", y="delivery_time_min", color="zone",
                     labels={"delivery_time_min": "Minutes", "zone": ""})
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Average rating by zone")
    fig = px.bar(zstats.sort_values("avg_rating", ascending=False).reset_index(),
                 x="zone", y="avg_rating", color_discrete_sequence=["#8a5fc9"],
                 labels={"avg_rating": "Avg rating (1-5)", "zone": ""})
    fig.update_yaxes(range=[0, 5])
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Orders per zone (volume)")
    fig = px.bar(zstats.sort_values("total_orders", ascending=False).reset_index(),
                 x="zone", y="total_orders", color_discrete_sequence=[GREY],
                 labels={"total_orders": "Orders", "zone": ""})
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Average basket value by zone")
        avg_basket = fdf.dropna(subset=["zone"]).groupby("zone")["basket_value"].mean().sort_values(ascending=False).reset_index()
        fig = px.bar(avg_basket, x="zone", y="basket_value", color_discrete_sequence=["#c98a5f"],
                     labels={"basket_value": "AED", "zone": ""})
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Rating distribution by zone")
        st.caption("A violin shows the full spread of ratings, not just the average.")
        rated = fdf.dropna(subset=["zone", "rating"])
        fig = px.violin(rated, x="zone", y="rating", color="zone", box=True, points=False)
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Zone comparison — all metrics normalised (radar)")
    st.caption("Each metric rescaled 0-1 across zones so shape, not raw units, tells the story. A bigger, rounder shape is healthier overall.")
    radar_cols = ["realised_revenue", "avg_rating"]
    radar_df = zstats.copy()
    radar_df["low_cancel"] = 1 - radar_df["cancel_rate"]
    radar_df["fast_delivery"] = 1 - (radar_df["avg_delivery_time"] / radar_df["avg_delivery_time"].max())
    norm_cols = ["realised_revenue", "avg_rating", "low_cancel", "fast_delivery"]
    radar_norm = radar_df[norm_cols].copy()
    for col in norm_cols:
        rng = radar_norm[col].max() - radar_norm[col].min()
        radar_norm[col] = (radar_norm[col] - radar_norm[col].min()) / rng if rng > 0 else 0.5
    fig = go.Figure()
    labels_map = {"realised_revenue": "Realised revenue", "avg_rating": "Avg rating",
                  "low_cancel": "Low cancellations", "fast_delivery": "Fast delivery"}
    theta = [labels_map[c] for c in norm_cols] + [labels_map[norm_cols[0]]]
    for zone in radar_norm.index:
        vals = radar_norm.loc[zone, norm_cols].tolist()
        vals += [vals[0]]
        fig.add_trace(go.Scatterpolar(r=vals, theta=theta, fill="toself", name=zone))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 1])), showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# TAB 3 — Cuisine
# ============================================================================
with tab_cuisine:
    cstats = fdf.dropna(subset=["cuisine"]).groupby("cuisine").agg(
        total_orders=("order_id", "count"),
        realised_revenue=("platform_revenue", "sum"),
        cancel_rate=("order_status", lambda s: (s == "Cancelled").mean()),
        avg_rating=("rating", "mean"),
    ).round(3).sort_values("realised_revenue", ascending=False)

    st.subheader("Realised revenue by cuisine")
    fig = px.bar(cstats.reset_index(), x="cuisine", y="realised_revenue",
                 color_discrete_sequence=["#8a5fc9"],
                 labels={"realised_revenue": "AED", "cuisine": ""})
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Order volume by cuisine")
        fig = px.pie(cstats.reset_index(), names="cuisine", values="total_orders", hole=0.45)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Cancellation rate by cuisine")
        fig = px.bar(cstats.sort_values("cancel_rate", ascending=False).reset_index(),
                     x="cuisine", y="cancel_rate", color_discrete_sequence=[WARN],
                     labels={"cancel_rate": "Cancellation rate", "cuisine": ""})
        fig.update_layout(yaxis_tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Cuisine mix by zone")
    st.caption("Which cuisines dominate each zone — useful for restaurant onboarding decisions.")
    mix = fdf.dropna(subset=["zone", "cuisine"]).groupby(["zone", "cuisine"]).size().reset_index(name="orders")
    fig = px.bar(mix, x="zone", y="orders", color="cuisine", barmode="stack",
                 labels={"orders": "Orders", "zone": ""})
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Full cuisine scorecard")
    st.dataframe(
        cstats.style.format({"realised_revenue": "AED {:,.0f}", "cancel_rate": "{:.1%}", "avg_rating": "{:.2f}"}),
        use_container_width=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Average basket value by cuisine")
        avg_by_cuisine = fdf.dropna(subset=["cuisine"]).groupby("cuisine")["basket_value"].mean().sort_values(ascending=False).reset_index()
        fig = px.bar(avg_by_cuisine, x="cuisine", y="basket_value", color_discrete_sequence=["#5f8ac9"],
                     labels={"basket_value": "AED", "cuisine": ""})
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Revenue vs. volume by cuisine")
        st.caption("Bubble size = average rating. Top-right cuisines drive both orders and revenue.")
        fig = px.scatter(cstats.reset_index(), x="total_orders", y="realised_revenue",
                          size="avg_rating", color="cuisine", text="cuisine",
                          labels={"total_orders": "Orders", "realised_revenue": "Realised revenue (AED)"})
        fig.update_traces(textposition="top center")
        st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# TAB 4 — Time & seasonality
# ============================================================================
with tab_time:
    st.subheader("Orders per day, with Ramadan 2025 highlighted")
    daily = fdf.groupby("date").size().reset_index(name="orders")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=daily["date"], y=daily["orders"], mode="lines", line_color=BLUE, name="Orders"))
    fig.add_vrect(x0="2025-03-01", x1="2025-03-30", fillcolor="orange", opacity=0.15,
                  line_width=0, annotation_text="Ramadan 2025 (approx.)", annotation_position="top left")
    fig.update_layout(yaxis_title="Orders", xaxis_title="")
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "March is the highest-volume month — this coincides with Ramadan 2025 (~Mar 1-30), a real demand "
        "event (evening iftar/suhoor ordering), not a data quality issue. It also lines up with the "
        "RAMADAN15 promo code being the most-used code in the dataset."
    )

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Orders by month")
        monthly = fdf.groupby("month").size().reset_index(name="orders")
        fig = px.bar(monthly, x="month", y="orders", color_discrete_sequence=[BLUE])
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Orders by hour of day")
        hourly = fdf.groupby("hour").size().reset_index(name="orders")
        fig = px.bar(hourly, x="hour", y="orders", color_discrete_sequence=["#c98a5f"])
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Orders by day of week")
    dow = fdf.groupby("day_of_week").size().reindex(DOW_ORDER).reset_index(name="orders")
    fig = px.bar(dow, x="day_of_week", y="orders", color_discrete_sequence=["#5fc98a"],
                 labels={"day_of_week": ""})
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Hour-of-day demand by zone (heatmap)")
    st.caption("Darker cells = more orders. Useful for staffing riders by zone and time.")
    heat = fdf.dropna(subset=["zone"]).groupby(["zone", "hour"]).size().reset_index(name="orders")
    heat_p = heat.pivot(index="zone", columns="hour", values="orders").fillna(0)
    fig = px.imshow(heat_p, aspect="auto", color_continuous_scale="Greens",
                     labels={"x": "Hour of day", "y": "", "color": "Orders"})
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Day of week x hour of day (city-wide demand heatmap)")
    st.caption("Shows peak ordering windows across the full week — useful for marketing send-times and rider shift planning.")
    dh = fdf.groupby(["day_of_week", "hour"]).size().reset_index(name="orders")
    dh_p = dh.pivot(index="day_of_week", columns="hour", values="orders").reindex(DOW_ORDER).fillna(0)
    fig = px.imshow(dh_p, aspect="auto", color_continuous_scale="Oranges",
                     labels={"x": "Hour of day", "y": "", "color": "Orders"})
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Weekday vs. weekend")
        fdf["is_weekend"] = fdf["day_of_week"].isin(["Friday", "Saturday"])
        wk = fdf.groupby("is_weekend").agg(orders=("order_id", "count"), avg_basket=("basket_value", "mean")).reset_index()
        wk["label"] = wk["is_weekend"].map({True: "Weekend (Fri-Sat)", False: "Weekday (Sun-Thu)"})
        fig = px.bar(wk, x="label", y="orders", color_discrete_sequence=[BLUE], labels={"label": ""})
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Dubai weekend is Friday-Saturday.")
    with c2:
        st.subheader("Monthly realised revenue trend")
        monthly_rev = fdf.groupby("month")["platform_revenue"].sum().reset_index()
        fig = px.line(monthly_rev, x="month", y="platform_revenue", markers=True,
                      color_discrete_sequence=[ACCENT], labels={"platform_revenue": "AED", "month": ""})
        st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# TAB 5 — Promotions
# ============================================================================
with tab_promo:
    st.subheader("Orders with vs. without a promo code")
    promo_summary = fdf.groupby("had_promo").agg(
        orders=("order_id", "count"),
        avg_basket_value=("basket_value", "mean"),
        avg_discount=("discount_amount", "mean"),
        avg_realised_revenue=("platform_revenue", "mean"),
    ).round(2)
    promo_summary.index = promo_summary.index.map({True: "With promo", False: "No promo"})
    st.dataframe(
        promo_summary.style.format({
            "avg_basket_value": "AED {:,.2f}", "avg_discount": "AED {:,.2f}", "avg_realised_revenue": "AED {:,.2f}",
        }),
        use_container_width=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Realised revenue by promo code")
        by_code = fdf.dropna(subset=["promo_code"]).groupby("promo_code").agg(
            orders=("order_id", "count"),
            total_discount_given=("discount_amount", "sum"),
            total_realised_revenue=("platform_revenue", "sum"),
        ).round(2).sort_values("total_realised_revenue", ascending=False)
        fig = px.bar(by_code.reset_index(), x="promo_code", y="total_realised_revenue",
                     color_discrete_sequence=[BLUE], labels={"total_realised_revenue": "AED", "promo_code": ""})
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Discount given vs. revenue earned, by code")
        fig = px.scatter(by_code.reset_index(), x="total_discount_given", y="total_realised_revenue",
                          size="orders", text="promo_code", color="promo_code",
                          labels={"total_discount_given": "Total discount given (AED)",
                                  "total_realised_revenue": "Total realised revenue (AED)"})
        fig.update_traces(textposition="top center")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Promo code usage table")
    st.dataframe(
        by_code.style.format({"total_discount_given": "AED {:,.0f}", "total_realised_revenue": "AED {:,.0f}"}),
        use_container_width=True,
    )

# ============================================================================
# TAB 6 — Customer behaviour
# ============================================================================
with tab_customer:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("New vs. Repeat")
        vc = fdf["customer_type"].value_counts().reset_index()
        vc.columns = ["customer_type", "orders"]
        fig = px.pie(vc, names="customer_type", values="orders", hole=0.45,
                     color_discrete_sequence=["#5fc98a", "#c9b25f"])
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Order channel")
        vc = fdf["order_channel"].value_counts().reset_index()
        vc.columns = ["order_channel", "orders"]
        fig = px.pie(vc, names="order_channel", values="orders", hole=0.45)
        st.plotly_chart(fig, use_container_width=True)
    with c3:
        st.subheader("Payment method")
        vc = fdf["payment_method"].value_counts().reset_index()
        vc.columns = ["payment_method", "orders"]
        fig = px.pie(vc, names="payment_method", values="orders", hole=0.45)
        st.plotly_chart(fig, use_container_width=True)

    c4, c5 = st.columns(2)
    with c4:
        st.subheader("Device platform")
        vc = fdf["device_platform"].value_counts().reset_index()
        vc.columns = ["device_platform", "orders"]
        fig = px.bar(vc, x="device_platform", y="orders", color_discrete_sequence=[BLUE],
                     labels={"device_platform": ""})
        st.plotly_chart(fig, use_container_width=True)
    with c5:
        st.subheader("New vs. Repeat, by zone")
        nr = fdf.dropna(subset=["zone"]).groupby(["zone", "customer_type"]).size().reset_index(name="orders")
        fig = px.bar(nr, x="zone", y="orders", color="customer_type", barmode="group",
                     labels={"zone": ""})
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Average rating: New vs. Repeat customers")
    rt = fdf.groupby("customer_type")["rating"].mean().reset_index()
    fig = px.bar(rt, x="customer_type", y="rating", color_discrete_sequence=["#8a5fc9"],
                 labels={"customer_type": "", "rating": "Avg rating"})
    fig.update_yaxes(range=[0, 5])
    st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# TAB 7 — Restaurant profile (from restaurants.csv attributes)
# ============================================================================
with tab_restaurant:
    st.caption(
        "These views use the restaurant-level attributes from sufraeats_restaurants.csv — price tier, "
        "premium-partner status, seating capacity, kitchen prep time, and platform tenure — to see which "
        "kinds of restaurants actually perform, not just which zones."
    )

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Realised revenue by price tier")
        pt = fdf.dropna(subset=["price_tier"]).groupby("price_tier")["platform_revenue"].sum().reset_index()
        fig = px.bar(pt, x="price_tier", y="platform_revenue", color_discrete_sequence=["#5f8ac9"],
                     labels={"platform_revenue": "AED", "price_tier": ""})
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Premium partner vs. standard")
        st.caption("Does paying for premium placement actually translate to more revenue and better ratings?")
        pp = fdf.dropna(subset=["is_premium_partner"]).groupby("is_premium_partner").agg(
            orders=("order_id", "count"),
            realised_revenue=("platform_revenue", "sum"),
            avg_rating=("rating", "mean"),
        ).reset_index()
        fig = px.bar(pp, x="is_premium_partner", y="realised_revenue", color_discrete_sequence=[ACCENT],
                     labels={"realised_revenue": "AED", "is_premium_partner": "Premium partner"})
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        st.subheader("Dark kitchens vs. dine-in-capable restaurants")
        st.caption("seating_capacity = 0 means a delivery-only 'dark kitchen'.")
        fdf["kitchen_type"] = np.where(fdf["seating_capacity"] == 0, "Dark kitchen (delivery-only)", "Has seating")
        kt = fdf.dropna(subset=["seating_capacity"]).groupby("kitchen_type").agg(
            orders=("order_id", "count"), avg_rating=("rating", "mean"),
            avg_delivery_time=("delivery_time_min", "mean"),
        ).reset_index()
        fig = px.bar(kt, x="kitchen_type", y="orders", color_discrete_sequence=["#c98a5f"],
                     labels={"kitchen_type": ""})
        st.plotly_chart(fig, use_container_width=True)
    with c4:
        st.subheader("Kitchen prep time vs. delivery time")
        st.caption("Each point is one restaurant's average — is slow delivery a rider problem or a kitchen problem?")
        rest_level = fdf.dropna(subset=["avg_prep_time_min", "delivery_time_min"]).groupby(
            ["restaurant_id", "restaurant_name", "zone"]
        ).agg(avg_prep_time_min=("avg_prep_time_min", "first"), avg_delivery_time=("delivery_time_min", "mean")).reset_index()
        fig = px.scatter(rest_level, x="avg_prep_time_min", y="avg_delivery_time", color="zone",
                          hover_name="restaurant_name",
                          labels={"avg_prep_time_min": "Kitchen prep time (min)", "avg_delivery_time": "Avg delivery time (min)"})
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Restaurant tenure (year joined) vs. performance")
    st.caption("Are newer restaurants ramping up well, or does it take years to become a strong performer?")
    tenure = fdf.dropna(subset=["opened_year"]).groupby("opened_year").agg(
        orders=("order_id", "count"), realised_revenue=("platform_revenue", "sum"), avg_rating=("rating", "mean"),
    ).reset_index()
    fig = go.Figure()
    fig.add_trace(go.Bar(x=tenure["opened_year"], y=tenure["realised_revenue"], name="Realised revenue", marker_color=ACCENT, yaxis="y1"))
    fig.add_trace(go.Scatter(x=tenure["opened_year"], y=tenure["avg_rating"], name="Avg rating", marker_color="#8a5fc9", yaxis="y2"))
    fig.update_layout(
        yaxis=dict(title="Realised revenue (AED)"),
        yaxis2=dict(title="Avg rating", overlaying="y", side="right", range=[0, 5]),
        xaxis=dict(title="Year joined platform"),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Top 10 restaurants by realised revenue")
    top_rest = fdf.dropna(subset=["restaurant_name"]).groupby(
        ["restaurant_name", "zone", "cuisine"]
    )["platform_revenue"].sum().sort_values(ascending=False).head(10).reset_index()
    fig = px.bar(top_rest, x="platform_revenue", y="restaurant_name", orientation="h",
                 color="zone", labels={"platform_revenue": "AED", "restaurant_name": ""})
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Bottom 10 restaurants by realised revenue (among restaurants with orders)")
    bottom_rest = fdf.dropna(subset=["restaurant_name"]).groupby(
        ["restaurant_name", "zone", "cuisine"]
    )["platform_revenue"].sum().sort_values(ascending=True).head(10).reset_index()
    fig = px.bar(bottom_rest, x="platform_revenue", y="restaurant_name", orientation="h",
                 color="zone", labels={"platform_revenue": "AED", "restaurant_name": ""})
    fig.update_layout(yaxis={"categoryorder": "total descending"})
    st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# TAB 8 — Data quality notes (transparency for stakeholders)
# ============================================================================
with tab_quality:
    st.subheader("What was found in the raw data, and what we did about it")
    st.caption("Shown here for transparency — every number in this dashboard is computed from the cleaned data below.")

    dq = pd.DataFrame([
        ["Exact duplicate order rows", f"{clean_notes['exact_dupes_dropped']}", "Dropped — same event recorded twice."],
        ["Re-logged duplicate order_ids", f"{clean_notes['relogged_dupes_dropped']}", "Dropped, kept first occurrence."],
        ["Zone label split (JLT vs Jumeirah Lake Towers)", "—", "Unified to 'Jumeirah Lake Towers'."],
        ["Zone whitespace bug ('Marina ' vs 'Marina')", "—", "Fixed by stripping whitespace on all text columns."],
        ["Cuisine label split (casing + Healthy/healthy food)", "—", "Unified casing; merged into 'Healthy Food'."],
        ["Orders with no matching restaurant (orphans)",
         f"{clean_notes['unmatched_orders']} ({clean_notes['unmatched_pct']:.1%})",
         "Kept in platform-wide totals; excluded from zone/cuisine breakdowns (no zone/cuisine to assign)."],
        ["Impossible delivery_time_min values (negative or >180 min)",
         f"{clean_notes['delivery_time_neutralised']}", "Set to missing (not a real delivery time)."],
        ["Impossible basket_value (<= 0)", f"{clean_notes['basket_value_neutralised']}", "Set to missing."],
        ["discount_amount exceeding basket_value", f"{clean_notes['discount_capped']}",
         "Capped at basket_value — a discount can't exceed the order it discounts."],
        ["Missing ratings", "100% of Cancelled/Refunded orders",
         "Expected, not a data bug — only Delivered orders get rated."],
    ], columns=["Issue found", "Count", "Decision made"])
    st.dataframe(dq, use_container_width=True, hide_index=True)

    st.subheader("Realised revenue — the formula used everywhere in this dashboard")
    st.code(
        "realised_revenue = commission_rate x (basket_value - discount_amount) + delivery_fee   [Delivered orders only]\n"
        "realised_revenue = 0                                                                     [Cancelled / Refunded]",
        language="text",
    )
    st.caption(
        "This is deliberately NOT the same as gross order value. A zone can look huge on gross value while "
        "contributing less to what the business actually keeps — especially with a high cancellation rate "
        "or restaurants on lower commission rates."
    )

    st.subheader("Current filtered dataset preview")
    st.dataframe(fdf.head(20), use_container_width=True)
