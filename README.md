# CloudSaver Helm charts

Independent Kubernetes deployment charts for [CloudSaver](https://github.com/ashokkondapuram/project). Chart version **0.1.0**, targeting CloudSaver **1.3.0** and Platform **1.0.0** configuration contracts. Application images and databases are managed separately.

| Chart | Workloads | Default replicas |
|---|---|---|
| `charts/cloudsaver` | Gateway, tenant API, scanner API, analytics, notification API, customer dashboard | Gateway/analytics/dashboard: 2; other APIs: 1 |
| `charts/cloudsaver-platform` | Internal identity API and operator portal | Identity: 2; portal: 1 |

The CloudSaver chart also supports opt-in Celery scan workers, one Beat scheduler and a delivery dispatcher. There are no bundled databases, Redis instances, plaintext Secret resources, application code or application credentials.

**Status:** Helm lint, render contract tests, packaging and strict Kubernetes schema validation are verified. No cluster install, database migration, cloud identity, Entra or live scan acceptance is claimed. Read [application compatibility](docs/COMPATIBILITY.md) before deploying the current upstream application snapshot; it has known startup blockers.

## Prerequisites

- Helm 3.17+, Kubernetes 1.26+, a CNI that enforces NetworkPolicy, an ingress controller, DNS and TLS certificates.
- Four published application images from your reviewed source: shared CloudSaver Python image, customer dashboard, Platform identity and Platform portal. Set your own registry repositories and preferably SHA256 image digests. The example domains and UUIDs are placeholders.
- Separate external PostgreSQL 16 databases for CloudSaver and the Platform, and separate external Redis 7 services. Redis must support logical databases 0 and 1 for CloudSaver; cluster mode with only DB 0 is incompatible with this configuration. Configure persistence and `noeviction` for CloudSaver's durable broker/leases.
- Pre-created database owner/runtime roles and pre-existing Kubernetes Secrets, reachable over private networking. Use verified TLS connections (`sslmode=verify-full` for PostgreSQL; `rediss://` for Redis).
- A workforce Entra API registration and confidential portal client, delegated scope, and assigned `PlatformOperator` / `PlatformAuditor` roles. Register `https://<platform-host>/api/auth/callback`; configure audience to the exact access-token `aud` value. Local operator-key login is deliberately excluded.
- A supported cloud credential path, verified from the workload. Current scanner code uses `ManagedIdentityCredential`; adding AKS Workload Identity annotations alone does **not** make it use `WorkloadIdentityCredential`. Implement and validate that application support before enabling live scans on AKS. Do not grant all pods a broadly privileged node identity as a workaround.

## Database preparation

Provision databases and identities outside Helm. Kubernetes Secret values are complete libpq DSNs; URL-encode passwords. CloudSaver's runtime login is `cloudsaver_app` (NOSUPERUSER, NOBYPASSRLS, NOCREATEDB, NOCREATEROLE), with no table ownership or schema-owner inheritance. Its migration login owns the application schema and has the privileges required by the reviewed Alembic migrations. Use a migration owner with `CREATE`/`USAGE` on `public`, and test the migrations against your managed PostgreSQL service.

Platform requires `identity_owner` (database/schema owner), `identity_app` (restricted runtime login), and `identity_retention` (NOLOGIN). Grant `identity_retention` to `identity_owner`; grant runtime CONNECT and revoke PUBLIC access as in upstream `platform/platform-db/init.sh`. The init scripts are provisioning references; these charts do not execute them or create database roles.

Do not recreate an existing database or regenerate its workspace-key pepper. For migration or upgrade, back up **both** databases and test restore first. Preserve database roles, pepper versions and service-token recovery separately from data backups.

## Create namespaces and Secrets

Create namespaces before provisioning their Secrets:

```bash
kubectl create namespace platform
kubectl create namespace cloudsaver
mkdir -m 700 config
cp examples/secrets/*.env.example config/
```

Rename the copied files to remove `.example`, replace every placeholder in `config/`, and set their permissions to 0600. These files are ignored by Git. Never use the examples unchanged. Prefer an external secret manager/controller that materializes the same Secret names/keys.

| Namespace | Existing Secret | Required keys |
|---|---|---|
| `cloudsaver` | `cloudsaver-runtime` | `database-url`, `redis-gateway-url`, `redis-worker-url`, `gateway-token`, `tenant-token`, `scanner-token`, `analytics-token`, `notification-token` |
| `cloudsaver` | `cloudsaver-migration` | `database-url` (schema owner) |
| `platform` | `platform-identity` | `database-url`, `redis-url`, `key-pepper`, `caller-digests` |
| `platform` | `platform-portal` | `caller-token`, `entra-client-secret` |
| `platform` | `platform-migration` | `database-url` (`identity_owner`) |

`caller-digests` is JSON mapping `gateway`, `tenant`, `scanner`, `analytics`, `notification`, and `portal` to SHA256 hex digests of their matching plaintext caller tokens. Use independent cryptographically random tokens. `key-pepper` is securely generated hex containing at least 32 random bytes, retained across restarts/upgrades. The caller-token setup helpers in the application repository can generate the initial material on an operator-controlled machine; do not copy development credentials into production.

Create Secrets from protected files without putting credentials in command arguments:

```bash
kubectl -n cloudsaver create secret generic cloudsaver-runtime --from-env-file=config/cloudsaver-runtime.env
kubectl -n cloudsaver create secret generic cloudsaver-migration --from-env-file=config/cloudsaver-migration.env
kubectl -n platform create secret generic platform-identity --from-env-file=config/platform-identity.env
kubectl -n platform create secret generic platform-portal --from-env-file=config/platform-portal.env
kubectl -n platform create secret generic platform-migration --from-env-file=config/platform-migration.env
```

Use Kubernetes encryption at rest and restrict Secret access with cluster RBAC. Helm never creates these Secrets. Runtime pods reference only their required keys; migration owner DSNs are referenced only by migration Jobs. Frontends receive neither backend runtime DSNs nor key peppers. The migration and runtime Secret names must differ.

## Configure and install

Copy the non-secret production values into the ignored configuration directory:

```bash
cp charts/cloudsaver/values-production.example.yaml config/cloudsaver.yaml
cp charts/cloudsaver-platform/values-production.example.yaml config/platform.yaml
```

Set actual image repositories/digests, domain names, TLS Secret names, Entra tenant/client IDs, delegated API scope, exact token audience and cloud identity identifiers. If using a private registry, set `imagePullSecrets` in **each** chart and provision the corresponding registry Secret in each namespace. A digest overrides the tag.

Align the ingress controller's namespace/pod selectors under `networkPolicy.ingressController` with your controller. Defaults target the `ingress-nginx` namespace and `app.kubernetes.io/component=controller`. Configure controller timeouts for scans (the example uses 180 seconds). TLS Secrets must already exist or be provisioned by your configured certificate controller.

Install Platform first, then CloudSaver:

```bash
helm upgrade --install platform ./charts/cloudsaver-platform \
  --namespace platform --values config/platform.yaml --wait --timeout 15m

helm upgrade --install cloudsaver ./charts/cloudsaver \
  --namespace cloudsaver --values config/cloudsaver.yaml --wait --timeout 15m
```

These commands **run database migrations**. Use them only after reviewing the application compatibility blockers, backups and schema changes. If migrations are managed separately, set `migration.enabled=false` and apply/verify the required schema before installing workloads.

The default identity endpoint is `http://platform-identity-service.platform.svc.cluster.local:8005`. If you change the Platform release name, `fullnameOverride`, namespace or cluster DNS suffix, update `platform.url` in the CloudSaver values. Update Platform's `networkPolicy.cloudsaverNamespaces` if the customer stack uses a different namespace. Release names/fullname overrides are limited to 40 characters.

Only the two web apps receive Ingress resources. Gateway and other APIs remain internal. CloudSaver services are headless so its trusted-caller resolver sees actual pod IPs. Do not replace those services with a public LoadBalancer. NetworkPolicies deny incoming traffic to chart pods except the specified service paths and ingress controller. Policies restrict **ingress only**: restrict DNS, database, Redis, Entra, provider/model and webhook **egress** using your CNI/firewall according to the enabled features. Cross-namespace identity access requires both the namespace and CloudSaver pod selectors.

## Verify and operate

```bash
kubectl -n platform get deployments,pods,services,ingresses,networkpolicies
kubectl -n cloudsaver get deployments,pods,services,ingresses,networkpolicies
kubectl -n platform rollout status deployment/platform-identity-service
kubectl -n platform rollout status deployment/platform-platform-portal
kubectl -n cloudsaver rollout status deployment/cloudsaver-scanner-service
kubectl -n cloudsaver rollout status deployment/cloudsaver-web-dashboard
```

Sign in to the operator portal, create a customer/workspace, add explicitly authorized cloud scopes and issue a restricted workspace key. Validate customer authentication, two-workspace isolation, key revocation, projected directory state and saved history after restart. Verify real cloud access separately before scans.

HTTP workloads have startup, liveness and readiness probes. API liveness is `/healthz`; dependency readiness uses `/readyz`. Portal probes use `/api/healthz`; dashboard probes use `/`. These frontend endpoints do not prove end-to-end API/Entra readiness. Worker processes rely on process exit/restart; no synthetic HTTP readiness is attached to Celery.

Pods run as non-root, drop capabilities, use RuntimeDefault seccomp, disable privilege escalation and use a read-only root filesystem. Writable `/tmp` and Next.js cache paths use bounded `emptyDir`. Service accounts receive no RoleBindings and disable token automount by default. Additional secret refs, mounted CAs, placement and identity annotations can be configured per component. Configure migration image CA trust outside the chart if your external DB requires a private CA; the migration hook must be able to connect independently of release ConfigMaps.

Multi-replica workloads receive PodDisruptionBudgets. Pod placement is operator-controlled through `nodeSelector`, `tolerations` and `affinity`; spread replicas across nodes before claiming node-failure availability. Budget PostgreSQL connections per process, replica and Celery child.

**Portal sessions and pending OAuth state are process-local.** Portal is limited to one replica with `Recreate` updates; upgrades/restarts sign operators out and temporarily interrupt sign-in. Beat also stays at one replica with `Recreate`. Tenant-service is limited to one directory projector. No HA claim is made for these components.

ConfigMap changes roll out pods through a checksum. External Secret rotation does **not** trigger an automatic rollout: coordinate rotation/grace periods, then explicitly restart the affected deployments. Do not regenerate the pepper to rotate a caller token.

Migration hooks run on pre-install/pre-upgrade with no runtime ConfigMap or Kubernetes API token dependency. They use a bounded deadline, no automatic retries and retain failed Job logs for up to 24 hours; successful Jobs are deleted. Use `kubectl logs job/<release>-migrate` in the release namespace after failure. The hook uses the namespace default ServiceAccount with token automount disabled; imagePullSecrets are supplied directly. Ensure namespace-level policies admit the hook's DB egress. Serialize releases yourself; never start concurrent migrations against one database.

Pause scheduling, dispatch and application writes before incompatible migrations. A Helm rollback or `--atomic` rollback does **not** reverse database migrations. Restore/application rollback needs a reviewed compatibility and recovery plan. `helm uninstall` leaves external databases, Redis, TLS Secrets and application Secrets in place; it removes chart workloads and policies. Never use uninstall as a data recovery procedure.

## Optional workers and features

All external-effect features default to disabled. To enable scheduled scans, enable these three components and the feature together:

```yaml
components:
  scan-worker:
    enabled: true
  scan-scheduler:
    enabled: true
  delivery-dispatcher:
    enabled: true
features:
  scheduledScans: true
```

The platform's persisted global settings, workspace plan and schedule must also allow scheduling. Enabling a Helm seed does not overwrite existing directory settings. Interactive Azure jobs require the worker and dispatcher. Delivery requires the dispatcher; automated alerts additionally require delivery. Schema/template guards reject incomplete combinations.

`features.ai` enables advisory configuration; paid model access still requires operator-bound `CLOUDSAVER_AI_TARGETS` and verified cloud/model permissions. AI batches need the worker and scheduler. `features.gitopsPublish` requires reviewed target bindings and GitHub App secret refs. These charts do not execute remediation, grant cloud permissions, configure native billing connectors or make unfinished application features production-ready. Platform billing remains disabled in this chart version while upstream migration/API compatibility is unresolved.

Put non-secret environment settings in `config`. Bind additional secrets only to the components that need them:

```yaml
components:
  scanner-service:
    secretEnv:
      CLOUDSAVER_GITHUB_APP_PRIVATE_KEY:
        name: cloudsaver-gitops
        key: private-key
```

Use the same pattern on the dispatcher/worker for their webhook or provider credentials where required. Never store actual secret values in Helm values or ConfigMaps.

## Validate and package

```bash
python3 -m pip install PyYAML==6.0.3
make lint
HELM=helm KUBECONFORM=kubeconform python3 scripts/test_charts.py
make package
```

The script tests default and production renders, renamed releases, pinned digests, optional workers, secret separation, singleton limits, ingress/network policies and invalid configuration guards. With kubeconform, it strictly checks every rendered resource against Kubernetes 1.26 and 1.33 schemas. Without `KUBECONFORM`, it explicitly reports schema validation as skipped. CI always enables it using checksum-pinned tools and packages both charts. Packages are written to ignored `dist/`; no charts are automatically published to an OCI registry or GitHub Pages.

Application source remains in `ashokkondapuram/project`. This repository owns the deployment charts and their tests only. See [verification results](docs/VERIFICATION.md).
