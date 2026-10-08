"""基于 PLK110 原厂配置生成 Aura 配置，保留镜头、分辨率和算法调校。"""

import argparse
from copy import deepcopy
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
MODE_ALIASES = {"gr_mode": "professional_mode", "retro_camera_mode": "photo_mode"}
FEATURE_KEYS = (
    "com.oplus.gr.mode.support",
    "com.oplus.camera.livephoto.grmode.support",
    "com.oplus.camera.gr.raw.capture_defer.not.support",
    "com.oplus.feature.retro.camera.support",
    "com.oplus.feature.retro.camera.livephoto.output.size",
    "com.oplus.camera.retro.fisheye.enable",
    "com.oplus.feature.color.palette.support",
    "com.oplus.ipu.color.palette.texture.support",
    "com.ocs.camera.ipu.meishe.filter.support",
)


def varint(data, position):
    value = shift = 0
    while position < len(data) and shift < 64:
        byte = data[position]
        position += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, position
        shift += 7
    raise ValueError("无效的 protobuf varint")


def fields(data):
    result = []
    position = 0
    while position < len(data):
        tag, position = varint(data, position)
        number, wire = tag >> 3, tag & 7
        if number == 0:
            raise ValueError("无效的 protobuf 字段编号")
        if wire == 0:
            value, position = varint(data, position)
        elif wire in (1, 2, 5):
            if wire == 2:
                size, position = varint(data, position)
            else:
                size = 8 if wire == 1 else 4
            end = position + size
            if end > len(data):
                raise ValueError("protobuf 字段被截断")
            value, position = data[position:end], end
        else:
            raise ValueError(f"不支持的 protobuf wire type: {wire}")
        result.append((number, wire, value))
    return result


def encode_varint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def encode_fields(entries):
    result = bytearray()
    for number, wire, value in entries:
        result += encode_varint((number << 3) | wire)
        if wire == 0:
            result += encode_varint(value)
        else:
            if wire == 2:
                result += encode_varint(len(value))
            result += value
    return bytes(result)


def patch_features(data):
    root = fields(data)
    pool = [value.decode() for number, wire, value in root if (number, wire) == (1, 2)]
    original_pool_size = len(pool)

    def pool_index(value):
        if value not in pool:
            pool.append(value)
        return pool.index(value)

    def patch_mode(name, entry):
        result = []
        for number, wire, value in entry:
            if (number, wire) == (1, 2):
                value = name.encode()
            elif (number, wire) == (2, 2):
                groups = []
                for gn, gw, raw_group in fields(value):
                    group = fields(raw_group)
                    camera = pool[next(v for n, w, v in group if (n, w) == (1, 0))]
                    changed = []
                    for fn, fw, features in group:
                        if (fn, fw) == (2, 2):
                            leaves = []
                            for leaf in fields(features):
                                key = pool[next(v for n, w, v in fields(leaf[2]) if (n, w) == (1, 0))]
                                if name == "gr_mode" and key == "com.oplus.camera.feature.live_photo":
                                    continue
                                if name == "retro_camera_mode" and key == "com.oplus.camera.feature.ai_composition":
                                    continue
                                leaves.append(leaf)
                            if camera == "common":
                                menu = "main_menu,other_app,video_other_app,quick_launch,watch,gimbal"
                                additions = [
                                    ("com.oplus.camera.feature.hdr_all_route", "com.oplus.camera.feature.hdr_all_route", "", "", "main_menu", "string"),
                                    ("com.oplus.camera.feature.gr_photo", "com.oplus.camera.feature.gr_photo", "", "", menu, "string"),
                                    ("com.oplus.camera.feature.filter", "feature_filter_index", "[0~100]", "0", menu, "int"),
                                ] if name == "gr_mode" else [
                                    ("com.oplus.camera.feature.retro_camera", "com.oplus.camera.feature.retro_camera", "", "", "", "string"),
                                ]
                                for definition in additions:
                                    key = definition[0]
                                    leaves = [leaf for leaf in leaves if pool[fields(leaf[2])[0][2]] != key]
                                    encoded = encode_fields([(i, 0, pool_index(text)) for i, text in enumerate(definition, 1)])
                                    leaves.append((1, 2, encoded))
                            features = encode_fields(leaves)
                        changed.append((fn, fw, features))
                    groups.append((gn, gw, encode_fields(changed)))
                value = encode_fields(groups)
            result.append((number, wire, value))
        return result
    containers = [i for i, (number, wire, _) in enumerate(root) if (number, wire) == (2, 2)]
    if len(containers) != 1:
        raise ValueError("相机功能表必须只有一个模式容器")
    index = containers[0]
    modes = fields(root[index][2])
    by_name = {}
    for number, wire, value in modes:
        if (number, wire) == (1, 2):
            entry = fields(value)
            name = next(v.decode() for n, w, v in entry if (n, w) == (1, 2))
            if name in by_name:
                raise ValueError(f"重复模式: {name}")
            by_name[name] = entry
    for name, source in MODE_ALIASES.items():
        if name in by_name:
            raise ValueError(f"输入已包含移植模式: {name}")
        entry = patch_mode(name, by_name[source])
        modes.append((1, 2, encode_fields(entry)))
    root[index] = (2, 2, encode_fields(modes))
    # 新字符串只追加到池尾，原厂字符串索引、原始模式和未知字段保持原样。
    root[index:index] = [(1, 2, value.encode()) for value in pool[original_pool_size:]]
    return encode_fields(root)


