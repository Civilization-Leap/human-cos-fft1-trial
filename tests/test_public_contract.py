import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREVIEW_RELEASE = "v0.1.0-fft1-preview.2"
PREVIEW_SHA256 = "0efde6884170bbd881a119b6e90b19225959c01693b01d44afc609b930110310"


def test_agent_result_schema_tracks_preview2_release() -> None:
    schema = json.loads((ROOT / "agent_test_result.schema.json").read_text(encoding="utf-8"))
    properties = schema["properties"]

    assert properties["schema_version"]["const"] == "1.2"
    assert properties["target"]["properties"]["release"]["const"] == PREVIEW_RELEASE
    assert (
        properties["target"]["properties"]["distribution_sha256"]["const"]
        == PREVIEW_SHA256
    )

    checksum_entries = [
        line.split()
        for line in (ROOT / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(
        parts[0] == PREVIEW_SHA256
        and parts[-1].lstrip("*") == "FFT1-distribution.zip"
        for parts in checksum_entries
    )
