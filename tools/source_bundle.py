"""Apache-2.0 distribution candidate: fixed original blobs, no Git client at runtime.

The inventory digest is a trust anchor in this reviewed harness, not a signature.
A publisher must distribute this harness and its outer SHA through a trusted channel.
"""

import argparse
import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path

INVENTORY_DIGEST = "498ad5917a1d1aea756a7cbf11074424e540789b9a7d31b9a7bc529de5e7bec9"
HERE = Path(__file__).resolve().parent
TOOL_FILES = (
    "source_bundle.py",
    "source_inventory.json",
    "run_fft1b.py",
    "verify_fft1b.py",
    "compare_repeat.py",
    "repeat_policy.json",
    "REPEATABILITY_POLICY.md",
    "README_ZH.md",
    "README_EN.md",
)


def inventory():
    raw = (HERE / "source_inventory.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != INVENTORY_DIGEST:
        raise ValueError("source inventory trust anchor mismatch")
    return json.loads(raw)


def verify_blob(data, entry):
    digest = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if len(data) != entry["size"] or digest != entry["sha"]:
        raise ValueError("source blob mismatch: " + entry["path"])


def zip_entry(name, data):
    info = zipfile.ZipInfo(name, (2026, 9, 16, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info, data


def source_bytes(root):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for entry in inventory()["files"]:
            path = root / entry["path"]
            # Reject symlinks in every component, including the supplied root.
            if any(p.is_symlink() for p in (path, *path.parents)):
                raise ValueError("symlink in source path")
            data = path.read_bytes()
            verify_blob(data, entry)
            archive.writestr(*zip_entry(entry["path"], data))
    return output.getvalue()


def export_bundle(bundle, target):
    doc = inventory()
    expected = {e["path"]: e for e in doc["files"]}
    # Validate every entry before creating any source output.
    contents = {}
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise ValueError("source bundle inventory mismatch")
        for info in archive.infolist():
            entry = expected[info.filename]
            mode = info.external_attr >> 16
            if info.is_dir() or stat.S_ISLNK(mode) or info.file_size != entry["size"]:
                raise ValueError("source bundle entry type/size mismatch")
            data = archive.read(info)
            verify_blob(data, entry)
            contents[info.filename] = data
    target.mkdir()  # never merge with an existing directory
    for name, data in contents.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    (target / ".human-cos-checked-out-commit").write_text(doc["commit"] + "\n")
    identity = {
        "commit": doc["commit"],
        "tree": doc["tree"],
        "export": "selected runtime blobs verified against the pinned public candidate inventory",
        "inventory_sha256": INVENTORY_DIGEST,
        "archive_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "build_marker": ".human-cos-checked-out-commit",
    }
    (target.parent / "source-identity.json").write_text(
        json.dumps(identity, indent=2) + "\n"
    )


NOTICE = """# Human-COS FFT-1 Apache-2.0 release candidate

Not yet publicly released. Original project source, tools and documentation in
this package are licensed under Apache-2.0. See LICENSE, NOTICE and LICENSE_SCOPE.md.
Third-party terms are unchanged. Supported behavior is the fixed Mock S5-S8 narrow
chain on a trusted dedicated Docker host. Support limits are not extra license terms.

Extract into a new directory. Requires Python 3.10+, Docker and Compose v2, and
network access for container/dependency downloads. Git and repository login are
not required. No model keys or real-case material are needed.

    python3 run_trial.py --output ../FFT1-run-01 --host-note 'actual host and interventions'

Use a nonexistent output directory. See tools/README_ZH.md for results and cleanup.
Keep raw evidence unchanged and share it privately, not in a public issue: it may
contain host paths and descriptions. No upload happens automatically.
Two same-UID directory acquisition races and N-3 remain OPEN; do not run with a
concurrent output mutator. Live provider NOT_RUN; real-case effectiveness NOT_DEMONSTRATED.

Only selected runtime blobs from the pinned public candidate snapshot are included;
no private Git history or old private evidence is present. This preview.2 candidate
hardens result semantics and evidence binding relative to preview.1. The inventory does
not reconstruct the complete public repository. Obtain the outer archive hash through a
trusted publisher channel: an in-archive manifest is not a signature.
"""


def build(root, output):
    payloads = {
        "runtime-source.zip": source_bytes(root),
        "run_trial.py": (HERE.parent / "run_trial.py").read_bytes(),
        "START_HERE.md": NOTICE.encode(),
    }
    for name in ("LICENSE", "NOTICE", "LICENSE_SCOPE.md"):
        payloads[name] = (root / name).read_bytes()
    for name in TOOL_FILES:
        payloads["tools/" + name] = (HERE / name).read_bytes()
    manifest = {
        name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()
    }
    payloads["PACKAGE_SHA256.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode()
    with zipfile.ZipFile(output, "x") as archive:
        for name, data in sorted(payloads.items()):
            archive.writestr(*zip_entry(name, data))
    return hashlib.sha256(output.read_bytes()).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            {
                "archive": str(args.output),
                "sha256": build(args.source_root, args.output),
                "public_release": False,
            }
        )
    )
