import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from core import physical_overlap

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
from shared_storage import shared_roots
spec = importlib.util.spec_from_file_location('nas_shares', ROOT/'nas-shares.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class SharedStorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_nas_uses_its_own_names_and_paths(self):
        a, b = self.root/'旅行素材', self.root/'Backup Disk'
        a.mkdir(); b.mkdir()
        cfg = self.root/'shares.conf'
        cfg.write_text(f'[global]\nworkgroup = WORKGROUP\n[旅行]\npath = {a}\n[备份盘]\npath = {b}\n[个人目录]\npath = %H\n')
        found = installer.discover([cfg])
        self.assertEqual(found, {'旅行': a, '备份盘': b})
        base = installer.base_configuration()
        base['services']['carddock']['environment']['AUTHENTICATION_PASSWORD'] = 'existing-password'
        config = installer.configuration(base, found)['services']['carddock']
        self.assertEqual(config['environment']['AUTHENTICATION_PASSWORD'], 'existing-password')
        mounts = [m for m in config['volumes'] if isinstance(m, dict)]
        self.assertEqual({m['target'] for m in mounts}, {'/shares/旅行', '/shares/备份盘'})
        self.assertEqual(config['environment']['NAS_SHARED_ROOT'], '/shares')
        self.assertNotIn('TARGET_ROOTS', config['environment'])

    def test_installer_rejects_system_roots_and_unknown_configuration(self):
        cfg = self.root/'invalid.conf'
        cfg.write_text('[unsafe]\npath = /\n')
        with self.assertRaises(ValueError): installer.discover([cfg])
        with self.assertRaises(ValueError): installer.discover([self.root/'missing'])

    def test_reading_share_definitions_never_changes_directory_permissions(self):
        share = self.root/'EmptyShare'; share.mkdir(mode=0o750)
        before = share.stat()
        cfg = self.root/'shares.conf'; cfg.write_text(f'[empty]\npath = {share}\n')
        installer.configuration(installer.base_configuration(), installer.discover([cfg]))
        after = share.stat()
        self.assertEqual((before.st_uid, before.st_gid, before.st_mode), (after.st_uid, after.st_gid, after.st_mode))

    def test_existing_password_dollar_signs_survive_compose_serialization(self):
        target = self.root/'compose.shared.yaml'
        installer.write_private(target, {'services': {'carddock': {'environment': {'AUTHENTICATION_PASSWORD': 'Test$Password'}}}})
        value = json.loads(target.read_text())['services']['carddock']['environment']['AUTHENTICATION_PASSWORD']
        self.assertEqual(value, 'Test$$Password')
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_only_real_granted_directories_are_listed(self):
        parent = self.root/'shares'; parent.mkdir()
        (parent/'实际共享').mkdir()
        (parent/'.hidden').mkdir(); (parent/'@system').mkdir()
        outside = self.root/'outside'; outside.mkdir()
        (parent/'link').symlink_to(outside, target_is_directory=True)
        self.assertEqual(shared_roots(parent), [parent/'实际共享'])
        self.assertEqual(shared_roots(self.root/'missing'), [])

    def test_duplicate_conflicting_share_names_fail_before_installation(self):
        paths = [self.root/'a', self.root/'b']
        configs = []
        for i, path in enumerate(paths):
            path.mkdir(); cfg = self.root/f'{i}.conf'; cfg.write_text(f'[Share]\npath = {path}\n'); configs.append(cfg)
        with self.assertRaises(ValueError): installer.discover(configs)

    def test_nested_bind_mount_aliases_cannot_be_source_and_backup(self):
        a, b = self.root/'mapped-share', self.root/'mapped-archive'
        a.mkdir(); b.mkdir()
        lines = f'1 0 8:2 /docker {a} rw - ext4 /dev/sda rw\n2 0 8:2 /docker/archive {b} rw - ext4 /dev/sda rw\n'
        with patch('core.Path.read_text', return_value=lines):
            self.assertTrue(physical_overlap(a,b))
            self.assertTrue(physical_overlap(b,a))
        separate = lines.replace('/docker/archive', '/other-archive')
        with patch('core.Path.read_text', return_value=separate):
            self.assertFalse(physical_overlap(a,b))
