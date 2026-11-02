"""Offline teardown safety checks. No AWS or Kubernetes commands are executed."""
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

script = Path(__file__).resolve().parents[1] / 'scripts/cloud/destroy.py'
spec = spec_from_file_location('persona_destroy', script)
destroy = module_from_spec(spec)
spec.loader.exec_module(destroy)


def resource(kind, attributes):
    return {'mode': 'managed', 'type': kind, 'instances': [{'attributes': attributes}]}


class TeardownTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {
            'RUNNER_TEMP': self.temp.name, 'AWS_REGION': 'eu-north-1',
            'STATE_BUCKET': 'example-state-bucket', 'CLUSTER_NAME': 'eks-persona-dev',
            'DESTROY_MODE': 'plan-only', 'CONFIRM_CLUSTER': '',
            'GITHUB_RUN_ID': '123', 'GITHUB_OUTPUT': str(Path(self.temp.name) / 'outputs'),
            'GITHUB_STEP_SUMMARY': str(Path(self.temp.name) / 'summary'),
        })
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def test_destroy_requires_exact_confirmation(self):
        with self.assertRaises(SystemExit):
            destroy.guard_confirmation()
        with patch.dict(os.environ, {'DESTROY_MODE': 'destroy', 'CONFIRM_CLUSTER': 'wrong'}):
            with self.assertRaises(SystemExit):
                destroy.guard_confirmation()
        with patch.dict(os.environ, {'DESTROY_MODE': 'destroy', 'CONFIRM_CLUSTER': 'eks-persona-dev'}):
            destroy.guard_confirmation()

    def test_bootstrap_resources_are_refused(self):
        for kind in ['aws_s3_bucket', 'aws_ecr_repository', 'aws_iam_openid_connect_provider']:
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                destroy.validate_state({'resources': [resource(kind, {})]})

    def test_ci_roles_are_refused(self):
        with self.assertRaises(ValueError):
            destroy.validate_state({'resources': [resource('aws_iam_role', {'name': 'eks-persona-ci-infra'})]})

    def test_other_cluster_or_project_is_refused(self):
        for item in [resource('aws_eks_cluster', {'name': 'some-other-cluster'}),
                     resource('aws_vpc', {'tags_all': {'Project': 'other-project'}})]:
            with self.assertRaises(ValueError):
                destroy.validate_state({'resources': [item]})

    def test_expected_workload_state_is_accepted(self):
        values = [resource('aws_eks_cluster', {'name': 'eks-persona-dev'}),
                  resource('aws_iam_role', {'name': 'eks-persona-workload-nodes'})]
        self.assertEqual(len(destroy.validate_state({'resources': values})), 2)

    def test_create_update_and_replacement_plans_are_refused(self):
        for actions in [['create'], ['update'], ['delete', 'create'], ['create', 'delete']]:
            with self.subTest(actions=actions), self.assertRaises(ValueError):
                destroy.validate_destroy_plan({'resource_changes': [{'address': 'aws_vpc.main', 'mode': 'managed', 'change': {'actions': actions}}]})

    def test_destroy_and_read_only_plan_is_accepted(self):
        plan = {'resource_changes': [
            {'address': 'aws_vpc.main', 'mode': 'managed', 'change': {'actions': ['delete']}},
            {'address': 'data.aws_caller_identity.current', 'mode': 'data', 'change': {'actions': ['read']}},
        ]}
        self.assertEqual(destroy.validate_destroy_plan(plan), ['aws_vpc.main'])

    def test_preview_does_not_apply(self):
        with patch.object(destroy, 'run') as run, patch.object(destroy, 'capture', return_value='{"resource_changes": []}'):
            destroy.plan()
        calls = [call.args[0] for call in run.call_args_list]
        self.assertTrue(any('-destroy' in command for command in calls))
        self.assertFalse(any('apply' in command for command in calls))

    def test_invalid_saved_plan_cannot_be_applied(self):
        unsafe = json.dumps({'resource_changes': [{'address': 'x', 'change': {'actions': ['create']}}]})
        with patch.dict(os.environ, {'DESTROY_MODE': 'destroy', 'CONFIRM_CLUSTER': 'eks-persona-dev'}), patch.object(destroy, 'run') as run, patch.object(destroy, 'capture', return_value=unsafe):
            with self.assertRaises(ValueError):
                destroy.plan(apply=True)
        self.assertFalse(any('apply' in call.args[0] for call in run.call_args_list))

    def test_missing_state_stops_before_terraform(self):
        missing = subprocess.CompletedProcess([], 254, stdout='', stderr='An error occurred (404): Not Found')
        with patch.object(destroy, 'run') as run, patch.object(destroy.subprocess, 'run', return_value=missing), patch.object(destroy, 'capture') as capture:
            destroy.prepare()
        self.assertEqual(run.call_count, 1)  # Read-only head-bucket.
        capture.assert_not_called()
        self.assertIn('has_state=false', Path(os.environ['GITHUB_OUTPUT']).read_text())

    def test_unready_database_aborts_backup(self):
        inventory = destroy.state_dir() / 'storage-inventory.json'
        inventory.write_text(json.dumps({'database_claim': 'data-mysql-0'}))
        with patch.dict(os.environ, {'DESTROY_MODE': 'destroy', 'CONFIRM_CLUSTER': 'eks-persona-dev', 'BACKUP_DATABASE': 'true'}), patch.object(destroy, 'run') as run, patch.object(destroy, 'capture', return_value='{"status":{"conditions":[]}}'):
            with self.assertRaises(SystemExit):
                destroy.backup()
        self.assertFalse(any('mysqldump' in ' '.join(call.args[0]) for call in run.call_args_list))


if __name__ == '__main__':
    unittest.main(verbosity=2)
