# Chart verification

Verified locally on 2026-10-23 using Helm 3.17.4, kubeconform 0.6.7 and PyYAML 6.0.3.

- Both charts pass `helm lint --strict` with their production example values. The CloudSaver chart also lints with defaults; Platform requires actual Entra settings, so default-only rendering deliberately fails validation.
- 30 render/guard scenarios pass, including default/production topology, optional workers, image digest precedence, renamed resources, secret separation, headless peer services, network policies, TLS and rejected unsafe combinations.
- Kubernetes 1.26.0 strict schema validation: **187 valid resources, 0 invalid, 0 errors, 0 skipped** across the successful scenarios.
- Kubernetes 1.33.0 strict schema validation: **187 valid resources, 0 invalid, 0 errors, 0 skipped** across the successful scenarios.
- Both charts package successfully as chart version 0.1.0.

The resources are repeated renders of test scenarios, not 187 workloads in one release. CI repeats lint, render/guard, strict schema checks and packaging.

No cluster installation, cloud inference/scan, Entra sign-in, database migration or restore drill was performed. An attempted application compatibility check failed on upstream's missing `TIERS` import; see [COMPATIBILITY.md](COMPATIBILITY.md). Application runtime edits and unfinished application tests are excluded from this chart repository.
