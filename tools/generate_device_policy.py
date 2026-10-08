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
        conditions.append(f'({model} && {json.dumps(firmware)}.equals(firmware))' if firmware else model)
    return ('// 由 tools/generate_device_policy.py 生成，不手工修改。\n'
            'package local.omnicam.aura;\n\n'
            'final class DevicePolicy {\n'
            '    private DevicePolicy() {}\n'
            '    static boolean matches(String model, String firmware) {\n'
            '        return ' + '\n            || '.join(conditions) + ';\n'
            '    }\n}\n')


def render_cpp(devices):
    conditions = []
    for device in devices:
        model = f'std::strcmp(model, {json.dumps(device["model"])}) == 0'
        firmware = device['firmware']
        conditions.append(f'({model} && std::strcmp(firmware, {json.dumps(firmware)}) == 0)' if firmware else model)
    return ('// 由 tools/generate_device_policy.py 生成，不手工修改。\n'
            '#pragma once\n#include <cstring>\n\n'
            'namespace aura {\n'
            'inline bool devicePolicyMatches(const char *model, const char *firmware) {\n'
            '    return ' + '\n        || '.join(conditions) + ';\n'
            '}\n}\n')


def render_shell(devices):
    result = ['#!/system/bin/sh', '# 由 config/supported-devices.json 生成；通过 tools/generate_device_policy.py 更新。',
              '# shellcheck disable=SC2034', 'DEVICE=$(getprop ro.product.model)', 'case "$DEVICE" in']
    for device in devices:
        result.extend([f'    {shlex.quote(device["model"])})',
                       f'        CAMERA_VERSION={shlex.quote(device["cameraVersion"])}'])
        if device['firmware']:
            result.extend([f'        if [ "$(getprop ro.build.display.id)" != {shlex.quote(device["firmware"])} ]; then',
                           "            echo 'Aura: 固件不匹配，需要重新提取原厂配置' >&2", '            return 1', '        fi'])
        result.extend([f'        CONFIG_DIR="$MODDIR/"{shlex.quote(device["configDir"])}',
                       f'        BIND_ISP={int(device["bindIsp"])}', f'        BIND_GAMMA={int(device["bindGamma"])}', '        ;;'])
    result.extend(['    *)', '        echo "Aura: 不支持的机型 $DEVICE" >&2', '        return 1', '        ;;', 'esac', ''])
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
