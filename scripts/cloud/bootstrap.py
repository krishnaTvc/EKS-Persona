#!/usr/bin/env python3
"""Bootstrap only. AWS absence is distinguished from denied/broken API calls."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ACCOUNT = '407178840502'
KEY = 'bootstrap/terraform.tfstate'
S3_RESOURCES = [
    'aws_s3_bucket.state', 'aws_s3_bucket_versioning.state',
    'aws_s3_bucket_server_side_encryption_configuration.state',
    'aws_s3_bucket_public_access_block.state', 'aws_s3_bucket_policy.state_tls',
]


def aws(*args, missing=()):
    result = subprocess.run(['aws', *args, '--output', 'json'], text=True,
                            capture_output=True, check=False)
    if result.returncode:
        match = re.search(r'An error occurred \(([^)]+)\)', result.stderr)
        if match and match.group(1) in missing:
            return None
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else {}


def tf(*args, capture=False):
    result = subprocess.run(['terraform', *args], text=True, check=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout if capture else None


def import_if_needed(address, resource_id, tracked):
    if address not in tracked:
        print(f'Importing {address}', flush=True)
        tf('import', '-input=false', '-lock-timeout=120s', address, resource_id)
        tracked.add(address)


def reject_destructive(plan):
    for resource in plan.get('resource_changes', []):
        if 'delete' in resource['change']['actions']:
            raise RuntimeError(f"Refusing deletion/replacement: {resource['address']}")


def make_plan(filename, targets=()):
    tf('plan', '-input=false', '-lock-timeout=120s', f'-out={filename}',
       *[f'-target={target}' for target in targets])
    reject_destructive(json.loads(tf('show', '-json', filename, capture=True)))


def discover_imports(bucket):
    """Probe all separately managed resources. Fail closed except explicit absence."""
    imports = [('aws_s3_bucket.state', bucket)]
    checks = [
        ('aws_s3_bucket_versioning.state', 'get-bucket-versioning', (),
         lambda value: value.get('Status') in ('Enabled', 'Suspended')),
        ('aws_s3_bucket_server_side_encryption_configuration.state',
         'get-bucket-encryption', ('ServerSideEncryptionConfigurationNotFoundError',),
         lambda value: True),
        ('aws_s3_bucket_public_access_block.state', 'get-public-access-block',
         ('NoSuchPublicAccessBlockConfiguration',), lambda value: True),
        ('aws_s3_bucket_policy.state_tls', 'get-bucket-policy', ('NoSuchBucketPolicy',),
         lambda value: True),
    ]
    for address, operation, absent, exists in checks:
        value = aws('s3api', operation, '--bucket', bucket,
                    '--expected-bucket-owner', ACCOUNT, missing=absent)
        if value is not None and exists(value):
            imports.append((address, bucket))
    for kind, policy in [('infra', 'eks-persona-lab-infrastructure'),
                         ('deploy', 'persona-deployment-and-backup')]:
        name = f'eks-persona-ci-{kind}'
        if aws('iam', 'get-role', '--role-name', name, missing=('NoSuchEntity',)) is not None:
            imports.append((f'aws_iam_role.ci["{kind}"]', name))
            if aws('iam', 'get-role-policy', '--role-name', name, '--policy-name', policy,
                   missing=('NoSuchEntity',)) is not None:
                imports.append((f'aws_iam_role_policy.{kind}', f'{name}:{policy}'))
    for service in ['frontend', 'registration', 'persona', 'media']:
        name = f'eks-persona/{service}'
        if aws('ecr', 'describe-repositories', '--repository-names', name,
               missing=('RepositoryNotFoundException',)) is not None:
            imports.append((f'aws_ecr_repository.app["{service}"]', name))
    return imports


def main():
    bucket = os.environ['STATE_BUCKET']
    region = os.environ['AWS_REGION']
    operation = os.environ.get('OPERATION', 'plan')
    if operation not in ('plan', 'apply'):
        raise RuntimeError('OPERATION must be plan or apply')
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', bucket):
        raise RuntimeError('Invalid STATE_BUCKET')
    if aws('sts', 'get-caller-identity')['Account'] != ACCOUNT:
        raise RuntimeError('Authenticated to the wrong AWS account')
    # Existing GitHub provider is referenced, never modified by this workflow.
    aws('iam', 'get-open-id-connect-provider', '--open-id-connect-provider-arn',
        f'arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com')
    os.environ['TF_VAR_create_github_oidc'] = 'false'
    os.chdir('terraform/bootstrap')
    if Path('backend.tf').exists() or Path('terraform.tfstate').exists():
        raise RuntimeError('Use a fresh checkout without backend.tf or local state')
    location = aws('s3api', 'get-bucket-location', '--bucket', bucket,
                   '--expected-bucket-owner', ACCOUNT, missing=('NoSuchBucket',))
    bucket_exists = location is not None
    if bucket_exists:
        actual_region = location.get('LocationConstraint') or 'us-east-1'
        if actual_region != region:
            raise RuntimeError(f'Bucket region is {actual_region}, not {region}')
    elif operation == 'plan':
        raise RuntimeError('Bucket does not exist yet. First run: choose apply to create '
                           'the bucket and persist bootstrap state. No resources changed.')

    backend_args = [f'-backend-config=bucket={bucket}', f'-backend-config=key={KEY}',
                    f'-backend-config=region={region}', '-backend-config=use_lockfile=true',
                    '-backend-config=encrypt=true',
                    f'-backend-config=expected_bucket_owner={ACCOUNT}']
    if not bucket_exists:
        # Exceptional first run: Terraform creates only S3 resources using local state.
        # Migrate that state immediately, before importing IAM roles or creating ECR.
        tf('init', '-input=false')
        make_plan('bucket.tfplan', S3_RESOURCES)
        tf('apply', '-input=false', 'bucket.tfplan')
        Path('backend.tf').write_text('terraform {\n  backend "s3" {}\n}\n')
        tf('init', '-input=false', '-force-copy', *backend_args)
    else:
        Path('backend.tf').write_text('terraform {\n  backend "s3" {}\n}\n')
        tf('init', '-input=false', *backend_args)

    state_object = aws('s3api', 'head-object', '--bucket', bucket, '--key', KEY,
                       '--expected-bucket-owner', ACCOUNT, missing=('404', 'NoSuchKey'))
    tracked = (set(tf('state', 'list', capture=True).splitlines())
               if state_object is not None else set())
    for address, resource_id in discover_imports(bucket):
        import_if_needed(address, resource_id, tracked)
    make_plan('bootstrap.tfplan')
    if operation == 'apply':
        tf('apply', '-input=false', 'bootstrap.tfplan')
        tf('output')
    else:
        print('Plan complete. Imports were saved to S3; planned configuration changes '
              'were not applied. Choose apply in a new run after reviewing the plan.')


def recover_local_state():
    # Only first-run bucket creation/migration can leave local state. Keep a private,
    # encrypted recovery copy rather than publishing state as an Actions artifact.
    state = Path('terraform.tfstate')
    if state.exists() and json.loads(state.read_text()).get('resources'):
        bucket = os.environ['STATE_BUCKET']
        run_id = os.environ.get('GITHUB_RUN_ID', 'manual')
        aws('s3api', 'put-object', '--bucket', bucket,
            '--expected-bucket-owner', ACCOUNT,
            '--key', f'bootstrap/recovery/{run_id}.tfstate', '--body', str(state),
            '--server-side-encryption', 'AES256')
        print(f'Recovery state saved privately at s3://{bucket}/bootstrap/recovery/{run_id}.tfstate',
              file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'ERROR: {error}', file=sys.stderr)
        try:
            recover_local_state()
        except Exception as recovery_error:
            print(f'RECOVERY FAILED: {recovery_error}', file=sys.stderr)
        sys.exit(1)
