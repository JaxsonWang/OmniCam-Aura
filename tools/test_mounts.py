"""执行实际挂载脚本，以桩记录 mount / umount 顺序并注入各阶段失败。"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parent.parent
CONFIG_NAMES = ('camera_unit_config', 'camera_unit_feature_config.protobuf', 'oplus_camera_config',
                'oplus_camera_algo_switch_config', 'oplus_camera_preview_decision_config.json')
LIBRARIES = ('libBasicTonePhotoX9.so', 'libBasicTonePhotoX10.so', 'libBasicTonePhoto.so',
             'libAlgoInterface.so', 'libmsnativefilter.so')


class MountTests(unittest.TestCase):
    def test_mountinfo_parent_chain_accepts_data_root_only_when_aura_is_top(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mountinfo = root / 'mountinfo'
            helper = root / 'mount-state.sh'
            helper.write_text((PROJECT / 'module/mount-state.sh').read_text().replace(
                '/proc/self/mountinfo', str(mountinfo)))
            target = '/odm/lib64/libBasicTonePhoto.so'
            source = '/data/adb/modules/omnicam_aura/system/odm/lib64/libBasicTonePhoto.so'
            mountinfo.write_text(
                f'800 271 0:1 /vendor/odm/lib64/libBasicTonePhoto.so {target} ro - erofs /dev/block/odm ro\n'
                f'269 800 0:1 /adb/modules/omnicam_aura/system/odm/lib64/libBasicTonePhoto.so {target} rw '
                '- ext4 /dev/block/data rw\n')
            script = '. "$0"; mount_entry_owned "$1" "$2"'
            owned = subprocess.run(['sh', '-c', script, str(helper), source, target])
            self.assertEqual(owned.returncode, 0)
            with mountinfo.open('a') as output:
                output.write(f'150 269 0:1 /adb/modules/other/system/odm/lib64/libBasicTonePhoto.so {target} rw '
                             '- ext4 /dev/block/data rw\n')
            covered = subprocess.run(['sh', '-c', script, str(helper), source, target])
            self.assertNotEqual(covered.returncode, 0)

    def execute(self, root, model='PLK110', fail_at=0, umount_fail=False):
        module, odm = root / 'module', root / 'odm'
        module.mkdir()
        shutil.copy2(PROJECT / 'module/device.sh', module / 'device.sh')
        shutil.copy2(PROJECT / 'module/inverse-light.sh', module / 'inverse-light.sh')
        mountinfo = root / 'mountinfo'
        mountinfo.touch()
        mount_state = (PROJECT / 'module/mount-state.sh').read_text().replace(
            '/proc/self/mountinfo', str(mountinfo))
        (module / 'mount-state.sh').write_text(mount_state)
        # 仅把绝对 ODM 路径指向临时目录；生产脚本不引入测试开关。
        source = (PROJECT / 'module/post-fs-data.sh').read_text().replace('/odm/', str(odm) + '/')
        (module / 'post-fs-data.sh').write_text(source)
        for relative in ('etc/camera/config', 'etc/camera/meishe_lut', 'etc/camera/basictone/setting', 'lib64/camera'):
            (odm / relative).mkdir(parents=True, exist_ok=True)
        for name in CONFIG_NAMES:
            config = module / ('profiles/PLK110/config' if model == 'PLK110' else 'payload') / name
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(name)
            (odm / 'etc/camera/config' / name).touch()
        for name in ('polaroid_sdr.mslut', 'fuji-nc.bin'):
            path = module / 'payload/meishe_lut' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            (odm / 'etc/camera/meishe_lut' / name).touch()
        (odm / 'etc/camera/basictone/setting_Retro').mkdir()
        (odm / 'etc/camera/basictone/setting_Retro/SimTool_Master.ini').touch()
        (module / 'payload/x10_basictone').mkdir()
        for lens in ('main', 'wide', 'tele', 'ultratele'):
            path = module / 'payload/isp' / f'com.qti.tuned.lighthouse{lens}.bin'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        for name in ('gamma_preview_sdr_conf.json', 'gamma_quick_sdr_conf.json', 'gamma_preview_hdr_conf.json'):
            path = module / 'payload/gamma' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        script = '''
getprop() { case "$1" in ro.product.model) echo "$MODEL";; ro.build.display.id) echo 'PLK110_17.0.0.102(CN01)';; ro.build.version.sdk) echo 37;; esac; }
chown() { :; }
chmod() { :; }
chcon() { :; }
MOUNT_CALLS=0
mount() {
    MOUNT_CALLS=$((MOUNT_CALLS + 1))
    if [ "$MOUNT_CALLS" = "$FAIL_AT" ]; then echo "failed $3" >> "$TRACE"; return 1; fi
    echo "mount $3" >> "$TRACE"
    echo "$MOUNT_CALLS 5000 0:1 $2 $3 rw - ext4 /dev/block/test rw" >> "$MOUNTINFO"
}
umount() {
    echo "umount $1" >> "$TRACE"
    [ "$UMOUNT_FAIL" = 0 ]
}
. "$0"
'''
        env = {**os.environ, 'MODEL': model, 'FAIL_AT': str(fail_at), 'TRACE': str(root / 'trace'),
               'MOUNTINFO': str(mountinfo),
               'UMOUNT_FAIL': str(int(umount_fail))}
        result = subprocess.run(['sh', '-c', script, str(module / 'post-fs-data.sh')],
                                env=env, capture_output=True, text=True)
        trace = (root / 'trace').read_text().splitlines()
        mounted = [s.removeprefix('mount ') for s in trace if s.startswith('mount ')]
        unmounted = [s.removeprefix('umount ') for s in trace if s.startswith('umount ')]
        return result, module, mounted, unmounted

    def execute_service(self, root, module, odm):
        trace = root / 'trace'
        mountinfo = root / 'mountinfo'
        source = (PROJECT / 'module/service.sh').read_text().replace('"/odm/', f'"{odm}/')
        (module / 'service.sh').write_text(source)
        system_lib = module / 'system/odm/lib64'
        target_lib = odm / 'lib64'
        system_lib.mkdir(parents=True)
        target_lib.mkdir(parents=True, exist_ok=True)
        for offset, name in enumerate(LIBRARIES):
            library_source = system_lib / name
            library_target = target_lib / name
            library_source.write_text(f'Aura {name}')
            library_target.write_text(f'Aura {name}')
            original_id = 800 + offset
            aura_id = 269 + offset
            original_parent = 271 if offset == 0 else 5000 + offset
            with mountinfo.open('a') as output:
                output.write(f'{original_id} {original_parent} 0:1 /vendor/odm/lib64/{name} {library_target} rw '
                             '- erofs /dev/block/odm ro\n')
                output.write(f'{aura_id} {original_id} 0:1 {library_source} {library_target} rw '
                             '- ext4 /dev/block/test rw\n')
            if name == LIBRARIES[-1]:
                library_target.write_text('other module')
                with mountinfo.open('a') as output:
                    output.write(f'150 {aura_id} 0:1 /adb/modules/other/system/odm/lib64/{name} {library_target} rw '
                                 '- ext4 /dev/block/test rw\n')
        unrelated = target_lib / 'unrelated.so'
        unrelated.touch()
        with mountinfo.open('a') as output:
            output.write(f'200 1 0:1 /adb/modules/other/system/odm/lib64/unrelated.so {unrelated} rw '
                         '- ext4 /dev/block/test rw\n')
        script = '''
getprop() { case "$1" in ro.product.model) echo 'PLK110';; ro.build.display.id) echo 'PLK110_17.0.0.102(CN01)';; ro.build.version.sdk) echo 37;; esac; }
umount() { echo "umount $1" >> "$TRACE"; }
. "$0"
'''
        result = subprocess.run(['sh', '-c', script, str(module / 'service.sh')],
                                env={**os.environ, 'TRACE': str(trace)}, capture_output=True, text=True)
        return result, unrelated

    def test_every_failed_mount_rolls_back_in_reverse_order(self):
        for model, total in (('PLK110', 7), ('PMA110', 14)):
            for failed in range(1, total + 1):
                with self.subTest(model=model, failed=failed), tempfile.TemporaryDirectory() as directory:
                    result, module, mounted, unmounted = self.execute(Path(directory), model, failed)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(len(mounted), failed - 1)
                    self.assertEqual(unmounted, list(reversed(mounted)))
                    self.assertTrue((module / 'skip_mount').is_file())
                    self.assertFalse((module / 'mount-ready').exists())

    def test_success_keeps_mounts(self):
        for model, total in (('PLK110', 7), ('PMA110', 14)):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as directory:
                result, module, mounted, unmounted = self.execute(Path(directory), model)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(mounted), total)
                self.assertEqual(unmounted, [])
                self.assertFalse((module / 'skip_mount').exists())
                self.assertTrue((module / 'mount-ready').exists())

    def test_unmount_failure_is_logged_and_does_not_skip_remaining_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            result, module, mounted, unmounted = self.execute(Path(directory), fail_at=4, umount_fail=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(unmounted, list(reversed(mounted)))
            self.assertEqual((module / 'bind.log').read_text().count('rollback FAIL'), 3)
            self.assertTrue((module / 'skip_mount').exists())

    def test_service_library_failure_rolls_back_owned_layers_in_reverse_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result, module, mounted, unmounted = self.execute(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            service, unrelated = self.execute_service(root, module, root / 'odm')
            self.assertNotEqual(service.returncode, 0)
            trace = (root / 'trace').read_text().splitlines()
            service_unmounts = [line.removeprefix('umount ') for line in trace if line.startswith('umount ')]
            owned_libraries = [str(root / 'odm/lib64' / name) for name in LIBRARIES[:-1]]
            self.assertEqual(service_unmounts, list(reversed(owned_libraries)) + list(reversed(mounted)))
            self.assertNotIn(str(root / 'odm/lib64' / LIBRARIES[-1]), service_unmounts)
            self.assertNotIn(str(unrelated), service_unmounts)
            self.assertTrue((module / 'skip_mount').is_file())
            self.assertFalse((module / 'mount-ready').exists())
            self.assertTrue((module / 'mounted-targets').is_file())
            service_log = (module / 'service.log').read_text()
            self.assertIn('拒绝卸载上层', service_log)
            self.assertIn('回滚不完整', service_log)


if __name__ == '__main__':
    unittest.main()
