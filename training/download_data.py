"""Tải CSV chính thức từ UCI và ghi checksum để xác định dữ liệu đã dùng."""

import hashlib
import json
from pathlib import Path

import httpx

from backend.core.config import ROOT

DATASET_URL = "https://archive.ics.uci.edu/api/dataset?id=891"


def download(output: Path) -> Path:
    """Lấy URL CSV từ API UCI và lưu nguồn gốc cùng checksum."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        metadata = client.get(DATASET_URL)
        metadata.raise_for_status()
        payload = metadata.json()["data"]
        url = payload["data_url"]
        if not url.startswith("https://archive.ics.uci.edu/"):
            raise ValueError("URL dữ liệu không thuộc kho UCI.")
        response = client.get(url)
        response.raise_for_status()
    output.write_bytes(response.content)
    output.with_suffix(".source.json").write_text(
        json.dumps(
            {
                "dataset_id": 891,
                "metadata_url": DATASET_URL,
                "csv_url": url,
                "sha256": hashlib.sha256(response.content).hexdigest(),
                "citation": "CDC Diabetes Health Indicators (2017), DOI: 10.24432/C53919",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return output


if __name__ == "__main__":
    print(download(ROOT / "data/raw/diabetes_binary_health_indicators_BRFSS2015.csv"))
