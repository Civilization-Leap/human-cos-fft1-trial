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


def test_report_schema_accepts_blocked_and_rejects_false_pass() -> None:
    # Validation fixtures only: these are not execution evidence.
    import copy
    import jsonschema

    schema = json.loads((ROOT / "agent_test_result.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    validator.check_schema(schema)
    report = {
        "schema_version": "1.2",
        "target": {"release": PREVIEW_RELEASE, "distribution_sha256": PREVIEW_SHA256,
                   "source": "PINNED_RELEASE", "public_source_commit": None, "deviations": []},
        "agent": {"product": "synthetic fixture", "model": "not a model run",
                  "operator": "test fixture", "operator_relationship": "UNKNOWN",
                  "prior_project_context": False},
        "access": {"shell": False, "network": False, "docker": False,
                   "repository_write": False, "human_assistance": "synthetic fixture"},
        "test": {"track": "A_EXECUTION_ATTEMPT", "execution_class": "ENVIRONMENT_BLOCKED",
                 "environment": "synthetic fixture", "interventions": []},
        "outcome": {"status": "BLOCKED", "summary": "synthetic fixture",
                    "minimal_reproducer": [], "exit_code": None,
                    "reported_physical_reproduction": None, "reported_cleanup": None,
                    "finding_category": "ENVIRONMENT"},
        "claims": {"ai_agent_used": True, "organizational_independence": "UNKNOWN",
                   "independent_human_validation": False, "live_model_validated": False,
                   "real_case_effectiveness": False, "complete_human_cos_validated": False,
                   "broader_theory_validated": False, "every_safety_boundary_validated": False},
    }
    validator.validate(report)
    review = copy.deepcopy(report)
    review["test"].update(track="C_FIRST_USE_REVIEW", execution_class="REVIEW_ONLY")
    review["outcome"]["status"] = "UNCERTAIN"
    validator.validate(review)
    for path, value in [
        (("target", "release"), "v0.1.0-fft1-preview.1"),
        (("target", "distribution_sha256"), "0" * 64),
        (("outcome", "status"), "PASS"),
        (("claims", "real_case_effectiveness"), True),
    ]:
        mutated = copy.deepcopy(report)
        mutated[path[0]][path[1]] = value
        assert list(validator.iter_errors(mutated)), path
    review["outcome"]["exit_code"] = 0
    assert list(validator.iter_errors(review))