def patch_unit(stock):
    result = deepcopy(stock)
    if result["camera_id_list"] != ["0", "1", "2", "3", "4"]:
        raise ValueError("输入不是已适配的 PLK110 五个相机 ID 配置")
    aliases = {**MODE_ALIASES, "tilt_shift_mode": "photo_mode"}
    for modes in result["mode_type_list"].values():
        for name, source in aliases.items():
            if source in modes and name not in modes:
                modes.append(name)
    for section in ("mode_operation_mode", "capture_stream_number"):
        for name, source in aliases.items():
            if name not in result[section]:
                result[section][name] = deepcopy(result[section][source])
    cases = result["usecase_info"]
    for name, source in {
        "gr_mode_case": "professional_case",
        "gr_mode_hq_raw_case": "professional_hqraw_case",
        "retro_camera_case": "sat_photo_full_size_case",
    }.items():
        cases[name] = deepcopy(cases[source])
    return result


def patch_config(stock, aura):
    entries = deepcopy(stock)
    result = {e["VendorTag"]: e for e in entries}
    source = {e["VendorTag"]: e for e in aura}

    def set_entry(entry):
        key = entry["VendorTag"]
        positions = [i for i, old in enumerate(entries) if old["VendorTag"] == key]
        if positions:
            for index in positions:
                entries[index] = deepcopy(entry)
        else:
            entries.append(deepcopy(entry))
        result[key] = entry

    for key in FEATURE_KEYS:
        set_entry(source[key])

    def set_value(key, value, kind="String"):
        set_entry({"VendorTag": key, "Type": kind,
                   "Count": str(len(value.split(","))), "Value": value})

    set_value("com.oplus.available.gr.mode.zoomvalues",
              result["com.oplus.pro.zoom.marked.zoomvalues"]["Value"])
    set_value("com.oplus.gr.mode.marked.zoomvalues", "1.1666667(28),1.6666667(40)")
    set_value("com.oplus.flashlevel.configurable.support", "1", "Byte")
    set_value("com.oplus.camera.mode.data.db.version", "103", "Byte")
    for key, additions in {
        "com.oplus.camera.preview.hdr.cap.mode.value": ("gr",),
        "com.oplus.camera.capture.hdr.cap.mode.value": ("gr", "retroCamera"),
        "com.oplus.flash.decision.by.aps.modelist": ("retroCamera", "retro_camera_mode"),
        "com.oplus.camera.wide.frame.ratio.support.modelist": ("retroCamera",),
    }.items():
        values = result[key]["Value"].split(",")
        values.extend(v for v in additions if v not in values)
        set_value(key, ",".join(values))
    # 原厂存在同名但不同值的条目，解析顺序属于厂商契约，不能转成字典后去重。
    return entries


