import importlib.util
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('registry_sync', Path(__file__).resolve().parents[1] / 'packaging/sync_registry.py')
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


class RegistrySyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'VERSION').write_text('1.0.0-nas.4')
        (self.root / 'compose.project.yaml').write_text('image: ghcr.io/xingyunshijie/carddock:1.0.0-nas.4\n')
        self.manifest = json.dumps({'manifests': [
            {'digest': 'sha256:' + 'a' * 64, 'platform': {'os': 'linux', 'architecture': 'amd64'}},
            {'digest': 'sha256:' + 'b' * 64, 'platform': {'os': 'linux', 'architecture': 'arm64'}},
        ]}).encode()

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_complete_untagged_repository_names_are_accepted(self):
        for value in ('', 'ghcr.io/owner/carddock', 'https://ccr.ccs.tencentyun.com/a/carddock',
                      'ccr.ccs.tencentyun.com/a/carddock:latest', 'host/a/carddock', 'registry.example.com/a;echo'):
            with self.assertRaises(ValueError):
                sync.validate_image(value)
        self.assertEqual(sync.validate_image('registry.example.com/team/carddock'), 'registry.example.com/team/carddock')

    def test_missing_credentials_never_attempt_network(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(sync, 'inspect') as inspect:
            with self.assertRaises(ValueError):
                sync.sync('registry.example.com/team/carddock', self.root / 'out', self.root)
            inspect.assert_not_called()

    def test_no_installer_is_emitted_for_incomplete_architectures(self):
        incomplete = json.dumps({'manifests': [{'platform': {'os': 'linux', 'architecture': 'amd64'}}]}).encode()
        with patch.dict(os.environ, CN_REGISTRY_USERNAME='test', CN_REGISTRY_PASSWORD='test-only'), patch.object(sync, 'inspect', return_value=incomplete), patch.object(sync, 'run') as run:
            with self.assertRaises(ValueError):
                sync.sync('registry.example.com/team/carddock', self.root / 'out', self.root)
            run.assert_not_called()
            self.assertFalse((self.root / 'out').exists())

    def test_mismatched_mirror_never_produces_an_installer(self):
        changed = self.manifest + b'\n'
        with patch.dict(os.environ, CN_REGISTRY_USERNAME='test', CN_REGISTRY_PASSWORD='test-only'), patch.object(sync, 'inspect', side_effect=[self.manifest, changed]), patch.object(sync, 'run'):
            with self.assertRaises(ValueError):
                sync.sync('registry.example.com/team/carddock', self.root / 'out', self.root)
            self.assertFalse((self.root / 'out').exists())

    def test_failed_anonymous_access_never_produces_an_installer(self):
        with patch.dict(os.environ, CN_REGISTRY_USERNAME='test', CN_REGISTRY_PASSWORD='test-only'), patch.object(sync, 'inspect', side_effect=[self.manifest, subprocess.CalledProcessError(1, ['skopeo', 'inspect'])]), patch.object(sync, 'run'):
            with self.assertRaises(subprocess.CalledProcessError):
                sync.sync('registry.example.com/team/carddock', self.root / 'out', self.root)
            self.assertFalse((self.root / 'out').exists())

    def test_success_uses_stdin_secrets_and_pins_both_architectures(self):
        with patch.dict(os.environ, CN_REGISTRY_USERNAME='test', CN_REGISTRY_PASSWORD='test-only'), patch.object(sync, 'inspect', return_value=self.manifest) as inspect, patch.object(sync, 'run') as run:
            sync.sync('registry.example.com/team/carddock', self.root / 'out', self.root)
            login, copy = run.call_args_list
            self.assertIn('--password-stdin', login.args[0])
            self.assertNotIn('test-only', login.args[0])
            self.assertEqual(login.kwargs['input'], b'test-only\n')
            self.assertIn('--all', copy.args[0])
            self.assertIn('--preserve-digests', copy.args[0])
            self.assertTrue(any('@sha256:' in x for x in copy.args[0]))
            self.assertEqual(inspect.call_count, 4)
            config = (self.root / 'out/compose.cn.yaml').read_text()
            self.assertIn('registry.example.com/team/carddock:1.0.0-nas.4', config)
            receipt = (self.root / 'out/registry-verification.json').read_text()
            self.assertNotIn('test-only', receipt)
