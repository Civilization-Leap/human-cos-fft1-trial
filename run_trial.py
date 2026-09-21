#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "tools"))
import run_fft1b

parser = argparse.ArgumentParser(
    description="Run the bundled fixed Mock S5→S8 narrow FFT-1 preview."
)
parser.add_argument(
    "--output", required=True, type=Path, help="new, nonexistent output directory"
)
parser.add_argument(
    "--host-note",
    required=True,
    help="sanitized host provenance and interventions; no credentials",
)
args = parser.parse_args()
sys.argv = [
    sys.argv[0],
    "--source-bundle",
    str(root / "runtime-source.zip"),
    "--output",
    str(args.output),
    "--host-note",
    args.host_note,
]
sys.exit(run_fft1b.main())
