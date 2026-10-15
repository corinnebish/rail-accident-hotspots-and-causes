"""Rail accident hotspots and causes: cleans Form 54 data and builds dashboard tables."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

RAW_DIR = Path("data/raw")
OUT_DIR = Path("data/processed")

BASE_COLUMNS = [
    "Reporting Railroad Code", "Accident Number", "Date",
    "Accident Type", "Equipment Type", "Track Type",
    "State Abbreviation", "State Name", "County Name",
]
NOT_RECORDED = "Not recorded"


def find_cause_column(columns):
    """Pick the best primary-cause column by name, or None if there is none."""
    # "Causing Car" columns describe rail cars, not accident causes, so skip them
    candidates = [c for c in columns if "cause" in c.lower() and "causing" not in c.lower()]
    rules = [
        lambda n: "primary" in n and "desc" in n,
        lambda n: "desc" in n,
        lambda n: "primary" in n,
        lambda n: True,
    ]
    for rule in rules:
        for col in candidates:
            if rule(col.lower()):
                return col
    return None


def load_raw():
    """Read every CSV in data/raw/ using only the columns we need."""
    files = sorted(RAW_DIR.glob("*.csv"))
    frames = []
    cause_col = None
    for path in files:
        header = pd.read_csv(path, nrows=0).columns
        cause_col = find_cause_column(header)
        use = BASE_COLUMNS + ([cause_col] if cause_col else [])
        frames.append(pd.read_csv(path, usecols=use, dtype=str, low_memory=False))
        print(f"Loaded {path.name}: {len(frames[-1]):,} rows")
    return pd.concat(frames, ignore_index=True), cause_col


def clean(df, cause_col):
    """Fix types, drop duplicates and unusable rows, and print what was removed."""
    print(f"Rows before cleaning: {len(df):,}")
    text_cols = [c for c in df.columns if c != "Date"]
    for col in text_cols:
        df[col] = df[col].str.strip()

    before = len(df)
    df = df.drop_duplicates()
    print(f"Removed {before - len(df):,} exact duplicate rows (same record repeated).")

    before = len(df)
    df = df.drop_duplicates(subset=["Reporting Railroad Code", "Accident Number", "Date"])
    print(f"Removed {before - len(df):,} rows sharing railroad, accident number and date "
          "(the same accident filed twice).")

    before = len(df)
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
    df = df.dropna(subset=["Date"])
    print(f"Removed {before - len(df):,} rows with a missing or unreadable date "
          "(cannot be placed on a timeline).")

    before = len(df)
    df = df.dropna(subset=["State Abbreviation"])
    print(f"Removed {before - len(df):,} rows with no state (cannot be mapped).")

    label_cols = ["Accident Type", "Equipment Type", "Track Type", "County Name"]
    if cause_col:
        label_cols.append(cause_col)
    for col in label_cols:
        missing = int(df[col].isna().sum())
        df[col] = df[col].fillna(NOT_RECORDED)
        print(f"Filled {missing:,} missing values in '{col}' with '{NOT_RECORDED}' (rows kept).")

    df["Month"] = df["Date"].dt.to_period("M")
    return df.reset_index(drop=True)


def count_table(df, col, name):
    """Count accidents per category and add each category's share of the total."""
    table = df.groupby(col).size().reset_index(name="accidents")
    table = table.rename(columns={col: name})
    table["share_pct"] = (100 * table["accidents"] / table["accidents"].sum()).round(2)
    return table.sort_values("accidents", ascending=False).reset_index(drop=True)


def state_table(df):
    """Count accidents per state for the map."""
    table = (df.groupby(["State Abbreviation", "State Name"]).size()
             .reset_index(name="accidents"))
    table.columns = ["state_abbr", "state_name", "accidents"]
    table["state_name"] = table["state_name"].str.title()
    table["share_pct"] = (100 * table["accidents"] / table["accidents"].sum()).round(2)
    return table.sort_values("accidents", ascending=False).reset_index(drop=True)


def county_table(df, top_n=50):
    """Count accidents per county (a county name repeats across states, so group by both)."""
    table = (df[df["County Name"] != NOT_RECORDED]
             .groupby(["State Abbreviation", "County Name"]).size()
             .reset_index(name="accidents"))
    table.columns = ["state_abbr", "county_name", "accidents"]
    table["county_name"] = table["county_name"].str.title()
    return table.sort_values("accidents", ascending=False).head(top_n).reset_index(drop=True)


def monthly_counts(df):
    """Count accidents for every month in range, filling empty months with zero."""
    counts = df.groupby("Month").size()
    full = pd.period_range(counts.index.min(), counts.index.max(), freq="M")
    return counts.reindex(full, fill_value=0)


