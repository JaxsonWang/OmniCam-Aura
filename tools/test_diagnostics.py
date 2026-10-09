"""验证实际诊断脚本的归档内容、读取边界、脱敏和失败清理。"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parent.parent
PACKAGES = ('com.oplus.camera', 'com.coloros.gallery3d', 'local.omnicam.aura')


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='aura diagnostics ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.module = self.root / 'module with spaces'
        self.module.mkdir()
        self.output = self.root / 'Download with spaces $(touch injected)'
        self.logs = self.root / 'lsposed'
        self.logs.mkdir()
        self.mounts = self.root / 'mountinfo'
        self.mounts.write_text(
            '101 100 0:1 /adb/modules/omnicam_aura/system/odm/lib64/libAlgoInterface.so '
            '/odm/lib64/libAlgoInterface.so ro - ext4 /dev/block/data rw\n'
            '102 100 0:1 /adb/modules/unrelated/private /unrelated ro - ext4 /dev/block/data rw\n')
        source = (PROJECT / 'module/diagnostics.sh').read_text()
        # 只替换设备绝对路径，生产脚本不增加测试来源或备用诊断入口。
        source = source.replace('/data/adb/lspd/log/', str(self.logs) + '/')
        source = source.replace('/proc/self/mountinfo', str(self.mounts))
        # shell 的 glob 需要保留，测试目录含空格时应引用其目录部分。
        source = source.replace(f'{self.logs}/modules_*.log', f'"{self.logs}"/modules_*.log')
        source = source.replace(f'{self.logs}/modules.log', f'"{self.logs}"/modules.log')
        source = source.replace(f'cat {self.mounts}', f'cat "{self.mounts}"')
        self.script = self.module / 'diagnostics.sh'
        self.script.write_text(source)
        (self.module / 'module.prop').write_text('id=omnicam_aura\nversion=1.1.2\nversionCode=9\n')
        (self.module / 'control.sh').write_text('''
[ "$#" -eq 1 ] && [ "$1" = status ] || exit 2
printf '%s\\n' '{"model":"PLK110","compatible":true,"inverseLight":false,"activeInverseLight":null}'
''')
        (self.module / 'bind.log').write_text('\n'.join(f'bind row {i}' for i in range(300)) + '\n')
        (self.module / 'service.log').write_text(
            'Aura: 配置与元模块算法库已就绪\n'
            'Aura: token=SECRET_TOKEN\n'
            'Aura: latitude=25.12345 longitude=121.56789\n'
            'Aura: file=/sdcard/DCIM/Private Image.jpg\n'
            'Aura: cache=/data/user/0/com.oplus.camera/private/image.heic\n'
            'Aura: endpoint=https://private.example/file?id=secret\n'
            'Aura: peer=192.168.50.168:5555 ipv6=fe80::dead:beef\n'
            'Aura: owner=person@example.invalid contact=13812345678\n')
        (self.module / 'mount-ready').touch()
        (self.logs / 'modules_old.log').write_text('local.omnicam.aura: obsolete log\n')
        os.utime(self.logs / 'modules_old.log', (1, 1))
        (self.logs / 'modules_new.log').write_text(
            'local.omnicam.aura: Symbols: 198 resolved, 0 missing\n'
            'other.module: PRIVATE_OTHER_MODULE\n'
            'local.omnicam.aura.extra: PRIVATE_PREFIX_COLLISION\n')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.trace = self.root / 'commands.jsonl'
        self.env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                    'DIAGNOSTICS_TRACE': str(self.trace), 'COPYFILE_DISABLE': '1'}
        for command in ('getprop', 'dumpsys', 'pidof', 'logcat'):
            self.stub(command, '''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
name = Path(sys.argv[0]).name
with open(os.environ['DIAGNOSTICS_TRACE'], 'a') as stream:
    stream.write(json.dumps([name, *args]) + '\\n')
if name == 'getprop':
    values = {'ro.product.model': 'PLK110', 'ro.product.device': 'OP5E1FL1',
              'ro.product.manufacturer': 'OPPO', 'ro.build.version.release': '16',
              'ro.build.version.sdk': '36', 'ro.build.display.id': 'PLK110_17.0.0.105(CN01)',
              'ro.build.version.security_patch': '2026-09-05'}
    if len(args) != 1 or args[0] not in values:
        raise SystemExit(40)
    print(values[args[0]])
elif name == 'dumpsys':
    if args != ['package', args[-1]] or args[-1] not in (
            'com.oplus.camera', 'com.coloros.gallery3d', 'local.omnicam.aura'):
        raise SystemExit(41)
    print('PRIVATE_PACKAGE_FIELD=do-not-share')
    print('    versionCode=60000 minSdk=30 targetSdk=36')
    print('    versionName=7.006.125')
elif name == 'pidof':
    if args == ['com.oplus.camera']:
        print('101')
    else:
        raise SystemExit(1)
elif name == 'logcat':
    if '--pid=101' in args:
        print('10-09 12:00:00.000 101 102 W Camera: save failed /storage/emulated/0/DCIM/secret.heic')
        print('10-09 12:00:00.001 101 102 I Aura: compatibility checked')
    elif args == ['-d', '-v', 'threadtime', '-t', '600', '-b', 'crash', '*:V']:
        print('10-09 12:00:00.000 200 200 E AndroidRuntime: FATAL EXCEPTION: main')
        print('10-09 12:00:00.001 200 200 E AndroidRuntime: Process: other.application, PID: 200')
        print('10-09 12:00:00.002 200 200 E AndroidRuntime: PRIVATE_OTHER_CRASH')
        print('10-09 12:00:00.003 101 101 E AndroidRuntime: FATAL EXCEPTION: main')
        print('10-09 12:00:00.004 101 101 E AndroidRuntime: Process: com.oplus.camera, PID: 101')
        print('10-09 12:00:00.005 101 101 E AndroidRuntime: java.lang.IllegalStateException: capture failed')
        print('10-09 12:00:00.006 101 101 E AndroidRuntime: at com.oplus.camera.Capture.save(Capture.java:12)')
        print('10-09 12:00:00.007 300 300 E AndroidRuntime: FATAL EXCEPTION: main')
        print('10-09 12:00:00.008 300 300 E AndroidRuntime: Process: other.application, PID: 300')
        print('10-09 12:00:00.009 300 300 E AndroidRuntime: PRIVATE_NEXT_CRASH')
    else:
        raise SystemExit(42)
''')

    def stub(self, name, body):
        command = self.bin / name
        command.write_text(f'#!{sys.executable}\n{body}')
        command.chmod(0o755)

    def run_export(self, extra=()):
        return subprocess.run(['sh', str(self.script), '--output-dir', str(self.output), *extra],
                              env=self.env, capture_output=True, text=True)

    def read_export(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        archive_path = Path(lines[0])
        self.assertTrue(archive_path.is_absolute())
        self.assertEqual(archive_path.parent, self.output.resolve())
        self.assertTrue(archive_path.name.endswith('.tar.gz'))
        with tarfile.open(archive_path, 'r:gz') as archive:
            files = {member.name: archive.extractfile(member).read().decode()
                     for member in archive.getmembers() if member.isfile()}
            self.assertTrue(all(member.name.startswith('report') for member in archive.getmembers()))
        self.assertFalse(list(self.module.glob('.diagnostics.*')))
        return archive_path, files

    def test_archive_has_useful_bounded_data_and_only_whitelisted_sources(self):
        _, files = self.read_export(self.run_export())
        self.assertIn('PLK110_17.0.0.105(CN01)', files['report/device.txt'])
        self.assertIn('versionCode=60000\nversionName=7.006.125', files['report/version-com.oplus.camera.txt'])
        self.assertIn('mount-ready=present', files['report/module-state.txt'])
        self.assertIn('skip_mount=absent', files['report/module-state.txt'])
        control = json.loads(files['report/control-status.txt'])
        self.assertTrue(control['compatible'])
        self.assertFalse(control['inverseLight'])
        self.assertIsNone(control['activeInverseLight'])
        self.assertNotIn('bind row 49\n', files['report/bind.log'])
        self.assertIn('bind row 50\n', files['report/bind.log'])
        self.assertIn('bind row 299', files['report/bind.log'])
        self.assertIn('198 resolved, 0 missing', files['report/lsposed.log'])
        self.assertIn('libAlgoInterface.so', files['report/mounts.txt'])
        self.assertIn('capture failed', files['report/crashes.log'])
        self.assertIn('Capture.java:12', files['report/crashes.log'])
        self.assertIn('不可用', files['report/logcat-local.omnicam.aura.log'])
        commands = [json.loads(line) for line in self.trace.read_text().splitlines()]
        properties = [command for command in commands if command[0] == 'getprop']
        self.assertEqual(len(properties), 7)
        self.assertTrue(all(len(command) == 2 for command in properties))
        self.assertEqual({command[2] for command in commands if command[0] == 'dumpsys'}, set(PACKAGES))
        process_logs = [command for command in commands if command[0] == 'logcat' and '--pid=101' in command]
        self.assertEqual(len(process_logs), 1)
        self.assertIn('*:W', process_logs[0])
        self.assertFalse((self.root / 'injected').exists())

    def test_privacy_filters_remove_personal_data_and_unrelated_entries(self):
        _, files = self.read_export(self.run_export())
        content = '\n'.join(files.values())
        for private in ('SECRET_TOKEN', '25.12345', '121.56789', '/sdcard/DCIM', '/storage/emulated',
                        '/data/user/0', 'private.example', 'secret.heic', 'Private Image', 'Image.jpg',
                        '192.168.50.168', 'fe80::dead:beef', 'person@example.invalid', '13812345678',
                        'PRIVATE_OTHER_MODULE', 'PRIVATE_PREFIX_COLLISION', 'PRIVATE_PACKAGE_FIELD',
                        'PRIVATE_OTHER_CRASH', 'PRIVATE_NEXT_CRASH', '/unrelated', 'obsolete log'):
            with self.subTest(private=private):
                self.assertNotIn(private, content)
        self.assertIn('[PRIVATE_PATH]', content)
        self.assertIn('[URI]', content)
        self.assertIn('[IP]', content)
        self.assertIn('分享前请自行解压检查', content)

    def test_missing_sources_and_permission_failure_are_visible_in_export(self):
        (self.module / 'bind.log').unlink()
        (self.module / 'control.sh').unlink()
        shutil.rmtree(self.logs)
        self.stub('logcat', "import sys\nprint('Permission denied token=PRIVATE_ERROR', file=sys.stderr)\nsys.exit(13)\n")
        _, files = self.read_export(self.run_export())
        self.assertIn('不可用', files['report/bind.log'])
        self.assertIn('不可用', files['report/lsposed.log'])
        self.assertIn('不可用', files['report/control-status.txt'])
        self.assertIn('control.sh', files['report/control-status.txt'])
        self.assertIn('exit=13', files['report/crashes.log'])
        self.assertNotIn('PRIVATE_ERROR', '\n'.join(files.values()))
        self.assertIn('PLK110', files['report/device.txt'])

    def test_invalid_saved_control_state_is_reported_with_the_actual_error(self):
        (self.module / 'control.sh').write_text('''
echo 'Aura: 反色补光开关值无效，未修改设置' >&2
exit 7
''')
        _, files = self.read_export(self.run_export())
        control = files['report/control-status.txt']
        self.assertIn('不可用', control)
        self.assertIn('exit=7', control)
        self.assertIn('反色补光开关值无效，未修改设置', control)
        self.assertNotIn('"compatible":true', control)

    def test_repeat_export_preserves_existing_files_and_gets_unique_names(self):
        first, _ = self.read_export(self.run_export())
        first_bytes = first.read_bytes()
        sentinel = self.output / 'user-owned.tar.gz'
        sentinel.write_text('user file')
        second, _ = self.read_export(self.run_export())
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), first_bytes)
        self.assertEqual(sentinel.read_text(), 'user file')
        self.assertEqual(len(list(self.output.iterdir())), 3)

    def test_archive_or_final_write_failure_has_no_finished_file_or_temp_directory(self):
        for command in ('tar', 'gzip', 'cp'):
            with self.subTest(command=command):
                self.stub(command, "import sys\nprint('injected archive failure', file=sys.stderr)\nsys.exit(17)\n")
                result = self.run_export()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
                self.assertIn('诊断导出失败', result.stderr)
                self.assertFalse(list(self.module.glob('.diagnostics.*')))
                self.assertEqual(list(self.output.iterdir()), [])
                (self.bin / command).unlink()

    def test_filename_collision_never_overwrites_or_deletes_existing_user_file(self):
        self.output.mkdir()
        sentinel = self.output / 'OmniCam-Aura-20261009-120000-FIXED123.tar.gz'
        sentinel.write_text('keep this existing file')
        self.stub('date', "print('20261009-120000')\n")
        self.stub('mktemp', '''
import sys
from pathlib import Path
directory = Path(sys.argv[-1].replace('XXXXXXXX', 'FIXED123'))
directory.mkdir()
print(directory)
''')
        result = self.run_export()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertIn('唯一文件名', result.stderr)
        self.assertEqual(sentinel.read_text(), 'keep this existing file')
        self.assertEqual(list(self.output.iterdir()), [sentinel])
        self.assertFalse(list(self.module.glob('.diagnostics.*')))

    def test_invalid_arguments_fail_without_running_any_collection(self):
        for args in (('--output-dir',), ('--unexpected',), ('--module-dir', '/does-not-exist')):
            with self.subTest(args=args):
                result = subprocess.run(['sh', str(self.script), *args], env=self.env,
                                        capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
                self.assertFalse(self.trace.exists())


if __name__ == '__main__':
    unittest.main()
