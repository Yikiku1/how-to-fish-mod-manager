import copy
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import manager


def archive(path, files):
    with zipfile.ZipFile(path, 'w') as z:
        for name, content in files.items():
            z.writestr(name, content)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.game = self.base / 'game'
        self.game.mkdir()
        self.store = manager.Store(self.game)

    def test_plugin_lifecycle_and_reload(self):
        path = self.base / 'mod.zip'
        archive(path, {'manifest.json': json.dumps({'name': 'Demo', 'version_number': '1.0'}),
                       'BepInEx/plugins/Demo/demo.dll': b'fixture'})
        self.store.install_mod(path)
        mod = self.store.state['mods'][0]
        self.assertEqual((self.store.modpath(mod) / 'Demo/demo.dll').read_bytes(), b'fixture')
        with self.assertRaises(ValueError):
            self.store.install_mod(path)
        self.store.toggle(mod)
        self.assertFalse(mod['enabled'])
        self.assertTrue(self.store.modpath(mod).is_dir())
        reloaded = manager.Store(self.game)
        mod = reloaded.state['mods'][0]
        reloaded.toggle(mod)
        self.assertTrue(mod['enabled'])
        reloaded.uninstall(mod)
        self.assertEqual(manager.Store(self.game).state['mods'], [])

    def test_reject_zip_traversal(self):
        path = self.base / 'bad.zip'
        archive(path, {'../escape.dll': b'x'})
        with self.assertRaises(ValueError):
            self.store.install_mod(path)
        self.assertFalse((self.base / 'escape.dll').exists())

    def test_loader_backup(self):
        path = self.base / 'loader.zip'
        (self.game / 'winhttp.dll').write_bytes(b'original')
        archive(path, {'BepInExPack/winhttp.dll': b'new', 'BepInExPack/doorstop_config.ini': b'cfg',
                       'BepInExPack/BepInEx/core/demo.dll': b'core'})
        self.store.install_loader(path)
        self.assertEqual((self.game / 'winhttp.dll').read_bytes(), b'new')
        self.assertEqual((self.store.root / 'loader-backup/winhttp.dll').read_bytes(), b'original')

    def test_loader_failure_restores_original(self):
        path = self.base / 'loader.zip'
        (self.game / 'winhttp.dll').write_bytes(b'original')
        (self.game / 'doorstop_config.ini').mkdir()
        archive(path, {'winhttp.dll': b'new', 'doorstop_config.ini': b'cfg', 'BepInEx/core.dll': b'core'})
        with self.assertRaises(OSError):
            self.store.install_loader(path)
        self.assertEqual((self.game / 'winhttp.dll').read_bytes(), b'original')
        self.assertIsNone(self.store.state['loader'])


class TranslationTests(unittest.TestCase):
    def test_dictionary_and_stale_description(self):
        self.assertEqual(len(manager.TRANSLATIONS), 240)
        for key, value in manager.TRANSLATIONS.items():
            self.assertTrue(value['name'])
            self.assertTrue(value['description'])
            package = {'full_name': key, 'versions': [{'description': 'Updated description'}]}
            self.assertIn('中文待更新', manager.mod_text(package)[1])

    def test_search_toggle_preserves_package(self):
        try:
            root = tk.Tk()
        except tk.TclError as e:
            self.skipTest('需要可用的桌面显示：' + str(e))
        root.withdraw()
        self.addCleanup(root.destroy)
        app = manager.App(root)
        key = 'NekoTeam-HowToFishDevConsole'
        package = {'full_name': key, 'name': 'HowToFishDevConsole', 'owner': 'NekoTeam',
                   'versions': [{'version_number': '1.2.0', 'description': manager.TRANSLATIONS[key]['source_description']}]}
        original = copy.deepcopy(package)
        app.catalog = [package]
        app.query.set('开发者指令控制台')
        root.update()
        self.assertEqual(app.remote.get_children(), ('0',))
        app.remote.selection_set('0')
        app.toggle_language()
        root.update()
        self.assertEqual(app.remote.selection(), ('0',))
        self.assertIn(key, app.remote.item('0', 'values')[0])
        app.toggle_language()
        self.assertIn('生成物品', app.details.get('1.0', 'end'))
        self.assertEqual(package, original)
        app.query.set('not-a-real-mod')
        self.assertEqual(app.remote.get_children(), ())


if __name__ == '__main__':
    unittest.main()
