# Scope of the Apache-2.0 grant

The project owner authorized Apache-2.0 on 2026-09-20 for the original project
code, tools and documentation in the final FFT-1 distribution inventory.

For this runtime source snapshot, the covered project material is:
- src/** (including packaged protocols, schemas and migrations);
- pyproject.toml, uv.lock, README.md, Dockerfile.trial, docker-compose.trial.yml;
- LICENSE, NOTICE and this LICENSE_SCOPE.md.

The detached distribution's original launcher, verification/packaging tools and
accompanying documentation are also covered as identified in its PACKAGE_SHA256.json.
Third-party material remains under its own terms. Dependency references in the
lockfile do not relicense dependency packages, container images or system libraries.
No grant over the rest of the private repository, its history, private evidence,
unrelated publications or other projects is implied by this scoped release.

The fixed Mock S5-S8 narrow support boundary describes tested behavior, not an
additional license restriction. Apache-2.0 permits modification and redistribution
under its terms; changed versions must not be represented as the tested candidate.
