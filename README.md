# Rail Accident Hotspots and Causes

A data analysis of 197,608 US rail accident reports from 1975 to 2026 that finds where, how, and with what equipment accidents cluster, and which types are rising now.

**[Open the live dashboard](https://pc-rail-accident-hotspots-and-causes-2uen7v5wuq-uc.a.run.app)**

## The business problem

Railroads and safety agencies need to know which causes, places, and equipment types are tied to the most accidents, so they can target safer operating rules. They also need to spot categories that have recently risen before those changes are approved.

## Question

> Which causes, locations, and equipment types are linked to the most train accidents, and have certain types spiked recently?

## Key findings

- Accidents cluster in a few places. Texas leads with 19,067 reports (9.65%), and the top three states hold 24.4% of all reports. Cook, IL is the top county with 8,801 reports.
- Derailment is the most common accident type, at 70.38% of reports (139,082).
- Freight Train appears in 52.64% of reports (104,016). This may partly reflect how much freight trains run, which the data does not measure.
- Rear end collision is up 129.4% in the last 12 months, with 13 reports against about 5.7 expected. In total, 9 categories are rising now.
- 48 months were unusual compared with the normal pattern. The largest was October 1976, with 1,049 reports against about 846.7 expected.

## How it was done

- SQL-style aggregation: grouped and counted reports by state, county, accident type, equipment, and cause. Simple counts show what appears most often and are easy to explain to non-technical readers.
- Geographic analysis: counted accidents by state and county to show where they cluster. The data gives only state and county, not exact locations.
- Anomaly detection with STL and a robust z-score: STL removes the long-term trend and yearly seasonal pattern, so only months that are truly unusual get flagged. This avoids false alarms from normal ups and downs.
- Recent versus baseline comparison: compared the last 12 months with the prior 3 years to find categories that are rising.

Methods used: SQL-style aggregation, geographic analysis, anomaly detection.

## Data source and license

- **Dataset:** [Rail Equipment Accident/Incident Data (Form 54)](https://data.transportation.gov/Railroads/Rail-Equipment-Accident-Incident-Data-Form-54-/85tf-25kj)
- **Publisher:** Federal Railroad Administration (U.S. Department of Transportation)
- **License:** Public Domain U.S. Government
- The data is public and unmodified in `data/raw/` (too large for the repo - run `python download_data.py` to fetch it).
- This is an independent portfolio project. It is not endorsed by the data publisher.

## Limits of this analysis

- Counts are raw totals. They are not adjusted for how many trains or miles each state or railroad runs.
- Reporting rules and dollar thresholds can change over time, which can move counts without any real change in safety.
- The most recent months may be incomplete because reports arrive late.
- Missing equipment, cause or county values were labeled 'Not recorded' and are left out of the leading-category findings.
- County names repeat across states, so counties are always paired with their state.
- The cause column used was 'Primary Accident Cause Code'.
- Accidents here are those reported on Form 54 and do not cover every incident type, such as some crossing events.

## What I would do next

- Adjust counts by train miles or traffic volume, since raw totals do not show whether a state or railroad is simply bigger. This would show true risk rates.
- Check the most recent months before trusting the spikes, because late-arriving reports can make recent counts look low or change later. Also check whether reporting rules changed, since that can shift counts without any real change in safety.
- Look up the meaning of the cause code 'T110' in the official codebook before acting on it. The data shows its count but not its full description here. Also note that these reports cover only the Form 54 incident types, so other incidents are not included.

## Run it yourself

```bash
pip install -r requirements.txt
python download_data.py
python analysis.py        # cleans the data and builds data/processed/
streamlit run app.py      # opens the dashboard
```

## Project layout

```
analysis.py        cleaning + analysis, writes data/processed/
app.py             Streamlit dashboard (reads data/processed/ only)
credits.py         shows the data source and license on the dashboard
data/raw/          the public source data
data/processed/    small tables the dashboard uses
tests/             smoke test: the dashboard opens without errors
Dockerfile         how the dashboard is packaged for Google Cloud Run
```

## Redeploying

The dashboard runs on Google Cloud Run. To redeploy after a change, open the **Actions** tab, choose **Redeploy to Cloud Run**, and press **Run workflow**. It needs a repository secret named `GCP_SA_KEY` (a Google Cloud service account key that can deploy to Cloud Run).
