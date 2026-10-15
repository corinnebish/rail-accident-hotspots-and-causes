"""Shows where the data came from and its license, at the bottom of the dashboard."""
import json
from pathlib import Path

import streamlit as st


def show_data_credit() -> None:
    info = json.loads((Path(__file__).parent / "data_credit.json").read_text(encoding="utf-8"))
    st.divider()
    st.caption(
        f"**Data source:** [{info['name']}]({info['landing_url']}), published by {info['publisher']}. "
        f"**License:** {info['license']}. This project is an independent portfolio piece and is not "
        "endorsed by the data publisher."
    )