def patch_algorithms(stock):
    result = deepcopy(stock)
    for group in result["aps_capture_configs"]:
        if group["mode"] in ("common", "portrait", "aiHighPixel"):
            for entity in group["entity"]:
                entity["aps_algo_color_palette"] = 1
    for section in ("aps_capture_configs", "aps_preview_configs"):
        groups = result[section]
        for name, source in (("grmode", "master"), ("retroCamera", "common")):
            if any(g["mode"] == name for g in groups):
                raise ValueError(f"输入已包含移植模式: {name}")
            group = deepcopy(next(g for g in groups if g["mode"] == source))
            group["mode"] = name
            if name == "retroCamera" and section == "aps_capture_configs":
                for entity in group["entity"]:
                    entity["aps_algo_basic_tone"] = 1
                    for key in ("aps_algo_super_text", "aps_algo_text_enhance", "aps_algo_aimoon"):
                        if key in entity:
                            entity[key] = 0
            groups.append(group)
    return result


def patch_decision(stock):
    result = deepcopy(stock)

    def extend_gr_mode(condition, mode):
        matches = 0

        def visit(value):
            nonlocal matches
            if isinstance(value, dict):
                for key, child in list(value.items()):
                    if child == ["captureMode", "APS_CAPMODE_MASTER"]:
                        if key != "eq" or "or" in value:
                            raise ValueError(f"{mode} 的 MASTER 条件结构不受支持")
                        del value[key]
                        value["or"] = {
                            "eq": child,
                            "eq1": ["captureMode", "APS_CAPMODE_GRMODE"],
                        }
                        matches += 1
                    else:
                        visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(condition)
        if matches != 1:
            raise ValueError(f"{mode} 必须且只能包含一个 MASTER 条件，实际为 {matches}")

    targets = (
        (result["multiAlgo"]["prerequisites"], "PREREQUISITES_MASTER"),
        (result["singleAlgo"]["algo"], "SINGLE_ALGO_BASIC_TONE"),
        (result["singleAlgo"]["algo"], "SINGLE_ALGO_RECTIFY"),
        (result["singleAlgo"]["algo"], "SINGLE_ALGO_HDR_TRANSFROM"),
    )
    for entries, mode in targets:
        matches = [entry for entry in entries if entry["mode"] == mode]
        if len(matches) != 1:
            raise ValueError(f"决策表必须且只能包含一个 {mode}，实际为 {len(matches)}")
        extend_gr_mode(matches[0]["condition"], mode)

    tone = next(e for e in result["singleAlgo"]["algo"] if e["mode"] == "SINGLE_ALGO_BASIC_TONE")
    tone["condition"] = {"or": {
        "or": tone["condition"]["or"],
        "and": {"eq": ["paramsHolder->retro_camera_mode", True], "or": {
            "eq": ["captureMode", "APS_CAPMODE_REAR_NORMAL"],
            "eq1": ["captureMode", "APS_CAPMODE_FRONT_NORMAL"],
        }},
    }}
    return result


def prepare(stock, output):
    def read(name):
        return json.loads((stock / name).read_bytes())

    output.mkdir(parents=True, exist_ok=True)
    configs = {
        "camera_unit_config": patch_unit(read("config/camera_unit_config")),
        "oplus_camera_config": patch_config(read("oplus_camera_config.json"),
                                           json.loads((PROJECT / "module/payload/oplus_camera_config").read_bytes())),
        "oplus_camera_algo_switch_config": patch_algorithms(read("oplus_camera_algo_switch_config.json")),
        "oplus_camera_preview_decision_config.json": patch_decision(read("oplus_camera_preview_decision_config.json")),
    }
    for name, value in configs.items():
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "camera_unit_feature_config.protobuf").write_bytes(
        patch_features((stock / "config/camera_unit_feature_config.protobuf").read_bytes()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path, help="已从指定固件读取的原厂配置目录")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.stock, args.output)
