"""从唯一设备清单生成 Java、C++ 及模块机型选择器。"""

import argparse
import json
from pathlib import Path
import shlex

PROJECT = Path(__file__).resolve().parent.parent
POLICY = PROJECT / 'config/supported-devices.json'


def render_java(devices):
    conditions = []
    for device in devices:
        model = f'{json.dumps(device["model"])}.equals(model)'
        firmware = device['firmware']
        terms = [model]
        if firmware:
            terms.append(f'patchMatches(firmware, {json.dumps(firmware["prefix"])}, {json.dumps(firmware["suffix"])})')
        if device['androidSdk'] is not None:
            terms.append(f'sdk == {device["androidSdk"]}')
        conditions.append('(' + ' && '.join(terms) + ')')
    return ('// 由 tools/generate_device_policy.py 生成，不手工修改。\n'
            'package local.omnicam.aura;\n\n'
            'final class DevicePolicy {\n'
            '    private DevicePolicy() {}\n'
            '    static boolean matches(String model, String firmware, int sdk) {\n'
            '        return ' + '\n            || '.join(conditions) + ';\n'
            '    }\n'
            '    private static boolean patchMatches(String value, String prefix, String suffix) {\n'
            '        if (value == null || !value.startsWith(prefix) || !value.endsWith(suffix)) return false;\n'
            '        int end = value.length() - suffix.length();\n'
            '        if (end <= prefix.length()) return false;\n'
            '        for (int i = prefix.length(); i < end; i++) {\n'
            "            char c = value.charAt(i);\n"
            "            if (c < '0' || c > '9') return false;\n"
            '        }\n'
            '        return true;\n'
            '    }\n}\n')


def render_cpp(devices):
    conditions = []
    for device in devices:
        model = f'std::strcmp(model, {json.dumps(device["model"])}) == 0'
        firmware = device['firmware']
        terms = [model]
        if firmware:
            terms.append(f'patchVersionMatches(firmware, {json.dumps(firmware["prefix"])}, {json.dumps(firmware["suffix"])})')
        if device['androidSdk'] is not None:
            terms.append(f'sdk == {device["androidSdk"]}')
        conditions.append('(' + ' && '.join(terms) + ')')
    return ('// 由 tools/generate_device_policy.py 生成，不手工修改。\n'
            '#pragma once\n#include <cstring>\n\n'
            'namespace aura {\n'
            'inline bool patchVersionMatches(const char *value, const char *prefix, const char *suffix) {\n'
            '    if (!value) return false;\n'
            '    const size_t size = std::strlen(value), start = std::strlen(prefix), tail = std::strlen(suffix);\n'
            '    if (size <= start + tail || std::strncmp(value, prefix, start) != 0\n'
            '        || std::strcmp(value + size - tail, suffix) != 0) return false;\n'
            '    for (size_t i = start; i < size - tail; ++i) {\n'
            "        if (value[i] < '0' || value[i] > '9') return false;\n"
            '    }\n'
            '    return true;\n'
            '}\n'
            'inline bool devicePolicyMatches(const char *model, const char *firmware, int sdk) {\n'
            '    return ' + '\n        || '.join(conditions) + ';\n'
            '}\n}\n')


def render_shell(devices):
    result = ['#!/system/bin/sh', '# 由 config/supported-devices.json 生成；通过 tools/generate_device_policy.py 更新。',
              '# shellcheck disable=SC2034',
              '# 仅允许同分支的数字补丁号，不把未知主版本当作已兼容。',
              'aura_match_patch_version() {',
              '    case "$1" in "$2"*"$3") ;; *) return 1 ;; esac',
              '    AURA_PATCH=${1#"$2"}', '    AURA_PATCH=${AURA_PATCH%"$3"}',
              '    case "$AURA_PATCH" in \'\'|*[!0-9]*) return 1 ;; esac',
              '}', '',
              'camera_version_matches() {', '    case "$DEVICE" in']
    for device in devices:
        rule = device['cameraVersion']
        if 'exact' in rule:
            check = f'[ "$1" = {shlex.quote(rule["exact"])} ]'
        else:
            check = f'aura_match_patch_version "$1" {shlex.quote(rule["prefix"])} {shlex.quote(rule["suffix"])}'
        result.append(f'        {shlex.quote(device["model"])}) {check} ;;')
    result.extend(['        *) return 1 ;;', '    esac', '}', '',
                   'DEVICE=$(getprop ro.product.model)', 'FIRMWARE=$(getprop ro.build.display.id)',
                   'ANDROID_SDK=$(getprop ro.build.version.sdk)', 'DEVICE_POLICY_ERROR=', 'case "$DEVICE" in'])
    for device in devices:
        rule = device['cameraVersion']
        label = rule['exact'] if 'exact' in rule else rule['prefix'] + '*' + rule['suffix']
        result.extend([f'    {shlex.quote(device["model"])})',
                       f'        CAMERA_VERSION={shlex.quote(label)}'])
        if device['firmware']:
            firmware = device['firmware']
            check = f'aura_match_patch_version "$FIRMWARE" {shlex.quote(firmware["prefix"])} {shlex.quote(firmware["suffix"])}'
            result.extend([f'        if ! {check}; then',
                           '            DEVICE_POLICY_ERROR="系统分支不兼容: $FIRMWARE"',
                           '            echo "Aura: $DEVICE_POLICY_ERROR" >&2', '            return 1', '        fi'])
        if device['androidSdk'] is not None:
            result.extend([f'        if [ "$ANDROID_SDK" != {shlex.quote(str(device["androidSdk"]))} ]; then',
                           '            DEVICE_POLICY_ERROR="Android API 不兼容: $ANDROID_SDK"',
                           '            echo "Aura: $DEVICE_POLICY_ERROR" >&2', '            return 1', '        fi'])
        result.extend([f'        CONFIG_DIR="$MODDIR/"{shlex.quote(device["configDir"])}',
                       f'        BIND_ISP={int(device["bindIsp"])}', f'        BIND_GAMMA={int(device["bindGamma"])}', '        ;;'])
    result.extend(['    *)', '        DEVICE_POLICY_ERROR="不支持的机型: $DEVICE"',
                   '        echo "Aura: $DEVICE_POLICY_ERROR" >&2', '        return 1', '        ;;', 'esac', ''])
    return '\n'.join(result)


def generate(output, shell=None):
    devices = json.loads(POLICY.read_text())
    java = output / 'java/local/omnicam/aura/DevicePolicy.java'
    cpp = output / 'cpp/device_policy.h'
    for path, content in ((java, render_java(devices)), (cpp, render_cpp(devices))):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    if shell:
        shell.write_text(render_shell(devices), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--shell', type=Path, help='显式更新提交到模块中的 device.sh')
    args = parser.parse_args()
    generate(args.output, args.shell)
