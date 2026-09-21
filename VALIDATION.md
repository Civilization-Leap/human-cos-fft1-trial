# Preview.2 validation record

This is a sanitized record of project-controlled engineering validation for the exact `v0.1.0-fft1-preview.2` distribution. The reviewer was an AI assistant involved in the project's implementation and review process. This was **not an independent external reproduction**.

## Bound artifact

- Public candidate commit: `5f30bb43ea311ed2410e44357ebc0e3f80cd1e3d`
- `FFT1-distribution.zip` SHA-256: `0efde6884170bbd881a119b6e90b19225959c01693b01d44afc609b930110310`
- Pinned public source snapshot: `ca93213174544f2ce5c3f862564a6cd5a3f0386f`
- Pinned runtime subtree: `a19c96d76072a1bbf7e94bba03b372cb963c3593`

The package itself is unchanged by this record. Raw host evidence and internal engineering material remain private.

## Execution and intake

A private GitHub-hosted Ubuntu 24.04 runner executed the exact distribution in workflow run `35567763250`. The retained artifact digest was `sha256:207d55d3cbb96e522f02f4e67443d8b148319d24a3b43f33c4640a4bf18f4aed`.

The project-controlled intake verified:

- two actual Docker executions;
- the exact ordered 12-transition trace in each execution;
- all 7 required negative probes as observed rejections;
- PostgreSQL persistence and production readback across 26 recorded tables in each execution;
- all 26 recorded commands exiting with status 0;
- owned containers, networks and volumes absent after cleanup;
- bounded semantic equivalence recomputed from retained evidence and matching the report;
- a mutated `FINAL_SYNTHESIS` result rejected even after its result hash was recomputed.

Raw run bytes were not identical because bounded fields can vary. The accepted repeatability result is semantic equivalence under the documented policy, not byte-for-byte determinism.

The run recorded resolved external image identities and build evidence. The package still uses environment-dependent upstream image tags rather than pinning every external image by digest, so future downloads are not asserted to be identical to this validation environment.

## Decision and limits

`PROJECT_CONTROLLED_PHYSICAL_RUN_AND_INTAKE = PASS`

This decision supports opening preview.2 for falsification and reproduction attempts. It does **not** establish:

- independent or external validation;
- public-trial validation;
- live-provider behavior (`NOT_RUN`);
- real-case effectiveness (`REAL_CASE_EFFECTIVENESS = NOT_DEMONSTRATED`);
- readiness of the complete Human-COS system;
- reality-execution, Final Synthesis or other authority outside the fixed Mock S5→S8 narrow trial.

N-3 and the documented same-UID output-directory acquisition races remain OPEN. The public result remains a narrow preview whose most valuable next evidence is an external reproducibility failure, false-positive success, unclear boundary or missing test case.
