"""Streamlit dashboard: rail accident hotspots, causes and recent spikes."""
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA_DIR = Path("data/processed")

# Okabe-Ito colors are readable for most kinds of color blindness.
BLUE = "#0072B2"
ORANGE = "#E69F00"
GREY = "#999999"
SKY = "#56B4E9"

st.set_page_config(page_title="Rail Accident Hotspots and Causes", layout="wide")


@st.cache_data
def load_tables() -> dict:
    """Read every processed CSV once and return them by name."""
    names = [
        "accident_type_counts", "cause_counts", "county_counts",
        "equipment_type_counts", "monthly_counts", "recent_vs_baseline",
        "state_counts", "track_type_counts",
    ]
    tables = {name: pd.read_csv(DATA_DIR / f"{name}.csv") for name in names}
    tables["monthly_counts"]["month"] = pd.to_datetime(tables["monthly_counts"]["month"])
    return tables


@st.cache_data
def load_findings() -> dict:
    """Read the findings summary written by the analysis step."""
    with open(DATA_DIR / "findings.json", encoding="utf-8") as handle:
        return json.load(handle)


def show_metrics(metrics: list) -> None:
    """Show the headline numbers as cards, three per row."""
    for start in range(0, len(metrics), 3):
        columns = st.columns(3)
        for column, metric in zip(columns, metrics[start:start + 3]):
            column.metric(metric["label"], metric["value"], help=metric["explanation"])


def state_map(states: pd.DataFrame) -> None:
    """Draw a US map shaded by accident count per state."""
    top3 = states.nlargest(3, "accidents")
    names = ", ".join(top3["state_name"])
    title = f"Accidents cluster in a few states: {names} hold {top3['share_pct'].sum():.1f}% of reports"
    fig = px.choropleth(
        states, locations="state_abbr", locationmode="USA-states", scope="usa",
        color="accidents", hover_name="state_name",
        color_continuous_scale="Blues", labels={"accidents": "Accidents"},
        title=title,
    )
    fig.update_layout(coloraxis_colorbar_title="Accidents", margin=dict(l=0, r=0, t=60, b=0))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Darker states have more reported accidents. Hover over a state to see its exact count.")


