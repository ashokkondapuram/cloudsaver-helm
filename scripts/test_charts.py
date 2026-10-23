"""Offline Helm contract tests; with KUBECONFORM, also validate Kubernetes schemas.

Requires Helm 3 and PyYAML. Does not contact a Kubernetes cluster or read Secrets.
Kubeconform fetches public JSON schemas when KUBECONFORM is set.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
HELM = os.getenv('HELM') or shutil.which('helm')
KUBECONFORM = os.getenv('KUBECONFORM')


def execute(*args):
    return subprocess.run(args, text=True, capture_output=True)


def of_kind(docs, kind):
    return [d for d in docs if d['kind'] == kind]


def check_contract(docs):
    names = [(d['kind'], d['metadata']['name']) for d in docs]
    assert len(names) == len(set(names)), 'Duplicate resource names'
    assert not of_kind(docs, 'Secret'), 'Charts must not store secret values'
    assert not of_kind(docs, 'StatefulSet') and not of_kind(docs, 'PersistentVolumeClaim')
    assert not of_kind(docs, 'RoleBinding') and not of_kind(docs, 'ClusterRoleBinding')
    for d in of_kind(docs, 'Deployment'):
        pod = d['spec']['template']
        assert pod['metadata']['labels'] == d['spec']['selector']['matchLabels']
        assert pod['spec']['automountServiceAccountToken'] is False
        security = pod['spec']['securityContext']
        assert security['runAsNonRoot'] is True and security['seccompProfile']['type'] == 'RuntimeDefault'
        c = pod['spec']['containers'][0]
        assert c['securityContext']['readOnlyRootFilesystem'] is True
        assert c['securityContext']['allowPrivilegeEscalation'] is False
        assert c['securityContext']['capabilities']['drop'] == ['ALL']
        assert c['resources']['requests'] and c['resources']['limits']
        assert len(c['env']) == len({v['name'] for v in c['env']}), 'Duplicate env names'
        assert all('secretRef' not in v for v in c.get('envFrom', [])), 'Do not import an entire Secret'
        for v in c['env']:
            if 'valueFrom' in v:
                assert 'migration' not in v['valueFrom']['secretKeyRef']['name']
        component = pod['metadata']['labels']['app.kubernetes.io/component']
        if component in ('platform-portal', 'scan-scheduler'):
            assert d['spec']['replicas'] == 1 and d['spec']['strategy'] == {'type': 'Recreate'}
        if c.get('ports'):
            assert c['startupProbe'] and c['livenessProbe'] and c['readinessProbe']
        if component in ('web-dashboard', 'platform-portal'):
            assert not c.get('envFrom'), 'Frontend must not receive backend config/credentials'
    for s in of_kind(docs, 'Service'):
        assert s['spec']['type'] == 'ClusterIP' and not s['spec'].get('externalIPs')
        assert any(d['spec']['template']['metadata']['labels'] == s['spec']['selector']
                   for d in of_kind(docs, 'Deployment'))
    for j in of_kind(docs, 'Job'):
        assert j['metadata']['annotations']['helm.sh/hook'] == 'pre-install,pre-upgrade'
        assert j['spec']['backoffLimit'] == 0 and j['spec']['activeDeadlineSeconds'] <= 3600
        pod = j['spec']['template']['spec']
        c = pod['containers'][0]
        assert pod['automountServiceAccountToken'] is False and not c.get('envFrom')
        assert len(c['env']) == 1
        assert c['env'][0]['valueFrom']['secretKeyRef']['name'].endswith('-migration')
    for cm in of_kind(docs, 'ConfigMap'):
        assert all(isinstance(v, str) for v in cm['data'].values())
    for i in of_kind(docs, 'Ingress'):
        spec = i['spec']
        assert spec['tls'][0]['secretName'] and spec['rules'][0]['host'] in spec['tls'][0]['hosts']
        for path in spec['rules'][0]['http']['paths']:
            assert path['backend']['service']['name'].endswith(('-web-dashboard', '-platform-portal'))


def main():
    if not HELM:
        raise SystemExit('Helm 3 is required; set HELM=/path/to/helm if necessary.')
    count, manifests = 0, []
    with tempfile.TemporaryDirectory(prefix='cloudsaver-charts-') as temporary:
        temporary = Path(temporary)

        def render(chart, changes=None, valid=True, example=True):
            nonlocal count
            count += 1
            chart_path = ROOT / 'charts' / chart
            override = temporary / 'override.yaml'
            override.write_text(yaml.safe_dump(changes or {}))
            flags = ['-f', str(chart_path / 'values-production.example.yaml')] if example else []
            name = 'platform' if chart.endswith('platform') else 'cloudsaver'
            result = execute(HELM, 'template', name, str(chart_path), '-n', name, *flags, '-f', str(override))
            if not valid:
                assert result.returncode != 0, f'Unsafe config accepted: {chart}, {changes}'
                return []
            assert result.returncode == 0, result.stderr
            docs = [d for d in yaml.safe_load_all(result.stdout) if d]
            check_contract(docs)
            manifests.append(result.stdout)
            return docs

        for chart in ('cloudsaver', 'cloudsaver-platform'):
            path = ROOT / 'charts' / chart
            result = execute(HELM, 'lint', str(path), '--strict', '-f', str(path / 'values-production.example.yaml'))
            assert result.returncode == 0, result.stdout + result.stderr
        baseline = render('cloudsaver', example=False)
        assert len(of_kind(baseline, 'Deployment')) == 6 and not of_kind(baseline, 'Ingress')
        cloud = render('cloudsaver')
        platform = render('cloudsaver-platform')
        assert len(of_kind(platform, 'Deployment')) == 2
        data = of_kind(platform, 'ConfigMap')[0]['data']
        assert data['PLATFORM_ENVIRONMENT'] == 'production' and data['PLATFORM_PORTAL_AUTH'] == 'entra'
        assert data['PLATFORM_OPERATOR_TENANT_ID'] == '11111111-1111-4111-8111-111111111111'
        migration = of_kind(platform, 'Job')[0]['spec']['template']['spec']['containers'][0]
        assert migration['env'][0]['name'] == 'PLATFORM_IDENTITY_MIGRATION_URL'
        policy = next(p for p in of_kind(platform, 'NetworkPolicy') if p['metadata']['name'] == 'platform-identity-service')
        peer = policy['spec']['ingress'][0]['from'][1]
        assert peer['namespaceSelector']['matchLabels']['kubernetes.io/metadata.name'] == 'cloudsaver'
        assert peer['podSelector']['matchLabels']['app.kubernetes.io/name'] == 'cloudsaver'
        for d in of_kind(cloud, 'Deployment'):
            c = d['spec']['template']['spec']['containers'][0]
            component = c['name']
            env = {v['name']: v for v in c['env']}
            if component == 'web-dashboard':
                assert 'CLOUDSAVER_DATABASE_URL' not in env and 'CLOUDSAVER_IDENTITY_TOKEN' not in env
            else:
                assert 'CLOUDSAVER_IDENTITY_TOKEN' in env
        workers = {n: {'enabled': True} for n in ('scan-worker', 'scan-scheduler', 'delivery-dispatcher')}
        full = render('cloudsaver', {'components': workers, 'features': {'scheduledScans': True, 'interactiveJobs': True,
                               'delivery': True, 'automatedAlerts': True, 'ai': True}})
        assert len(of_kind(full, 'Deployment')) == 9
        for chart in ('cloudsaver', 'cloudsaver-platform'):
            docs = render(chart, {'migration': {'enabled': False}, 'networkPolicy': {'enabled': False}})
            assert not of_kind(docs, 'Job') and not of_kind(docs, 'NetworkPolicy')
        digest = 'sha256:' + 'a' * 64
        custom = render('cloudsaver', {'fullnameOverride': 'renamed', 'images': {'python': {'digest': digest}},
                      'components': {'scanner-service': {'secretEnv': {
                        'CLOUDSAVER_GITHUB_APP_PRIVATE_KEY': {'name': 'gitops', 'key': 'private-key'}},
                        'extraVolumes': [{'name': 'ca', 'configMap': {'name': 'db-ca'}}],
                        'extraVolumeMounts': [{'name': 'ca', 'mountPath': '/etc/db-ca', 'readOnly': True}]}}})
        scanner = next(d for d in of_kind(custom, 'Deployment') if d['metadata']['name'] == 'renamed-scanner-service')
        assert scanner['spec']['template']['spec']['containers'][0]['image'].endswith('@' + digest)
        render('cloudsaver-platform', {'fullnameOverride': 'renamed', 'imagePullSecrets': [{'name': 'registry'}],
               'serviceAccount': {'annotations': {'example.com/identity': 'bound'}},
               'podAnnotations': {'example.com/revision': '2'}})
        bad_cloud = [
            {'features': {'scheduledScans': True}}, {'features': {'interactiveJobs': True}},
            {'features': {'delivery': True}}, {'features': {'automatedAlerts': True}},
            {'components': {'scan-scheduler': {'replicas': 2}}},
            {'components': {'tenant-service': {'replicas': 2}}},
            {'components': {'typo': {'enabled': True}}}, {'runtimeSecret': 'cloudsaver-migration'},
            {'ingress': {'tlsSecretName': ''}}, {'ingress': {'host': 'https://bad.example.com'}},
            {'config': {'CLOUDSAVER_KEY_VERIFIER': 'local'}}, {'config': {'CLOUDSAVER_DB_POOL_SIZE': 5}},
            {'components': {'scanner-service': {'secretEnv': {'CLOUDSAVER_DATABASE_URL': {'name': 'bad', 'key': 'url'}}}}},
            {'images': {'python': {'digest': 'sha256:invalid'}}}]
        for change in bad_cloud:
            render('cloudsaver', change, valid=False)
        for change in [
            {'components': {'platform-portal': {'replicas': 2}}}, {'config': {'PLATFORM_PORTAL_AUTH': 'operator_key'}},
            {'publicUrl': 'http://platform.example.com'}, {'publicUrl': 'https://other.example.com'},
            {'entra': {'tenantId': 'invalid'}}, {'identitySecret': 'platform-migration'},
            {'networkPolicy': {'ingressController': {'namespaceSelector': None}}}]:
            render('cloudsaver-platform', change, valid=False)
        render('cloudsaver-platform', valid=False, example=False)
        if KUBECONFORM:
            path = temporary / 'rendered.yaml'
            path.write_text('\n---\n'.join(manifests))
            cache = temporary / 'cache'
            cache.mkdir()
            for version in ('1.26.0', '1.33.0'):
                result = execute(KUBECONFORM, '-strict', '-summary', '-kubernetes-version', version,
                                 '-cache', str(cache), str(path))
                assert result.returncode == 0, result.stdout + result.stderr
                print(f'Kubernetes {version}: {result.stdout.strip()}')
        else:
            print('Kubernetes schema validation skipped: set KUBECONFORM to enable it.')
    print(f'Passed: 2 strict lints and {count} render/guard scenarios.')


if __name__ == '__main__':
    main()
