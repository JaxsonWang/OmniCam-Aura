"""手动补光只改变显式选择后的运行时配置，默认配置和 PMA110 不受影响。"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parent.parent
KEY = 'com.oplus.feature.colorful.screen.torch.config'


class InverseLightTests(unittest.TestCase):
    def prepare(self, root, value, model='PLK110', config=None):
        base = root / 'config'
        base.mkdir(exist_ok=True)
        original = config if config is not None else json.loads(
            (PROJECT / 'module/profiles/PLK110/config/oplus_camera_config').read_bytes())
        (base / 'oplus_camera_config').write_text(json.dumps(original, indent=2) + '\n')
        state = root / 'manual-choice'
        if value is not None:
            state.write_text(value)
        script = '''
MODDIR=$2
CONFIG_DIR=$2/config
DEVICE=$3
. "$1"
prepare_inverse_light_config "$2/manual-choice"
'''
        result = subprocess.run(['sh', '-c', script, 'test', str(PROJECT / 'module/inverse-light.sh'),
                                 str(root), model], capture_output=True, text=True)
        self.assertEqual(json.loads((base / 'oplus_camera_config').read_bytes()), original)
        return result, original, root / 'runtime/oplus_camera_config'

    def test_default_off_and_explicit_off_do_not_generate_an_override(self):
        for value in (None, '0\n'):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                result, _, runtime = self.prepare(Path(directory), value)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(runtime.exists())

    def test_manual_on_adds_only_bit_four_without_changing_any_base_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            result, original, runtime = self.prepare(Path(directory), '1\n')
            self.assertEqual(result.returncode, 0, result.stderr)
            generated = json.loads(runtime.read_bytes())
            self.assertEqual(generated[:-1], original)
            self.assertEqual(generated[-1]['VendorTag'], KEY)
            self.assertEqual(int(generated[-1]['Value'], 2), 4)

    def test_invalid_choice_and_unexpected_base_key_fail_visibly(self):
        cases = [('bad\n', None), ('1\n\n', None), ('1\x00\n', None),
                 ('1\n', [{'VendorTag': KEY, 'Value': '10'}])]
        for value, config in cases:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                result, _, runtime = self.prepare(Path(directory), value, config=config)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('停止挂载', result.stderr)
                self.assertFalse(runtime.exists())

    def test_pma110_is_not_affected_by_plk110_manual_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            result, _, runtime = self.prepare(Path(directory), '1\n', 'PMA110')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(runtime.exists())

    def test_action_toggles_choice_across_module_replacement_and_uninstall_keeps_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / 'persistent'
            commands = root / 'bin'
            commands.mkdir()
            (commands / 'getprop').write_text('''#!/bin/sh
case "$1" in
ro.product.model) echo PLK110 ;;
ro.build.display.id) echo 'PLK110_17.0.0.105(CN01)' ;;
ro.build.version.sdk) echo 37 ;;
esac
''')
            (commands / 'dumpsys').write_text("#!/bin/sh\necho '  versionName=7.006.125'\n")
            for command in commands.iterdir():
                command.chmod(0o755)
            env = {**os.environ, 'PATH': str(commands) + os.pathsep + os.environ['PATH']}
            for generation in ('module', 'modules_update'):
                module = root / generation
                module.mkdir()
                for name in ('device.sh', 'inverse-light.sh', 'action.sh', 'module.prop'):
                    shutil.copy2(PROJECT / 'module' / name, module / name)
                (module / 'control.sh').write_text((PROJECT / 'module/control.sh').read_text().replace(
                    '/data/adb/omnicam_aura', str(state)))
                result = subprocess.run(['sh', str(module / 'action.sh')], env=env,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((state / 'inverse-light').read_text(), '1\n' if generation == 'module' else '0\n')
            (state / 'legacy-overrides.snapshot').write_text('original')
            uninstall = (PROJECT / 'module/uninstall.sh').read_text().replace('/data/adb/omnicam_aura', str(state))
            subprocess.run(['sh', '-c', uninstall], check=True)
            self.assertFalse((state / 'inverse-light').exists())
            self.assertEqual((state / 'legacy-overrides.snapshot').read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