def county_chart(counties: pd.DataFrame, state: str, top_n: int) -> None:
    """Draw a bar chart of the counties with the most accidents."""
    data = counties if state == "All states" else counties[counties["state_abbr"] == state]
    data = data.nlargest(top_n, "accidents").copy()
    if data.empty:
        st.info("No county data for this choice.")
        return
    # County names repeat across states, so always show the state too.
    data["place"] = data["county_name"] + ", " + data["state_abbr"]
    lead = data.iloc[0]
    scope = "in the country" if state == "All states" else f"in {state}"
    title = f"{lead['place']} has the most accidents of any county {scope} ({lead['accidents']:,})"
    fig = px.bar(
        data.sort_values("accidents"), x="accidents", y="place", orientation="h",
        labels={"accidents": "Accidents reported", "place": "County"},
        title=title, color_discrete_sequence=[BLUE],
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Longer bars mean more accidents. Use the sidebar to pick a state or show more counties.")


def category_chart(tables: dict, dimension: str, top_n: int) -> None:
    """Draw a bar chart of the leading categories for one dimension."""
    sources = {
        "Accident type": ("accident_type_counts", "accident_type"),
        "Cause": ("cause_counts", "cause"),
        "Equipment type": ("equipment_type_counts", "equipment_type"),
        "Track type": ("track_type_counts", "track_type"),
    }
    table_name, column = sources[dimension]
    data = tables[table_name]
    # Unknown values would only say "we do not know", so leave them out.
    data = data[data[column] != "Not recorded"].nlargest(top_n, "accidents")
    if data.empty:
        st.info("No categories to show for this choice.")
        return
    lead = data.iloc[0]
    title = f"{lead[column]} leads by {dimension.lower()} ({lead['share_pct']:.1f}% of all reports)"
    fig = px.bar(
        data.sort_values("accidents"), x="accidents", y=column, orientation="h",
        labels={"accidents": "Accidents reported", column: dimension},
        title=title, color_discrete_sequence=[BLUE],
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Longer bars mean more accidents. Causes are shown as FRA cause codes, which are listed in the FRA Form 54 guide.")


def timeline_chart(monthly: pd.DataFrame, years: tuple) -> None:
    """Draw monthly counts with unusual months marked."""
    data = monthly[monthly["month"].dt.year.between(years[0], years[1])]
    if data.empty:
        st.info("No months in this year range.")
        return
    unusual = data[data["is_unusual"]]
    spikes = int((unusual["direction"] == "spike").sum())
    drops = int((unusual["direction"] == "drop").sum())
    title = f"{len(unusual)} unusual months in {years[0]} to {years[1]}: {spikes} spikes and {drops} drops"
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=data["month"], y=data["accidents"], mode="lines",
                             name="Accidents", line=dict(color=BLUE, width=1.5)))
    fig.add_trace(go.Scatter(x=data["month"], y=data["expected"], mode="lines",
                             name="Expected", line=dict(color=GREY, width=1, dash="dash")))
    for direction, symbol, color in [("spike", "triangle-up", ORANGE), ("drop", "triangle-down", SKY)]:
        part = unusual[unusual["direction"] == direction]
        fig.add_trace(go.Scatter(
            x=part["month"], y=part["accidents"], mode="markers", name=f"Unusual {direction}",
            marker=dict(symbol=symbol, size=10, color=color, line=dict(color="black", width=1)),
        ))
    fig.update_layout(title=title, xaxis_title="Month", yaxis_title="Accidents reported",
                      legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("The blue line is monthly accidents and the dashed line is what trend and season predict. Markers show months far from that.")


def spike_chart(recent: pd.DataFrame, dimension: str, min_recent: int, only_spikes: bool) -> None:
    """Draw the change in the last 12 months versus the earlier baseline."""
    data = recent[(recent["dimension"] == dimension) & (recent["recent_12m"] >= min_recent)]
    data = data[data["category"] != "Not recorded"]
    if only_spikes:
        data = data[data["is_spike"]]
    data = data.nlargest(15, "change_pct").copy()
    if data.empty:
        st.info("No categories match these filters. Try a lower minimum count or turn off the spikes-only option.")
        return
    data["Status"] = data["is_spike"].map({True: "Clear spike", False: "Not a clear spike"})
    lead = data.iloc[0]
    title = f"{lead['category']} is up {lead['change_pct']:.0f}% in the last 12 months ({lead['recent_12m']:.0f} vs about {lead['expected_12m']:.1f} expected)"
    fig = px.bar(
        data.sort_values("change_pct"), x="change_pct", y="category", orientation="h",
        color="Status", color_discrete_map={"Clear spike": ORANGE, "Not a clear spike": GREY},
        labels={"change_pct": "Change vs expected (%)", "category": dimension},
        hover_data={"recent_12m": True, "expected_12m": True, "z_score": True},
        title=title,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Bars show how far the last 12 months sit above the earlier pattern. Orange bars are statistically clear spikes. Small counts can swing a lot.")


def show_findings(findings: list) -> None:
    """List each finding with its evidence and what to do about it."""
    for item in findings:
        st.markdown(f"**{item['statement']}**")
        st.write(item["evidence"])
        st.write(f"What to do: {item['so_what']}")


def show_expanders(method_notes: list, caveats: list) -> None:
    """Show the methods and the data limits in expanders."""
    with st.expander("How it was done"):
        for note in method_notes:
            st.markdown(f"**{note['method']}**")
            st.write(f"Why: {note['why']}")
            st.write(f"Other option: {note['alternative']}")
    with st.expander("Limits of this data"):
        for caveat in caveats:
            st.markdown(f"- {caveat}")


def main() -> None:
    """Build the whole dashboard page."""
    tables = load_tables()
    findings = load_findings()

    st.title("Rail Accident Hotspots and Causes")
    st.write(
        "Which causes, places and equipment types are linked to the most train accidents, "
        "and have any types spiked recently? "
        f"Data covers {findings['date_range']}."
    )
    st.info(findings["headline"])
    show_metrics(findings["metrics"])

    monthly = tables["monthly_counts"]
    recent = tables["recent_vs_baseline"]
    counties = tables["county_counts"]

    st.sidebar.header("Filters")
    st.sidebar.subheader("Where")
    state_options = ["All states"] + sorted(counties["state_abbr"].unique())
    county_state = st.sidebar.selectbox("State for the county chart", state_options)
    county_n = st.sidebar.slider("Counties to show", 5, 25, 10)
    st.sidebar.subheader("What")
    dimension = st.sidebar.selectbox("Group accidents by", ["Accident type", "Cause", "Equipment type", "Track type"])
    top_n = st.sidebar.slider("Categories to show", 5, 20, 10)
    st.sidebar.subheader("When")
    first_year, last_year = int(monthly["month"].dt.year.min()), int(monthly["month"].dt.year.max())
    years = st.sidebar.slider("Years for the timeline", first_year, last_year, (first_year, last_year))
    st.sidebar.subheader("Recent spikes")
    spike_dimension = st.sidebar.selectbox("Spike chart groups", sorted(recent["dimension"].unique()))
    min_recent = st.sidebar.slider("Minimum accidents in last 12 months", 0, 50, 5)
    only_spikes = st.sidebar.checkbox("Show clear spikes only", value=False)

    st.header("Where accidents happen")
    state_map(tables["state_counts"])
    county_chart(counties, county_state, county_n)

    st.header("What kinds of accidents happen")
    category_chart(tables, dimension, top_n)

    st.header("When accidents look unusual")
    timeline_chart(monthly, years)
    spike_chart(recent, spike_dimension, min_recent, only_spikes)

    st.header("What this means")
    show_findings(findings["findings"])
    show_expanders(findings["method_notes"], findings["caveats"])


main()

from credits import show_data_credit
show_data_credit()
