"""验证移植边界：原厂镜头、模式和未知 protobuf 字段必须保留。"""

from copy import deepcopy
from pathlib import Path
import json
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
            return {"VendorTag": key, "Type": "String",
                    "Count": str(len(value.split(","))), "Value": value}
        duplicates = [entry("stock.duplicate", "0"), entry("stock.duplicate", "1")]
        preview_key = "com.oplus.camera.preview.hdr.cap.mode.value"
        capture_key = "com.oplus.camera.capture.hdr.cap.mode.value"
        sdr_conversion_key = "com.oplus.camera.sdr.to.hdr.support.rear.mode.list"
        sdr_output_key = "com.oplus.camera.preview.hdr.display.transform.sdr.mode.value"
        stock = duplicates + [entry(key, value) for key, value in (
            ("com.oplus.pro.zoom.marked.zoomvalues", "0.6(16),1(24),3.5(85),7(170)"),
            (preview_key, "common,professional,night,highPixel,underWater"),
            ("com.oplus.camera.preview.hdr.brightness.ratio", "5"),
            (capture_key, "professional"),
            (sdr_conversion_key, "photo_mode,high_pixel_mode,night_mode"),
            ("com.oplus.flash.decision.by.aps.modelist", "common"),
            ("com.oplus.camera.wide.frame.ratio.support.modelist", "common"),
        )]
        original = deepcopy(stock)
        result = patch_config(stock, [entry(key, "1") for key in FEATURE_KEYS])
        self.assertEqual(stock, original)
        self.assertEqual(result[:2], duplicates)
        self.assertEqual(result[2], stock[2])
        by_key = {item["VendorTag"]: item for item in result}
        stock_by_key = {item["VendorTag"]: item for item in stock}
        preview_modes = by_key[preview_key]["Value"].split(",")
        self.assertEqual(preview_modes, stock_by_key[preview_key]["Value"].split(",") + ["gr"])
        self.assertEqual(int(by_key[preview_key]["Count"]), len(preview_modes))
        capture_modes = by_key[capture_key]["Value"].split(",")
        self.assertEqual(capture_modes, ["professional", "gr", "retroCamera"])
        self.assertEqual(int(by_key[capture_key]["Count"]), len(capture_modes))
        self.assertEqual(by_key[sdr_conversion_key], stock_by_key[sdr_conversion_key])
        self.assertEqual(by_key["com.oplus.camera.preview.hdr.brightness.ratio"],
                         stock_by_key["com.oplus.camera.preview.hdr.brightness.ratio"])
        self.assertNotIn(sdr_output_key, by_key)
        torch_key = "com.oplus.feature.colorful.screen.torch.config"
        self.assertNotIn(torch_key, by_key)
        # POP 修复不能启用全局反色补光，也不能改写原有补光功能位。
        stock.append(entry(torch_key, "11"))
        result = patch_config(stock, [entry(key, "1") for key in FEATURE_KEYS])
        by_key = {item["VendorTag"]: item for item in result}
        self.assertEqual(by_key[torch_key]["Value"], "11")

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

    def test_preview_extends_only_master_decisions_to_gr(self):
        def master_condition(gate=None):
            condition = {"eq": ["captureMode", "APS_CAPMODE_MASTER"]}
            return condition if gate is None else {"and": {"eq": [gate, True], "and": condition}}

        stock = {
            "multiAlgo": {
                "prerequisites": [
                    {"mode": "PREREQUISITES_MASTER", "condition": master_condition(),
                     "childMode": "ALGO_MASTER_SUPER_RAW"},
                    {"mode": "PREREQUISITES_NORMAL",
                     "condition": {"eq": ["captureMode", "APS_CAPMODE_REAR_NORMAL"]}},
                ],
                "algo": [{"mode": "ORIGINAL_SENSOR_ALGO"}],
            },
            "singleAlgo": {"algo": [
                {"mode": "SINGLE_ALGO_BASIC_TONE",
                 "condition": {"or": {"eq": ["captureMode", "APS_CAPMODE_MASTER"],
                                        "eq1": ["captureMode", "APS_CAPMODE_XPAN"]}},
                 "nextMode": "SINGLE_ALGO_RECTIFY"},
                {"mode": "SINGLE_ALGO_RECTIFY", "condition": master_condition("rectifyEnabled")},
                {"mode": "SINGLE_ALGO_HDR_TRANSFROM", "condition": master_condition("ultraHdrEnabled")},
                {"mode": "SINGLE_ALGO_TILT_SHIFT",
                 "condition": {"or": {"eq": ["captureMode", "APS_CAPMODE_MASTER"],
                                        "eq1": ["blur", 1]}}},
            ]},
        }
        original = deepcopy(stock)
        result = patch_decision(stock)
        self.assertEqual(stock, original)
        self.assertEqual(result["multiAlgo"]["algo"], stock["multiAlgo"]["algo"])
        self.assertEqual(result["multiAlgo"]["prerequisites"][1],
                         stock["multiAlgo"]["prerequisites"][1])
        self.assertEqual(result["singleAlgo"]["algo"][3], stock["singleAlgo"]["algo"][3])

        def evaluate(value, params):
            if not isinstance(value, dict):
                raise AssertionError(f"不支持的测试条件: {value!r}")
            results = []
            for operator, operands in value.items():
                if operator.startswith("or"):
                    results.append(any(evaluate({key: child}, params) for key, child in operands.items()))
                elif operator.startswith("and"):
                    results.append(all(evaluate({key: child}, params) for key, child in operands.items()))
                elif operator.startswith("eq"):
                    results.append(params.get(operands[0]) == operands[1])
                else:
                    raise AssertionError(f"不支持的测试运算符: {operator}")
            return all(results)

        original_conditions = {
            entry["mode"]: entry["condition"]
            for section in (stock["multiAlgo"]["prerequisites"], stock["singleAlgo"]["algo"])
            for entry in section if "condition" in entry
        }
        patched_conditions = {
            entry["mode"]: entry["condition"]
            for section in (result["multiAlgo"]["prerequisites"], result["singleAlgo"]["algo"])
            for entry in section if "condition" in entry
        }
        non_gr_cases = (
            {"captureMode": "APS_CAPMODE_MASTER", "rectifyEnabled": True, "ultraHdrEnabled": True},
            {"captureMode": "APS_CAPMODE_XPAN"},
            {"captureMode": "APS_CAPMODE_REAR_NORMAL"},
            {"captureMode": "APS_CAPMODE_REAR_NORMAL", "blur": 1},
        )
        for mode, condition in original_conditions.items():
            for params in non_gr_cases:
                with self.subTest(mode=mode, params=params):
                    self.assertEqual(evaluate(patched_conditions[mode], params), evaluate(condition, params))

        retro = {"captureMode": "APS_CAPMODE_REAR_NORMAL", "paramsHolder->retro_camera_mode": True}
        self.assertFalse(evaluate(original_conditions["SINGLE_ALGO_BASIC_TONE"], retro))
        self.assertTrue(evaluate(patched_conditions["SINGLE_ALGO_BASIC_TONE"], retro))
        gr = {"captureMode": "APS_CAPMODE_GRMODE"}
        self.assertTrue(evaluate(patched_conditions["PREREQUISITES_MASTER"], gr))
        self.assertTrue(evaluate(patched_conditions["SINGLE_ALGO_BASIC_TONE"], gr))
        self.assertTrue(evaluate(patched_conditions["SINGLE_ALGO_RECTIFY"], {**gr, "rectifyEnabled": True}))
        self.assertFalse(evaluate(patched_conditions["SINGLE_ALGO_RECTIFY"], {**gr, "rectifyEnabled": False}))
        self.assertTrue(evaluate(patched_conditions["SINGLE_ALGO_HDR_TRANSFROM"], {**gr, "ultraHdrEnabled": True}))
        self.assertFalse(evaluate(patched_conditions["SINGLE_ALGO_HDR_TRANSFROM"], {**gr, "ultraHdrEnabled": False}))
        self.assertEqual(patch_decision(original), result)

    def test_generated_preview_profile_matches_stock_patch(self):
        stock_path = PROJECT / "build/device-plk110/stock/oplus_camera_preview_decision_config.json"
        if not stock_path.exists():
            self.skipTest("本地没有 PLK110 原厂配置，仅执行内嵌决策 fixture")
        stock = json.loads(stock_path.read_bytes())
        profile = json.loads((PROJECT / "module/profiles/PLK110/config/"
                              "oplus_camera_preview_decision_config.json").read_bytes())
        self.assertEqual(profile, patch_decision(stock))

    def test_installer_accepts_patch_family_and_rejects_unsupported_contracts(self):
        script = '''
getprop() {
    case "$1" in
        ro.product.model) printf '%s\\n' "$MODEL" ;;
        ro.build.display.id) printf '%s\\n' "$FIRMWARE" ;;
        ro.build.version.sdk) printf '%s\\n' "$SDK" ;;
    esac
}
dumpsys() { printf '    versionName=%s\\n' "$CAMERA"; }
abort() { echo "$*" >&2; exit 1; }
ui_print() { :; }
set_perm() { :; }
set_perm_recursive() { :; }
MODPATH=$1
. "$MODPATH/customize.sh"
'''
        import os
        base = {**os.environ, "MODEL": "PLK110", "FIRMWARE": "PLK110_17.0.0.105(CN01)",
                "SDK": "37", "CAMERA": "7.006.125", "KSU": "true", "ARCH": "arm64"}
        cases = [
            ({}, None),
            ({"FIRMWARE": "PLK110_17.0.0.102(CN01)", "CAMERA": "7.006.100"}, None),
            ({"FIRMWARE": "PLK110_17.0.0.9999(CN01)", "CAMERA": "7.006.9999"}, None),
            ({"CAMERA": "7.006.0"}, None),
            ({"CAMERA": "7.006.00125"}, None),
            ({"MODEL": "PMA110", "CAMERA": "7.006.77", "SDK": "36"}, None),
            ({"MODEL": "PMA110", "CAMERA": "7.006.125"}, "相机版本不匹配"),
            ({"MODEL": "PMA110", "CAMERA": "7.006.077"}, "相机版本不匹配"),
            ({"KSU": "false"}, "KernelSU"),
            ({"ARCH": "x64"}, "arm64"),
            ({"MODEL": "OTHER"}, "不支持的机型"),
            ({"SDK": "36"}, "Android API 不兼容"),
            ({"SDK": "38"}, "Android API 不兼容"),
            ({"SDK": ""}, "Android API 不兼容"),
            ({"FIRMWARE": "PLK110_17.0.1.105(CN01)"}, "系统分支不兼容"),
            ({"FIRMWARE": "PLK110_17.0.0.105(EX01)"}, "系统分支不兼容"),
            ({"FIRMWARE": "PLK110_17.0.0.(CN01)"}, "系统分支不兼容"),
            ({"FIRMWARE": "PLK110_17.0.0.１０５(CN01)"}, "系统分支不兼容"),
            ({"CAMERA": "7.007.1"}, "相机版本不匹配"),
            ({"CAMERA": "8.006.125"}, "相机版本不匹配"),
            ({"CAMERA": "7.006."}, "相机版本不匹配"),
            ({"CAMERA": "7.006.-125"}, "相机版本不匹配"),
            ({"CAMERA": "7.006.+125"}, "相机版本不匹配"),
            ({"CAMERA": "7.006.125.1"}, "相机版本不匹配"),
            ({"CAMERA": "7.006.125beta"}, "相机版本不匹配"),
            ({"CAMERA": "7.006.１２５"}, "相机版本不匹配"),
            ({"CAMERA": "7.006.١٢٥"}, "相机版本不匹配"),
            ({"CAMERA": " 7.006.125"}, "相机版本不匹配"),
            ({"CAMERA": "7.006.125 "}, "相机版本不匹配"),
            ({"CAMERA": ""}, "相机版本不匹配"),
        ]
        for changes, error in cases:
            with self.subTest(changes=changes):
                with tempfile.TemporaryDirectory() as directory:
                    module = Path(directory)
                    for name in ("customize.sh", "device.sh", "clear-overrides.sh"):
                        shutil.copy2(PROJECT / "module" / name, module / name)
                    result = subprocess.run(["sh", "-c", script, "test", str(module)],
                                            env={**base, **changes}, capture_output=True, text=True)
                    self.assertEqual(result.returncode == 0, error is None, result.stderr)
                    if error is not None:
                        self.assertIn(error, result.stderr)


if __name__ == "__main__":
    unittest.main()