def detect_unusual_months(counts):
    """Flag months far from the trend-plus-season pattern using a robust z-score."""
    # STL splits a series into trend, yearly pattern and leftover noise
    fit = STL(counts.astype(float), period=12, robust=True).fit()
    residual = fit.resid
    median = np.median(residual)
    mad = np.median(np.abs(residual - median))
    # MAD (median absolute deviation) is not thrown off by the very outliers we hunt
    z = 0.6745 * (residual - median) / mad if mad > 0 else residual * 0
    out = pd.DataFrame({
        "month": counts.index.to_timestamp(),
        "accidents": counts.values,
        "expected": (fit.trend + fit.seasonal).round(1).values,
        "robust_z": np.round(z.values, 2),
    })
    out["is_unusual"] = out["robust_z"].abs() > 3.5
    out["direction"] = np.where(out["robust_z"] > 0, "spike", "drop")
    return out


def monthly_by_type(df):
    """Monthly accident counts per accident type for the timeline filter."""
    table = df.groupby([df["Month"].dt.to_timestamp(), "Accident Type"]).size()
    table = table.reset_index(name="accidents")
    table.columns = ["month", "accident_type", "accidents"]
    return table


def recent_vs_baseline(df, col, dimension):
    """Compare the latest 12 months with the 36 months before, per category."""
    last = df["Month"].max()
    recent_start = last - 11
    base_start = max(recent_start - 36, df["Month"].min())
    base_months = (recent_start - base_start).n
    recent = df[df["Month"] >= recent_start].groupby(col).size()
    base = df[(df["Month"] >= base_start) & (df["Month"] < recent_start)].groupby(col).size()
    table = pd.DataFrame({"recent_12m": recent, "baseline": base}).fillna(0)
    # Scale the baseline to a 12-month equivalent so the two are comparable
    table["expected_12m"] = table["baseline"] / base_months * 12
    table = table[table["expected_12m"] > 0].copy()
    table["change_pct"] = (100 * (table["recent_12m"] / table["expected_12m"] - 1)).round(1)
    # Poisson rule of thumb: count noise is about the square root of the count
    table["z_score"] = ((table["recent_12m"] - table["expected_12m"])
                        / np.sqrt(table["expected_12m"])).round(2)
    table["is_spike"] = (table["change_pct"] >= 25) & (table["z_score"] >= 3)
    table["expected_12m"] = table["expected_12m"].round(1)
    table = table.drop(columns="baseline").reset_index()
    table = table.rename(columns={col: "category"})
    table.insert(0, "dimension", dimension)
    return table.sort_values("z_score", ascending=False).reset_index(drop=True)


def top_known(table, name_col):
    """Return the top row that is not the 'Not recorded' placeholder."""
    known = table[table[name_col] != NOT_RECORDED]
    return known.iloc[0]


