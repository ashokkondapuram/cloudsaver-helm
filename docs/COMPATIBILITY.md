# Application compatibility and deployment gates

The charts were extracted from the local Helm work against application commit `6fc05bb3215a300bbec3b05218614dce35a4403d` in `ashokkondapuram/project`. They target the current documented CloudSaver 1.3.0 / Platform 1.0.0 configuration contracts. No application code or credentials are copied into this repository.

Static Helm and Kubernetes validation proves manifest structure/configuration contracts. It does not prove that the source application's current images start successfully.

The upstream snapshot has confirmed Platform blockers:

- `identity/app.py` imports `app.runtime`, but the isolated Platform Dockerfile does not include CloudSaver's `app` package.
- Platform runtime/migration code still reads legacy `CLOUDSAVER_IDENTITY_DATABASE_URL` / `CLOUDSAVER_IDENTITY_MIGRATION_URL` in places, while its separate Compose stack supplies the new `PLATFORM_*` settings. The charts deliberately supply the intended new names.
- IdentityService still reads legacy environment/provider-scope settings; without correcting it, the new production setting does not control production key prefixes as intended.
- A source compatibility test exposed `ImportError: cannot import name 'TIERS' from 'identity.domain'`. The service still expects a three-argument `normalize_scope_items` interface, while the updated domain defines a four-argument interface. Billing/store changes and migration completeness must be reviewed together; replacing one missing constant is not a sufficient fix.
- The separate Compose stack omits the workforce operator tenant ID from identity-service's environment. The Helm chart explicitly supplies `PLATFORM_OPERATOR_TENANT_ID`.

The local application checkout retains the earlier limited runtime/configuration edits; those edits are not part of this chart repository and do not resolve every blocker above. No complete application fix, release image build or live migration was performed as part of the chart extraction. Use application images built from a reviewed, corrected source revision, and record their immutable digests in production values.

Before production installation, validate the complete isolated Platform image (no source bind mounts), migration paths on disposable PostgreSQL, Entra token audience/roles, directory projection and key lifecycle. Current application docs also reference billing migration/import components that are absent in this snapshot: keep billing disabled until that path is complete and tested.

Cloud scanning on AKS additionally needs a verified credential implementation. Current scanners instantiate ManagedIdentityCredential, so service-account annotations alone do not enable the native AKS Workload Identity token exchange. Configure an application-supported identity path and least-privilege customer roles before live scans.

None of these issues is concealed by Helm readiness probes or by successful schema validation. The charts are ready for review and integration testing; production application acceptance is outstanding.
