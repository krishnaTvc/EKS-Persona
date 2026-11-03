import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'scripts/cloud/bootstrap.py'
spec = importlib.util.spec_from_file_location('bootstrap', PATH)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class BootstrapTests(unittest.TestCase):
    def test_only_explicit_absence_is_accepted(self):
        for code in ['AccessDenied', 'ExpiredToken', 'Throttling', 'NoSuchEntity']:
            result = subprocess.CompletedProcess([], 1, '', f'An error occurred ({code})')
            with patch.object(b.subprocess, 'run', return_value=result):
                if code == 'NoSuchEntity':
                    self.assertIsNone(b.aws('iam', 'get-role', missing=('NoSuchEntity',)))
                else:
                    with self.assertRaises(RuntimeError):
                        b.aws('iam', 'get-role', missing=('NoSuchEntity',))

    def test_unknown_failure_is_not_absence(self):
        result = subprocess.CompletedProcess([], 1, '', 'network timeout')
        with patch.object(b.subprocess, 'run', return_value=result):
            with self.assertRaises(RuntimeError):
                b.aws('s3api', 'get-bucket-location', missing=('NoSuchBucket',))

    def test_repeated_import_skips_tracked_resource(self):
        tracked = set()
        with patch.object(b, 'tf') as tf:
            b.import_if_needed('role', 'existing', tracked)
            b.import_if_needed('role', 'existing', tracked)
            self.assertEqual(tf.call_count, 1)

    def test_replacements_and_deletes_are_blocked(self):
        for actions in [['delete'], ['create', 'delete'], ['delete', 'create']]:
            with self.assertRaises(RuntimeError):
                b.reject_destructive({'resource_changes': [
                    {'address': 'role', 'change': {'actions': actions}}]})
        b.reject_destructive({'resource_changes': [
            {'address': 'role', 'change': {'actions': ['update']}}]})

    def test_discovery_missing_roles_ecr_and_bucket_settings(self):
        with patch.object(b, 'aws', return_value=None):
            self.assertEqual(b.discover_imports('bucket'), [('aws_s3_bucket.state', 'bucket')])

    def test_discovery_includes_separately_managed_settings_and_inline_policies(self):
        with patch.object(b, 'aws', return_value={'Status': 'Enabled'}):
            imports = dict(b.discover_imports('bucket'))
        self.assertEqual(len(imports), 13)
        self.assertEqual(imports['aws_iam_role_policy.infra'],
                         'eks-persona-ci-infra:eks-persona-lab-infrastructure')
        self.assertEqual(imports['aws_ecr_repository.app["media"]'], 'eks-persona/media')
        self.assertIn('aws_s3_bucket_policy.state_tls', imports)

    def test_plan_deletion_blocks_apply(self):
        plan = {'resource_changes': [{'address': 'role', 'change': {'actions': ['delete']}}]}
        with patch.object(b, 'tf', side_effect=[None, json.dumps(plan)]) as tf:
            with self.assertRaises(RuntimeError):
                b.make_plan('plan')
            self.assertFalse(any(call.args[0] == 'apply' for call in tf.call_args_list))


if __name__ == '__main__':
    unittest.main()
