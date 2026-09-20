#!/usr/bin/env python3
import sys
from pathlib import Path
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / 'tools'))
import run_fft1b
if any(a == '--repo' or a.startswith('--repo=') or a == '--source-bundle' or a.startswith('--source-bundle=') for a in sys.argv[1:]):
    raise SystemExit('This package uses only its bundled fixed source.')
sys.argv[1:1] = ['--source-bundle', str(root / 'runtime-source.zip')]
sys.exit(run_fft1b.main())