def build_findings(df, states, types, equipment, cause, counties, unusual, spikes, cause_col):
    """Assemble the findings.json content from computed tables only."""
    total = len(df)
    first, last = df["Date"].min(), df["Date"].max()
    top_state = states.iloc[0]
    top_type = types.iloc[0]
    top_equip = top_known(equipment, "equipment_type")
    top_three_share = round(states.head(3)["share_pct"].sum(), 1)
    top_county = counties.iloc[0]
    flagged = unusual[unusual["is_unusual"]]
    spiking = spikes[spikes["is_spike"]]
    last_month = df["Month"].max()

    metrics = [
        {"label": "Accidents analyzed", "value": f"{total:,}",
         "explanation": "Reports left after removing duplicates and rows with no date or state."},
        {"label": "Top state", "value": f"{top_state['state_name']} ({top_state['share_pct']}%)",
         "explanation": "The state with the most reported accidents, and its share of all reports."},
        {"label": "Top accident type", "value": f"{top_type['accident_type']} ({top_type['share_pct']}%)",
         "explanation": "The most common kind of accident in the reports."},
        {"label": "Top equipment type", "value": f"{top_equip['equipment_type']} ({top_equip['share_pct']}%)",
         "explanation": "The kind of train or equipment involved most often, among reports that name one."},
        {"label": "Unusual months", "value": str(len(flagged)),
         "explanation": "Months whose count was far from what trend and season predict."},
        {"label": "Categories spiking now", "value": str(len(spiking)),
         "explanation": "Types, equipment or causes with a clearly higher last 12 months than before."},
    ]

    findings = [
        {"statement": f"Accidents cluster in a few states: the top three hold {top_three_share}% of reports.",
         "evidence": f"{top_state['state_name']} leads with {int(top_state['accidents']):,} reports. "
                     f"The top county is {top_county['county_name']}, {top_county['state_abbr']} "
                     f"with {int(top_county['accidents']):,}.",
         "so_what": "Focus inspections and safety reviews on the leading states and counties first."},
        {"statement": f"{top_type['accident_type']} is the most common accident type.",
         "evidence": f"It makes up {top_type['share_pct']}% of reports ({int(top_type['accidents']):,}).",
         "so_what": "Match safety rules and training to the accident types that happen most often."},
        {"statement": f"{top_equip['equipment_type']} is involved most often among reports that name equipment.",
         "evidence": f"It appears in {top_equip['share_pct']}% of all reports "
                     f"({int(top_equip['accidents']):,}).",
         "so_what": "Check whether this equipment simply runs the most, then target its maintenance rules."},
    ]

    if cause is not None:
        top_cause = top_known(cause, "cause")
        findings.append({
            "statement": "One cause stands out above the rest.",
            "evidence": f"'{top_cause['cause']}' is the leading recorded cause "
                        f"({top_cause['share_pct']}% of reports, {int(top_cause['accidents']):,}).",
            "so_what": "Put prevention effort behind the leading causes before smaller ones."})
    if len(flagged):
        worst = flagged.loc[flagged["robust_z"].abs().idxmax()]
        findings.append({
            "statement": f"{len(flagged)} months were unusual compared with the normal pattern.",
            "evidence": f"The largest outlier is {worst['month']:%B %Y}, a {worst['direction']} "
                        f"with {int(worst['accidents'])} reports against about {worst['expected']} expected.",
            "so_what": "Look into what happened in flagged months, such as weather, events or reporting changes."})
    elif len(findings) < 3:
        findings.append({"statement": "No month was unusual.", "evidence": "All months fell within the expected range.",
                         "so_what": "Keep monitoring monthly counts."})

    if len(spiking):
        s = spiking.iloc[0]
        spike_text = (f"{s['category']} ({s['dimension']}) is up {s['change_pct']}% in the last 12 months "
                      f"({int(s['recent_12m'])} vs about {s['expected_12m']} expected).")
    else:
        spike_text = "No type, equipment or cause rose sharply in the last 12 months."
    headline = (f"{top_state['state_name']} and {top_type['accident_type'].lower()} accidents lead "
                f"{total:,} reports from {first:%Y} to {last:%Y}. {spike_text}")

    cause_note = (f"The cause column used was '{cause_col}'." if cause_col
                  else "No cause column was found in the file, so cause results are not shown.")
    return {
        "headline": headline,
        "rows_analyzed": int(total),
        "date_range": f"{first:%Y-%m-%d} to {last:%Y-%m-%d}",
        "metrics": metrics,
        "findings": findings,
        "method_notes": [
            {"method": "SQL-style aggregation",
             "why": "Group-and-count tables answer which causes, places and equipment appear most.",
             "alternative": "A regression model could weigh factors together, but counts are easier to explain and enough here."},
            {"method": "Geographic analysis",
             "why": "Counting by state and county shows where accidents cluster on a map.",
             "alternative": "Exact coordinates would allow finer clusters, but this data only gives state and county."},
            {"method": "Anomaly detection (STL plus robust z-score)",
             "why": "STL removes trend and yearly season, so only truly odd months are flagged.",
             "alternative": "A simple average and standard deviation is easier, but trends and seasons would cause false alarms."},
            {"method": "Recent versus baseline comparison",
             "why": "Comparing the last 12 months with the prior 3 years shows which categories are rising.",
             "alternative": "A full forecast model could be used, but it needs more tuning and is harder to explain."},
        ],
        "caveats": [
            "Counts are raw totals. They are not adjusted for how many trains or miles each state or railroad runs.",
            "Reporting rules and dollar thresholds can change over time, which can move counts without any real change in safety.",
            "The most recent months may be incomplete because reports arrive late.",
            f"Missing equipment, cause or county values were labeled '{NOT_RECORDED}' and are left out of the leading-category findings.",
            "County names repeat across states, so counties are always paired with their state.",
            cause_note,
            "Accidents here are those reported on Form 54 and do not cover every incident type, such as some crossing events.",
        ],
    }


def main():
    """Run the full pipeline and save dashboard tables."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw, cause_col = load_raw()
    df = clean(raw, cause_col)

    states = state_table(df)
    types = count_table(df, "Accident Type", "accident_type")
    equipment = count_table(df, "Equipment Type", "equipment_type")
    tracks = count_table(df, "Track Type", "track_type")
    counties = county_table(df)

    counts = monthly_counts(df)
    unusual = detect_unusual_months(counts)

    spike_parts = [recent_vs_baseline(df, "Accident Type", "Accident type"),
                   recent_vs_baseline(df, "Equipment Type", "Equipment type")]
    cause = None
    if cause_col:
        cause = count_table(df, cause_col, "cause")
        spike_parts.append(recent_vs_baseline(df, cause_col, "Cause"))
    spikes = pd.concat(spike_parts, ignore_index=True)

    tables = {
        "state_counts": states, "county_counts": counties,
        "accident_type_counts": types, "equipment_type_counts": equipment,
        "track_type_counts": tracks, "monthly_counts": unusual,
        "monthly_by_type": monthly_by_type(df), "recent_vs_baseline": spikes,
    }
    if cause is not None:
        tables["cause_counts"] = cause.head(30)
    for name, table in tables.items():
        table.to_csv(OUT_DIR / f"{name}.csv", index=False)
        print(f"Saved {name}.csv ({len(table):,} rows)")

    findings = build_findings(df, states, types, equipment, cause, counties,
                              unusual, spikes, cause_col)
    with open(OUT_DIR / "findings.json", "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2)
    print("Saved findings.json")
    print(findings["headline"])


if __name__ == "__main__":
    main()
