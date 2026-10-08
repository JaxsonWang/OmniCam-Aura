"""验证移植边界：原厂镜头、模式和未知 protobuf 字段必须保留。"""

from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from prepare_plk110 import (
    FEATURE_KEYS, PROJECT, encode_fields, fields, patch_algorithms, patch_config, patch_decision, patch_features, patch_unit,
)


class ProfileTests(unittest.TestCase):
    def test_config_preserves_duplicate_vendor_tag_order(self):
        def entry(key, value):
            return {"VendorTag": key, "Type": "String", "Count": "1", "Value": value}
        duplicates = [entry("stock.duplicate", "0"), entry("stock.duplicate", "1")]
        stock = duplicates + [entry(key, value) for key, value in (
            ("com.oplus.pro.zoom.marked.zoomvalues", "0.6(16),1(24),3.5(85),7(170)"),
            ("com.oplus.camera.preview.hdr.cap.mode.value", "professional"),
            ("com.oplus.camera.capture.hdr.cap.mode.value", "professional"),
            ("com.oplus.flash.decision.by.aps.modelist", "common"),
            ("com.oplus.camera.wide.frame.ratio.support.modelist", "common"),
        )]
        result = patch_config(stock, [entry(key, "1") for key in FEATURE_KEYS])
        self.assertEqual(result[:2], duplicates)
        self.assertEqual(result[2], stock[2])
        by_key = {item["VendorTag"]: item["Value"] for item in result}
        self.assertEqual(by_key["com.oplus.camera.preview.hdr.cap.mode.value"], "professional")
        self.assertIn("gr", by_key["com.oplus.camera.capture.hdr.cap.mode.value"].split(","))
        torch_key = "com.oplus.feature.colorful.screen.torch.config"
        self.assertEqual(int(by_key[torch_key], 2) & 4, 4)
        # 已有补光位必须保留，POP 仅补上遮罩 shader 所需的位。
        stock.append(entry(torch_key, "11"))
        result = patch_config(stock, [entry(key, "1") for key in FEATURE_KEYS])
        by_key = {item["VendorTag"]: item["Value"] for item in result}
        self.assertEqual(by_key[torch_key], "111")

    def test_unit_preserves_sensor_and_stream_definitions(self):
        stock = {
            "camera_id_list": ["0", "1", "2", "3", "4"],
            "device_info": {"sensor": "infinitimain"},
            "mode_type_list": {"rear_main": ["photo_mode", "professional_mode"], "front_main": ["photo_mode"]},
            "mode_operation_mode": {"photo_mode": "8001", "professional_mode": "8009"},
            "capture_stream_number": {"photo_mode": {"front_main": {"2dol": "2"}}, "professional_mode": {"rear_main": {"2dol": "2"}}},
            "usecase_info": {"professional_case": [{"raw_output": "rear_tele"}],
                             "professional_hqraw_case": [{"preview": "rear_sat"}],
                             "sat_photo_full_size_case": [{"raw_output": "rear_main"}]},
        }
        before = deepcopy(stock)
        patched = patch_unit(stock)
        self.assertEqual(stock, before)
        self.assertEqual(patched["camera_id_list"], stock["camera_id_list"])
        self.assertEqual(patched["device_info"], stock["device_info"])
        for name, streams in stock["usecase_info"].items():
            self.assertEqual(patched["usecase_info"][name], streams)
        self.assertEqual(patched["usecase_info"]["gr_mode_case"], stock["usecase_info"]["professional_case"])
        self.assertNotIn("gr_mode", patched["mode_type_list"]["front_main"])

    def test_rejects_other_sensor_layout(self):
        with self.assertRaises(ValueError):
            patch_unit({"camera_id_list": ["0", "1", "2", "3", "4", "5"]})

    def test_protobuf_preserves_pool_original_modes_and_unknown_fields(self):
        leaf = encode_fields([(1, 0, 1), (2, 0, 1)])
        group = encode_fields([(1, 0, 0), (2, 2, encode_fields([(1, 2, leaf)]))])
        mode = lambda name: (1, 2, encode_fields([(1, 2, name.encode()), (2, 2, encode_fields([(1, 2, group)]))]))
        original_modes = [mode("professional_mode"), mode("photo_mode"), mode("tilt_shift_mode")]
        original = [(1, 2, b"common"), (1, 2, b"stock.feature"), (2, 2, encode_fields(original_modes)),
                    (3, 2, b"\x08\x00"), (4, 2, b"831"), (9, 5, b"abcd")]
        result = fields(patch_features(encode_fields(original)))
        self.assertEqual(result[:2], original[:2])
        self.assertEqual(result[-3:], original[-3:])
        patched_modes = fields(next(v for n, w, v in result if (n, w) == (2, 2)))
        self.assertEqual(patched_modes[:3], original_modes)
        for entry, name, source in zip(patched_modes[3:], ("gr_mode", "retro_camera_mode"), original_modes):
            decoded = fields(entry[2])
            self.assertEqual(decoded[0], (1, 2, name.encode()))
            groups = fields(decoded[1][2])
            leaves = fields(fields(groups[0][2])[1][2])
            self.assertEqual(leaves[0][2], leaf)
            self.assertGreater(len(leaves), 1)

    def test_rejects_truncated_protobuf(self):
        for data in (b"\x0a\x05ab", b"\x80", b"\x00"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                fields(data)

    def test_capture_preserves_unsupported_front_high_pixel(self):
        stock = {
            "aps_capture_configs": [
                {"mode": "common", "entity": [{"id": 0, "aps_algo_turbo_hdr": 1}, {"id": 1, "aps_algo_turbo_hdr": 0}]},
                {"mode": "master", "entity": [{"id": 0, "aps_algo_super_raw": 1}]},
                {"mode": "aiHighPixel", "entity": [{"id": 0, "aps_algo_face_beauty": 1}]},
            ],
            "aps_preview_configs": [{"mode": "common", "entity": [{"id": 0}]}, {"mode": "master", "entity": [{"id": 0}]}],
        }
        result = patch_algorithms(stock)
        high = next(g for g in result["aps_capture_configs"] if g["mode"] == "aiHighPixel")
        self.assertEqual([e["id"] for e in high["entity"]], [0])
        self.assertEqual(high["entity"][0]["aps_algo_face_beauty"], 1)
        gr = next(g for g in result["aps_capture_configs"] if g["mode"] == "grmode")
        self.assertEqual(gr["entity"], stock["aps_capture_configs"][1]["entity"])

    def test_preview_keeps_original_branches(self):
        stock = {"multiAlgo": {"algo": [{"mode": "ORIGINAL_SENSOR_ALGO"}]}, "singleAlgo": {"algo": [
            {"mode": "SINGLE_ALGO_BASIC_TONE", "condition": {"or": {"eq": ["captureMode", "APS_CAPMODE_MASTER"]}},
             "nextMode": "SINGLE_ALGO_RECTIFY"},
            {"mode": "SINGLE_ALGO_TILT_SHIFT", "condition": {"eq": ["blur", 1]}},
        ]}}
        result = patch_decision(stock)
        self.assertEqual(result["multiAlgo"], stock["multiAlgo"])
        self.assertEqual(result["singleAlgo"]["algo"][1], stock["singleAlgo"]["algo"][1])
        self.assertEqual(result["singleAlgo"]["algo"][0]["condition"]["or"]["or"],
                         stock["singleAlgo"]["algo"][0]["condition"]["or"])

    def test_installer_requires_matching_device_firmware_camera_and_ksu(self):
        script = '''
getprop() { case "$1" in ro.product.model) echo "$MODEL";; ro.build.display.id) echo "$FIRMWARE";; esac; }
dumpsys() { echo "    versionName=$CAMERA"; }
abort() { echo "$*" >&2; exit 1; }
ui_print() { :; }
set_perm() { :; }
set_perm_recursive() { :; }
MODPATH=$1
. "$MODPATH/customize.sh"
'''
        import os
        base = {**os.environ, "MODEL": "PLK110", "FIRMWARE": "PLK110_17.0.0.102(CN01)",
                "CAMERA": "7.006.100", "KSU": "true", "ARCH": "arm64"}
        cases = [({}, True), ({"MODEL": "PMA110", "CAMERA": "7.006.77"}, True),
                 ({"KSU": "false"}, False), ({"MODEL": "OTHER"}, False),
                 ({"FIRMWARE": "PLK110_new_firmware"}, False), ({"CAMERA": "7.007.1"}, False)]
        for changes, accepted in cases:
            with self.subTest(changes=changes):
                with tempfile.TemporaryDirectory() as directory:
                    module = Path(directory)
                    for name in ("customize.sh", "device.sh"):
                        shutil.copy2(PROJECT / "module" / name, module / name)
                    for model in ("PMA110", "PLK110"):
                        profile = module / "profiles" / model
                        profile.mkdir(parents=True)
                        (profile / "settings.conf").touch()
                    (module / "skip_mount").touch()
                    (module / "mount-ready").touch()
                    result = subprocess.run(["sh", "-c", script, "test", str(module)],
                                            env={**base, **changes}, capture_output=True, text=True)
                    self.assertEqual(result.returncode == 0, accepted, result.stderr)
                    self.assertEqual((module / "skip_mount").exists(), not accepted)
                    self.assertEqual((module / "mount-ready").exists(), not accepted)


if __name__ == "__main__":
    unittest.main()
