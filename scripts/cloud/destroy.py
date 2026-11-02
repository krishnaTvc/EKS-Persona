#!/usr/bin/env python3
"""Manual teardown of this repository's INFRA state, never its bootstrap state.

No normal provisioning apply is called. The final apply consumes only a plan
created with -destroy and rejects create/update/replacement actions.
"""
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_CLUSTER = 'eks-persona-dev'
STATE_KEY = 'infra/terraform.tfstate'


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def capture(args):
    return run(args, capture_output=True, text=True).stdout


def aws(*args):
    return ['aws', *args, '--region', os.environ['AWS_REGION']]


def kubectl(*args):
    return ['kubectl', *args]


def state_dir():
    folder = Path(os.environ['RUNNER_TEMP']) / 'eks-persona-destroy'
    folder.mkdir(mode=0o700, exist_ok=True)
    return folder


def output(**values):
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as file:
            for key, value in values.items():
                file.write(f'{key}={str(value).lower() if isinstance(value, bool) else value}\n')


def summary(text):
    print(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as file:
            file.write(text + '\n\n')


def guard_confirmation():
    if os.environ.get('CLUSTER_NAME') != EXPECTED_CLUSTER:
        raise SystemExit('This addition is scoped to eks-persona-dev only.')
    if os.environ.get('DESTROY_MODE') != 'destroy' or os.environ.get('CONFIRM_CLUSTER') != EXPECTED_CLUSTER:
        raise SystemExit('Destructive steps require destroy mode and an exact cluster-name confirmation.')


def validate_state(state):
    resources = [item for item in state.get('resources', []) if item.get('mode') == 'managed']
    for resource in resources:
        kind = resource['type']
        if kind in {'aws_s3_bucket', 'aws_ecr_repository', 'aws_iam_openid_connect_provider'}:
            raise ValueError('State contains bootstrap/shared resources; refusing teardown.')
        for instance in resource.get('instances', []):
            attrs = instance.get('attributes', {})
            if kind == 'aws_eks_cluster' and attrs.get('name') != EXPECTED_CLUSTER:
                raise ValueError('State contains a different EKS cluster.')
            if kind == 'aws_iam_role' and not attrs.get('name', '').startswith('eks-persona-workload-'):
                raise ValueError('State contains an IAM role outside the project workload prefix.')
            project = (attrs.get('tags_all') or attrs.get('tags') or {}).get('Project')
            if project and project != 'eks-persona':
                raise ValueError('State contains resources tagged for another project.')
    return resources


def validate_destroy_plan(plan):
    deleted = []
    for change in plan.get('resource_changes', []):
        actions = change.get('change', {}).get('actions', [])
        if any(action not in {'delete', 'no-op', 'read'} for action in actions):
            raise ValueError(f"Not a delete-only plan: {change.get('address')} {actions}")
        if change.get('mode') == 'managed' and 'delete' in actions:
            deleted.append(change['address'])
    return deleted


def metadata():
    return json.loads((state_dir() / 'metadata.json').read_text())


def prepare():
    if os.environ.get('CLUSTER_NAME') != EXPECTED_CLUSTER:
        raise SystemExit('Unexpected target cluster.')
    bucket = os.environ['STATE_BUCKET']
    # A missing/inaccessible bucket is a configuration error, not an empty state.
    run(aws('s3api', 'head-bucket', '--bucket', bucket))
    head = subprocess.run(aws('s3api', 'head-object', '--bucket', bucket, '--key', STATE_KEY), capture_output=True, text=True)
    if head.returncode:
        if '(404)' in head.stderr or 'NoSuchKey' in head.stderr:
            output(has_state=False, cluster_exists=False)
            summary(f'No infra state exists at s3://{bucket}/{STATE_KEY}. Nothing was destroyed.')
            return
        raise SystemExit('Cannot read the infra state object. Check bucket/key/IAM permissions; no cleanup was attempted.')
    run(['terraform', '-chdir=terraform/infra', 'init', '-input=false',
         f'-backend-config=bucket={bucket}', f'-backend-config=key={STATE_KEY}',
         f'-backend-config=region={os.environ["AWS_REGION"]}', '-backend-config=use_lockfile=true'])
    state = json.loads(capture(['terraform', '-chdir=terraform/infra', 'state', 'pull']))
    resources = validate_state(state)
    if not resources:
        output(has_state=False, cluster_exists=False)
        summary('The infra state has no managed resources. Nothing was destroyed.')
        return
    # Only inspect/connect to an EKS cluster actually owned by this state.
    owns_cluster = any(item['type'] == 'aws_eks_cluster' for item in resources)
    cluster = None
    if owns_cluster:
        response = subprocess.run(aws('eks', 'describe-cluster', '--name', EXPECTED_CLUSTER, '--output', 'json'), capture_output=True, text=True)
        if response.returncode == 0:
            cluster = json.loads(response.stdout)['cluster']
            if cluster['status'] != 'ACTIVE':
                raise SystemExit('Cluster is not ACTIVE. Wait for its current operation before teardown.')
        elif 'ResourceNotFoundException' not in response.stderr:
            raise SystemExit('Cannot inspect the managed cluster; check IAM/API errors before retrying.')
    # The uploaded repo has no committed pins. Resolve valid inputs if missing;
    # these reads do not create/upgrade add-ons, and no normal apply is called.
    pins = ROOT / 'terraform/infra/addons.auto.tfvars.json'
    if not pins.exists() and not os.environ.get('TF_VAR_addon_versions'):
        run(['python3', 'scripts/cloud/resolve-addon-versions.py'])
    (state_dir() / 'metadata.json').write_text(json.dumps({'cluster': cluster, 'managed_resources': len(resources)}))
    output(has_state=True, cluster_exists=cluster is not None)
    summary(f'Using only s3://{bucket}/{STATE_KEY}; found {len(resources)} managed infra resource records.')


def plan(apply=False):
    if apply:
        guard_confirmation()
    file = Path(os.environ['RUNNER_TEMP']) / 'eks-persona-destroy.tfplan'
    run(['terraform', '-chdir=terraform/infra', 'plan', '-destroy', '-input=false', '-lock-timeout=5m', f'-out={file}'])
    document = json.loads(capture(['terraform', '-chdir=terraform/infra', 'show', '-json', str(file)]))
    changes = validate_destroy_plan(document)
    summary(f'Destroy-only plan validated: {len(changes)} managed resources scheduled for deletion.')
    if apply:
        run(['terraform', '-chdir=terraform/infra', 'apply', '-input=false', '-lock-timeout=5m', str(file)])
        summary('Infra teardown completed. Bootstrap resources and retained EBS disks were not targeted; check retained-storage inventory and remaining costs.')
    else:
        summary('Plan-only mode: no Helm uninstall, endpoint change, or Terraform apply was performed.')


def connect():
    guard_confirmation()
    cluster = metadata()['cluster']
    config = cluster['resourcesVpcConfig']
    if not config.get('endpointPublicAccess'):
        raise SystemExit('This cluster has a private-only API. Use an EC2 runner with VPC access; this script will not enable public access.')
    cidrs = json.loads(os.environ['TF_VAR_api_allowed_cidrs'])
    for item in cidrs:
        if ipaddress.IPv4Network(item, strict=False).prefixlen == 0:
            raise SystemExit('Refusing an unrestricted API CIDR.')
    merged = list(dict.fromkeys(config.get('publicAccessCidrs', []) + cidrs))
    if len(merged) > 50:
        raise SystemExit('Too many API allowlist entries; review the existing list before teardown.')
    if set(merged) != set(config.get('publicAccessCidrs', [])):
        update = json.loads(capture(aws('eks', 'update-cluster-config', '--name', EXPECTED_CLUSTER,
                                        '--resources-vpc-config', json.dumps({'publicAccessCidrs': merged}), '--output', 'json')))
        for _ in range(120):
            response = json.loads(capture(aws('eks', 'describe-update', '--name', EXPECTED_CLUSTER, '--update-id', update['update']['id'], '--output', 'json')))
            status = response['update']['status']
            if status == 'Successful':
                break
            if status in {'Failed', 'Cancelled'}:
                raise SystemExit('EKS endpoint update did not complete; no app cleanup was attempted.')
            time.sleep(5)
        else:
            raise SystemExit('Timed out waiting for endpoint allowlist update.')
    run(aws('eks', 'update-kubeconfig', '--name', EXPECTED_CLUSTER))
    namespace = capture(kubectl('get', 'namespace', 'persona', '--ignore-not-found', '-o', 'json'))
    inventory = {'cluster': EXPECTED_CLUSTER, 'namespace_exists': bool(namespace.strip()), 'database_claim': None, 'volume': None}
    if namespace.strip():
        claim_text = capture(kubectl('-n', 'persona', 'get', 'pvc', 'data-mysql-0', '--ignore-not-found', '-o', 'json'))
        if claim_text.strip():
            claim = json.loads(claim_text)
            inventory['database_claim'] = claim['metadata']['name']
            bound = claim.get('spec', {}).get('volumeName')
            if bound:
                volume = json.loads(capture(kubectl('get', 'pv', bound, '-o', 'json')))
                run(kubectl('patch', 'pv', bound, '--type=merge', '-p', json.dumps({'spec': {'persistentVolumeReclaimPolicy': 'Retain'}})))
                inventory['volume'] = {'pv': bound, 'ebs_volume_id': volume.get('spec', {}).get('csi', {}).get('volumeHandle'),
                                       'node_affinity': volume.get('spec', {}).get('nodeAffinity')}
        sts = capture(kubectl('-n', 'persona', 'get', 'statefulset', 'mysql', '--ignore-not-found', '-o', 'json'))
        if sts.strip():
            run(kubectl('-n', 'persona', 'patch', 'statefulset', 'mysql', '--type=merge', '-p',
                        json.dumps({'spec': {'persistentVolumeClaimRetentionPolicy': {'whenDeleted': 'Retain', 'whenScaled': 'Retain'}}})))
    (state_dir() / 'storage-inventory.json').write_text(json.dumps(inventory, indent=2))
    summary('Cluster access checked and MySQL disk retention recorded. Endpoint CIDR update is a teardown-only adjustment, not a provisioning apply.')


def backup():
    guard_confirmation()
    folder = state_dir()
    inventory = json.loads((folder / 'storage-inventory.json').read_text())
    prefix = f"backups/destroy-{os.environ['GITHUB_RUN_ID']}"
    bucket = os.environ['STATE_BUCKET']
    run(aws('s3', 'cp', str(folder / 'storage-inventory.json'), f's3://{bucket}/{prefix}/storage-inventory.json', '--sse', 'AES256', '--only-show-errors'))
    summary(f'Retained storage inventory: s3://{bucket}/{prefix}/storage-inventory.json')
    if not inventory.get('namespace_exists', True):
        summary('Application namespace was never created; there is no database to back up.')
        return
    if os.environ.get('BACKUP_DATABASE', 'true').lower() != 'true':
        summary('Database backup was explicitly disabled. Existing MySQL EBS storage remains retained.')
        return
    pod = capture(kubectl('-n', 'persona', 'get', 'pod', 'mysql-0', '--ignore-not-found', '-o', 'json'))
    if not pod.strip():
        if inventory['database_claim']:
            raise SystemExit('A MySQL claim exists but no MySQL pod is available for backup. Teardown stopped. Repair/start MySQL, or deliberately disable backup while retaining its disk.')
        summary('No MySQL pod or claim was deployed; database backup is not applicable.')
        return
    conditions = json.loads(pod).get('status', {}).get('conditions', [])
    if not any(item.get('type') == 'Ready' and item.get('status') == 'True' for item in conditions):
        raise SystemExit('MySQL is not Ready. Backup could not be verified; teardown stopped before uninstall.')
    file = folder / 'animal-persona.sql'
    try:
        with file.open('wb') as stream:
            run(kubectl('-n', 'persona', 'exec', 'mysql-0', '--', 'sh', '-c',
                        'MYSQL_PWD="$(cat /run/secrets/mysql_root_password)" exec mysqldump -uroot --single-transaction --no-tablespaces animal_persona'), stdout=stream)
        if not file.stat().st_size:
            raise SystemExit('Database dump was empty; teardown stopped.')
        run(aws('s3', 'cp', str(file), f's3://{bucket}/{prefix}/animal-persona.sql', '--sse', 'AES256', '--only-show-errors'))
        summary(f'Database backup uploaded: s3://{bucket}/{prefix}/animal-persona.sql')
    finally:
        file.unlink(missing_ok=True)


def uninstall_app():
    guard_confirmation()
    inventory = json.loads((state_dir() / 'storage-inventory.json').read_text())
    if not inventory.get('namespace_exists', True):
        summary('Application namespace is absent; app uninstall is not applicable.')
        return
    run(['helm', 'uninstall', 'persona', '--namespace', 'persona', '--ignore-not-found', '--cascade', 'foreground', '--wait', '--timeout', '15m'])
    service = capture(kubectl('-n', 'persona', 'get', 'service', 'frontend', '--ignore-not-found', '-o', 'json'))
    if service.strip():
        raise SystemExit('Frontend Service remains. Do not remove its controller/finalizers until NLB cleanup is resolved.')
    summary('Application Helm release removed and frontend Service deletion completed while its load balancer controller was still running.')


def uninstall_controller():
    guard_confirmation()
    # Defense in depth before deleting the controller that owns Service finalizers.
    inventory = json.loads((state_dir() / 'storage-inventory.json').read_text())
    if inventory.get('namespace_exists', True):
        service = capture(kubectl('-n', 'persona', 'get', 'service', 'frontend', '--ignore-not-found', '-o', 'json'))
        if service.strip():
            raise SystemExit('Frontend Service still exists; refusing controller removal.')
    run(['helm', 'uninstall', 'aws-load-balancer-controller', '--namespace', 'kube-system', '--ignore-not-found', '--cascade', 'foreground', '--wait', '--timeout', '5m'])


def main():
    commands = {'prepare': prepare, 'plan': plan, 'connect': connect, 'backup': backup,
                'uninstall-app': uninstall_app, 'uninstall-controller': uninstall_controller,
                'destroy': lambda: plan(apply=True)}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        raise SystemExit('Use: destroy.py prepare|plan|connect|backup|uninstall-app|uninstall-controller|destroy')
    commands[sys.argv[1]]()


if __name__ == '__main__':
    main()
