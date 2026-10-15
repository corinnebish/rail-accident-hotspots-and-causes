"""Downloads the raw data used in this project into data/raw/.

Run:  python download_data.py
The files are public. See README.md for the source and license.
"""
import io
import zipfile
from pathlib import Path

import requests

SOURCES = {
    "Rail_Equipment_Accident_Incident_Data__Form_54_.csv": "https://data.transportation.gov/api/views/85tf-25kj/rows.csv?accessType=DOWNLOAD"
}
RAW = Path(__file__).parent / "data" / "raw"


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        print(f"Downloading {name} ...")
        resp = requests.get(url, timeout=120, headers={"User-Agent": "portfolio-project"})
        resp.raise_for_status()
        (RAW / name).write_bytes(resp.content)
        if name.lower().endswith(".zip"):
            zipfile.ZipFile(io.BytesIO(resp.content)).extractall(RAW)
    print("Done.")


if __name__ == "__main__":
    main()
