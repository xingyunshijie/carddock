import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / 'admin' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth = load('nas_auth', 'nas_auth.py')
installer = load('admin_install', 'install.py')


class AdminAuthorizationTests(unittest.TestCase):
    def setUp(self):
        auth.CONFIG = {'admin_group': 'nas-operators', 'app_gid': 1200, 'pam_service': 'carddock'}

    def test_explicit_group_accepts_supplementary_membership(self):
        with patch.object(auth.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=1000, pw_gid=100)), patch.object(auth.grp, 'getgrnam', return_value=SimpleNamespace(gr_gid=500)) as group, patch.object(auth.os, 'getgrouplist', return_value=[100, 500]):
            self.assertTrue(auth.administrator('alice'))
            group.assert_called_once_with('nas-operators')

    def test_root_without_configured_membership_is_rejected(self):
        with patch.object(auth.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=0, pw_gid=0)), patch.object(auth.grp, 'getgrnam', return_value=SimpleNamespace(gr_gid=500)), patch.object(auth.os, 'getgrouplist', return_value=[0]):
            self.assertFalse(auth.administrator('root'))

    def test_unknown_account_is_rejected_before_pam(self):
        with patch.object(auth.pwd, 'getpwnam', side_effect=KeyError), patch.object(auth.C, 'CDLL') as library:
            self.assertFalse(auth.authenticate('missing', 'secret'))
            library.assert_not_called()

    def test_certificate_hosts(self):
        self.assertEqual(installer.certificate_san('192.0.2.3'), 'IP:192.0.2.3')
        self.assertEqual(installer.certificate_san('2001:db8::1'), 'IP:2001:db8::1')
        self.assertEqual(installer.certificate_san('nas.example'), 'DNS:nas.example')
        for host in ('https://nas.example', 'nas:8443', 'nas,DNS:evil', 'nas\nexample', '-nas', 'nas..example'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                installer.certificate_san(host)

    def test_group_writable_configuration_rejected(self):
        with patch.object(auth.Path, 'stat', return_value=SimpleNamespace(st_uid=0, st_mode=0o100660)):
            with self.assertRaises(ValueError):
                auth.load_config()


if __name__ == '__main__':
    unittest.main()
