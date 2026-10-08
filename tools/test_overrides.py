"""验证旧覆盖键的精确清理和 ODM 单一配置来源。"""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parent.parent
KEYS = (
    "com.oplus.gr.mode.support", "com.oplus.camera.mode.data.db.version",
    "com.oplus.available.gr.mode.zoomvalues", "com.oplus.gr.mode.marked.zoomvalues",
    "com.oplus.camera.capture.hdr.cap.mode.value", "com.oplus.camera.preview.hdr.cap.mode.value",
    "com.oplus.feature.retro.camera.support", "com.oplus.flashlevel.configurable.support",
    "com.oplus.feature.tilt.shift.photo.support", "com.oplus.feature.colorful.screen.torch.config",
)


class OverrideTests(unittest.TestCase):
    def clean(self, prefs, state, cleaner="clear_camera_overrides", restorecon_ok=True):
        script = '''
am() { [ "$*" = "force-stop $EXPECTED_PACKAGE" ]; }
restorecon() { [ "$RESTORECON_OK" = 1 ]; }
. "$1"
"$4" "$2" "$3"
'''
        package = ("com.oplus.camera" if cleaner == "clear_camera_overrides"
                   else "com.coloros.gallery3d")
        return subprocess.run(["sh", "-c", script, "test", str(PROJECT / "module/clear-overrides.sh"),
                               str(prefs), str(state), cleaner],
                              env={"RESTORECON_OK": str(int(restorecon_ok)),
                                   "EXPECTED_PACKAGE": package},
                              capture_output=True, text=True)

    def test_precise_cleanup_preserves_unrelated_settings_and_original_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefs, state = root / "prefs.xml", root / "persistent"
            kept = '<string name="com.oplus.gr.mode.support.custom">keep &amp; me</string>\n'
            original = '<map>\n' + ''.join(f'    <string name="{key}">1</string>\n' for key in KEYS) + kept + '</map>\n'
            prefs.write_text(original)
            prefs.chmod(0o660)
            result = self.clean(prefs, state)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(prefs.read_text(), '<map>\n' + kept + '</map>\n')
            self.assertEqual(prefs.stat().st_mode & 0o777, 0o660)
            backups = list(state.iterdir())
            self.assertEqual(len(backups), 1)
            self.assertTrue(backups[0].name.startswith('legacy-overrides.'))
            self.assertEqual(backups[0].read_text(), original)
            # 覆盖安装不会把已清理文件当成原始备份，也不会再写入任何键。
            result = self.clean(prefs, state)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(state.iterdir()), backups)
            self.assertEqual(backups[0].read_text(), original)
            self.assertFalse(list(root.glob('prefs.xml.aura.*')))

    def test_actual_upgrade_cleans_gallery_key_without_overwriting_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            camera_prefs = root / "camera.xml"
            gallery_prefs = root / "gallery.xml"
            state = root / "persistent"
            camera_original = (
                '<map>\n'
                '    <string name="com.oplus.gr.mode.support">1</string>\n'
                '    <string name="camera.unrelated">keep</string>\n'
                '</map>\n'
            )
            gallery_kept = '    <boolean name="gallery.unrelated" value="true" />\n'
            gallery_original = (
                '<map>\n'
                '    <boolean name="business_featureSwitch_is_camera_gr_supported" value="true" />\n'
                + gallery_kept +
                '</map>\n'
            )
            camera_prefs.write_text(camera_original)
            gallery_prefs.write_text(gallery_original)

            camera_result = self.clean(camera_prefs, state)
            gallery_result = self.clean(gallery_prefs, state, "clear_gallery_overrides")
            self.assertEqual(camera_result.returncode, 0, camera_result.stderr)
            self.assertEqual(gallery_result.returncode, 0, gallery_result.stderr)
            self.assertEqual(camera_prefs.read_text(),
                             '<map>\n    <string name="camera.unrelated">keep</string>\n</map>\n')
            self.assertEqual(gallery_prefs.read_text(), '<map>\n' + gallery_kept + '</map>\n')

            camera_snapshots = list(state.glob('legacy-overrides.*'))
            gallery_snapshots = list(state.glob('legacy-gallery-overrides.*'))
            self.assertEqual(len(camera_snapshots), 1)
            self.assertEqual(len(gallery_snapshots), 1)
            self.assertEqual(camera_snapshots[0].read_text(), camera_original)
            self.assertEqual(gallery_snapshots[0].read_text(), gallery_original)

            # 再次安装时已无旧键，不得覆盖或新增清理前快照。
            camera_result = self.clean(camera_prefs, state)
            gallery_result = self.clean(gallery_prefs, state, "clear_gallery_overrides")
            self.assertEqual(camera_result.returncode, 0, camera_result.stderr)
            self.assertEqual(gallery_result.returncode, 0, gallery_result.stderr)
            self.assertEqual(list(state.glob('legacy-overrides.*')), camera_snapshots)
            self.assertEqual(list(state.glob('legacy-gallery-overrides.*')), gallery_snapshots)
            self.assertEqual(gallery_snapshots[0].read_text(), gallery_original)

    def test_absent_preferences_are_not_created_or_backed_up(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for cleaner in ("clear_camera_overrides", "clear_gallery_overrides"):
                with self.subTest(cleaner=cleaner):
                    result = self.clean(root / "absent.xml", root / "persistent", cleaner)
                    self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_unknown_format_fails_without_changing_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefs = root / "prefs.xml"
            original = '<map>\n<string name="com.oplus.gr.mode.support">\n1</string>\n</map>\n'
            prefs.write_text(original)
            result = self.clean(prefs, root / "persistent")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('格式异常', result.stderr)
            self.assertEqual(prefs.read_text(), original)
            self.assertFalse((root / "persistent").exists())

    def test_unknown_gallery_format_fails_without_changing_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefs = root / "gallery.xml"
            original = (
                '<map>\n'
                '    <string name="business_featureSwitch_is_camera_gr_supported">true</string>\n'
                '</map>\n'
            )
            prefs.write_text(original)
            result = self.clean(prefs, root / "persistent", "clear_gallery_overrides")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('格式异常', result.stderr)
            self.assertEqual(prefs.read_text(), original)
            self.assertFalse((root / "persistent").exists())

    def test_restorecon_failure_does_not_replace_or_back_up_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefs, state = root / "prefs.xml", root / "persistent"
            original = '<map>\n<string name="com.oplus.gr.mode.support">1</string>\n</map>\n'
            prefs.write_text(original)
            result = self.clean(prefs, state, restorecon_ok=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(prefs.read_text(), original)
            self.assertFalse(state.exists())
            self.assertFalse(list(root.glob('prefs.xml.aura.*')))

    def test_pma110_effective_configuration_is_preserved(self):
        entries = json.loads((PROJECT / 'module/payload/oplus_camera_config').read_bytes())
        values = {e['VendorTag']: e['Value'] for e in entries}
        expected = (
            '1', '102', '0.6(14),1(23),2(47),3(70),6(139),10(230)',
            '1.2173913(28),1.7391304(40)',
            'common,portrait,professional,night,highPixel,xpan,underWater,telephoto,gr,retroCamera',
            'common,professional,night,highPixel,xpan,underWater,telephoto,gr', '1', '1', '1',
        )
        self.assertEqual([values[key] for key in KEYS[:-1]], list(expected))
        capture_hdr = next(e for e in entries
                           if e['VendorTag'] == 'com.oplus.camera.capture.hdr.cap.mode.value')
        self.assertEqual(int(capture_hdr['Count']), len(capture_hdr['Value'].split(',')))


if __name__ == '__main__':
    unittest.main()
