import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from core import Engine


class InitialStorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.share = self.root / 'Photos'
        self.share.mkdir()
        self.engine = Engine(self.root / 'state', [], [self.share])

    def tearDown(self):
        self.engine.db.close()
        self.tmp.cleanup()

    def test_fresh_install_creates_archive_without_enabling_auto_or_backup(self):
        self.engine.initialize_primary('影像归仓')
        self.assertEqual(self.engine.config['primary'], str(self.share / '影像归仓'))
        self.assertTrue((self.share / '影像归仓').is_dir())
        self.assertFalse(self.engine.config['auto'])
        self.assertFalse(self.engine.config['setup_complete'])
        self.assertEqual(self.engine.config['backups'], [])
        saved = json.loads((self.root / 'state/config.json').read_text())
        self.assertEqual(saved['primary'], self.engine.config['primary'])

    def test_saved_empty_choice_is_not_overridden(self):
        self.engine.configure({'primary': ''})
        self.engine.initialize_primary('影像归仓')
        self.assertEqual(self.engine.config['primary'], '')
        self.assertFalse((self.share / '影像归仓').exists())

    def test_user_can_change_primary_and_add_backups_after_install(self):
        self.engine.initialize_primary('影像归仓')
        main, backup = self.share / '新主盘', self.share / '备份'
        main.mkdir(); backup.mkdir()
        self.engine.configure({'primary': str(main), 'backups': [str(backup)], 'setup_complete': True})
        self.engine.initialize_primary('影像归仓')
        self.assertEqual(self.engine.config['primary'], str(main))
        self.assertEqual(self.engine.config['backups'], [str(backup)])
        self.assertTrue(self.engine.config['setup_complete'])

    def test_legacy_settings_do_not_trigger_first_run_setup(self):
        legacy = dict(self.engine.config)
        legacy.pop('setup_complete')
        (self.root / 'state/config.json').write_text(json.dumps(legacy))
        other = Engine(self.root / 'state', [], [self.share])
        try:
            self.assertTrue(other.config['setup_complete'])
        finally:
            other.db.close()

    def test_default_directory_cannot_escape_shared_root(self):
        for value in ('..', '../outside', '/outside', 'a/b', 'a\\b'):
            with self.assertRaises(ValueError):
                self.engine.initialize_primary(value)
        outside = self.root / 'outside'
        outside.mkdir()
        (self.share / '影像归仓').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.engine.initialize_primary('影像归仓')
        self.assertFalse((self.root / 'state/config.json').exists())
