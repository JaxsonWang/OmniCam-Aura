"""在临时模块运行真实控制脚本，验证网页状态、明确开关和挂载状态合同。"""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parent.parent


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.module = self.root / 'module with spaces'
        self.module.mkdir()
        self.state_dir = self.root / 'persistent'
        self.state = self.state_dir / 'inverse-light'
        self.mountinfo = self.root / 'mountinfo'
        self.mountinfo.touch()
        self.live = self.root / 'odm/oplus_camera_config'
        self.live.parent.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for name in ('device.sh', 'inverse-light.sh', 'action.sh', 'module.prop'):
            shutil.copy2(PROJECT / 'module' / name, self.module / name)
        source = (PROJECT / 'module/control.sh').read_text().replace(
            '/data/adb/omnicam_aura', str(self.state_dir)).replace(
            '/proc/self/mountinfo', str(self.mountinfo)).replace(
            '/odm/etc/camera/config/oplus_camera_config', str(self.live))
        (self.module / 'control.sh').write_text(source)
        self.base = self.module / 'profiles/PLK110/config/oplus_camera_config'
        self.base.parent.mkdir(parents=True)
        self.base.write_text('base\n')
        self.runtime = self.module / 'runtime/oplus_camera_config'
        self.runtime.parent.mkdir()
        self.runtime.write_text('inverse\n')
        self.command('getprop', '''case "$1" in
ro.product.model) printf '%s\n' "$TEST_MODEL" ;;
ro.build.display.id) printf '%s\n' "$TEST_FIRMWARE" ;;
ro.build.version.sdk) printf '%s\n' "$TEST_SDK" ;;
esac
''')
        self.command('dumpsys', '''[ "$*" = 'package com.oplus.camera' ] || exit 3
[ "$FAIL_DUMPSYS" = 0 ] || { echo 'injected dumpsys failure' >&2; exit 4; }
printf 'Packages:\n    versionName=%s\n' "$TEST_CAMERA_VERSION"
''')
        self.command('mv', '''[ "$FAIL_MOVE" = 0 ] || { echo 'injected move failure' >&2; exit 5; }
exec ''' + shlex.quote(shutil.which('mv')) + ' "$@"\n')
        self.env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                    'MODEL': 'PLK110', 'FIRMWARE': 'PLK110_17.0.0.105(CN01)',
                    'SDK': '37', 'CAMERA_VERSION': '7.006.125',
                    'FAIL_DUMPSYS': '0', 'FAIL_MOVE': '0'}

    def command(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/sh\n' + body)
        path.chmod(0o755)

    def run_control(self, *args, script='control.sh', env=None):
        environment = {**self.env, **(env or {})}
        for key in ('MODEL', 'FIRMWARE', 'SDK', 'CAMERA_VERSION'):
            environment['TEST_' + key] = environment.pop(key)
        return subprocess.run(['sh', str(self.module / script), *args],
                              env=environment, capture_output=True, text=True)

    def status(self, *args, env=None):
        result = self.run_control(*(args or ('status',)), env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1, result.stdout)
        data = json.loads(result.stdout)
        self.assertIsInstance(data['compatible'], bool)
        self.assertIsInstance(data['inverseLight'], bool)
        self.assertIn(data['activeInverseLight'], (None, True, False))
        return data

    def write_state(self, content):
        self.state_dir.mkdir(exist_ok=True)
        self.state.write_text(content)

    def mount_live(self, content):
        (self.module / 'mount-ready').touch()
        self.live.write_text(content)
        self.mountinfo.write_text(f'100 1 0:1 /aura/runtime {self.live} rw - ext4 /dev/test rw\n')

    def test_status_defaults_off_without_creating_persistent_state(self):
        data = self.status()
        self.assertEqual(data['model'], 'PLK110')
        self.assertEqual(data['androidSdk'], '37')
        self.assertEqual(data['firmware'], self.env['FIRMWARE'])
        self.assertEqual(data['cameraVersion'], self.env['CAMERA_VERSION'])
        self.assertTrue(data['compatible'])
        self.assertFalse(data['inverseLight'])
        self.assertIsNone(data['activeInverseLight'])
        self.assertFalse(self.state_dir.exists())

    def test_explicit_switches_are_idempotent_and_preserve_private_modes(self):
        for desired, value in (('on', True), ('on', True), ('off', False), ('off', False)):
            with self.subTest(desired=desired):
                data = self.status('inverse', desired)
                self.assertEqual(data['inverseLight'], value)
                self.assertIsNone(data['activeInverseLight'])
                self.assertEqual(self.state.read_text(), '1\n' if value else '0\n')
                self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)
                self.assertEqual(self.state_dir.stat().st_mode & 0o777, 0o700)
                self.assertEqual(list(self.state_dir.iterdir()), [self.state])

    def test_generated_policy_accepts_numeric_patches_but_rejects_other_branches(self):
        for firmware, camera in (('PLK110_17.0.0.102(CN01)', '7.006.100'),
                                 ('PLK110_17.0.0.105(CN01)', '7.006.125'),
                                 ('PLK110_17.0.0.999(CN01)', '7.006.999')):
            with self.subTest(firmware=firmware, camera=camera):
                self.assertTrue(self.status(env={'FIRMWARE': firmware, 'CAMERA_VERSION': camera})['compatible'])
        for changes in ({'FIRMWARE': 'PLK110_17.0.1.105(CN01)'},
                        {'FIRMWARE': 'PLK110_17.0.0.105(EX01)'},
                        {'FIRMWARE': 'PLK110_17.0.0.105beta(CN01)'},
                        {'FIRMWARE': 'PLK110_17.0.0.(CN01)'},
                        {'SDK': '36'}, {'CAMERA_VERSION': '7.007.125'},
                        {'CAMERA_VERSION': '7.006.125-beta'}, {'CAMERA_VERSION': '7.006.'}):
            with self.subTest(changes=changes):
                data = self.status(env=changes)
                self.assertFalse(data['compatible'])
                self.assertTrue(data['reason'])
                self.assertNotEqual(self.run_control('inverse', 'on', env=changes).returncode, 0)
                self.assertFalse(self.state.exists())

    def test_incompatible_plk_can_disable_a_saved_choice(self):
        self.write_state('1\n')
        data = self.status('inverse', 'off', env={'FIRMWARE': 'PLK110_18.0.0.105(CN01)'})
        self.assertFalse(data['compatible'])
        self.assertFalse(data['inverseLight'])
        self.assertEqual(self.state.read_text(), '0\n')

    def test_pma_and_unsupported_devices_cannot_modify_plk_choice(self):
        for model, version, compatible in (('PMA110', '7.006.77', True),
                                           ('PMA110', '7.006.125', False),
                                           ('OTHER', '7.006.125', False)):
            with self.subTest(model=model, version=version):
                env = {'MODEL': model, 'CAMERA_VERSION': version}
                self.assertEqual(self.status(env=env)['compatible'], compatible)
                for value in ('on', 'off'):
                    self.assertNotEqual(self.run_control('inverse', value, env=env).returncode, 0)
                self.assertFalse(self.state.exists())

    def test_invalid_state_fails_without_overwriting_for_status_or_switches(self):
        for invalid in ('', 'bad\n', '2\n', '1\n0\n', '1\n\n', '1\x00\n'):
            with self.subTest(value=invalid):
                self.write_state(invalid)
                for command in (('status',), ('inverse', 'on'), ('inverse', 'off')):
                    result = self.run_control(*command)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('开关值无效', result.stderr)
                    self.assertEqual(result.stdout, '')
                    self.assertEqual(self.state.read_text(), invalid)

    def test_state_directory_instead_of_file_is_reported_as_read_failure(self):
        self.state.mkdir(parents=True)
        result = self.run_control('status')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('无法读取', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_failed_atomic_replace_keeps_previous_choice_and_removes_temp_file(self):
        self.write_state('0\n')
        result = self.run_control('inverse', 'on', env={'FAIL_MOVE': '1'})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('无法保存', result.stderr)
        self.assertEqual(self.state.read_text(), '0\n')
        self.assertEqual(list(self.state_dir.iterdir()), [self.state])

    def test_active_state_requires_mount_marker_mountinfo_and_matching_live_bytes(self):
        self.write_state('0\n')
        self.mount_live('inverse\n')
        self.assertTrue(self.status()['activeInverseLight'])
        self.write_state('1\n')
        self.mount_live('base\n')
        self.assertFalse(self.status()['activeInverseLight'])
        self.mount_live('unknown configuration\n')
        self.assertIsNone(self.status()['activeInverseLight'])
        self.mount_live('inverse\n')
        self.mountinfo.write_text('')
        self.assertIsNone(self.status()['activeInverseLight'])
        self.mount_live('inverse\n')
        (self.module / 'mount-ready').unlink()
        self.assertIsNone(self.status()['activeInverseLight'])

    def test_policy_source_failure_is_a_visible_compatibility_reason_and_off_still_works(self):
        with (self.module / 'device.sh').open('a') as output:
            output.write("\nDEVICE_POLICY_ERROR='测试策略失效'\nreturn 1\n")
        self.write_state('1\n')
        data = self.status()
        self.assertFalse(data['compatible'])
        self.assertIn('测试策略失效', data['reason'])
        self.assertFalse(self.status('inverse', 'off')['inverseLight'])
        (self.module / 'device.sh').unlink()
        data = self.status()
        self.assertFalse(data['compatible'])
        self.assertIn('策略文件不可读', data['reason'])

    def test_failed_camera_read_is_not_treated_as_compatible(self):
        for env in ({'FAIL_DUMPSYS': '1'}, {'CAMERA_VERSION': ''}):
            with self.subTest(env=env):
                data = self.status(env=env)
                self.assertFalse(data['compatible'])
                self.assertIn('相机版本', data['reason'])
                self.assertNotEqual(self.run_control('inverse', 'on', env=env).returncode, 0)

    def test_json_escapes_control_characters_quotes_and_backslashes(self):
        firmware = 'PLK110_"version"\\新版本\n' + ''.join(chr(i) for i in range(1, 32)) + 'tail'
        data = self.status(env={'FIRMWARE': firmware})
        self.assertEqual(data['firmware'], firmware)
        self.assertIn(firmware, data['reason'])
        self.assertFalse(data['compatible'])

    def test_unknown_commands_and_values_do_not_change_state(self):
        for args in ((), ('status', 'extra'), ('inverse',), ('inverse', 'toggle'),
                     ('inverse', 'on; exit 0'), ('export',)):
            with self.subTest(args=args):
                self.assertNotEqual(self.run_control(*args).returncode, 0)
                self.assertFalse(self.state_dir.exists())


if __name__ == '__main__':
    unittest.main()
