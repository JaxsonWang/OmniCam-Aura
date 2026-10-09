"""执行同源生成的 Java、C++ 和 Shell 策略，验证补丁族边界一致。"""

from pathlib import Path
import subprocess
import tempfile
import unittest

from generate_device_policy import generate


class DevicePolicyTests(unittest.TestCase):
    def test_java_native_and_shell_agree_on_device_firmware_and_sdk_boundaries(self):
        cases = [
            ('PMA110', 'original-firmware', 36, True),
            ('PMA110', 'another-firmware', 37, True),
            ('PMA110', '', 38, True),
            ('PLK110', 'PLK110_17.0.0.102(CN01)', 37, True),
            ('PLK110', 'PLK110_17.0.0.105(CN01)', 37, True),
            ('PLK110', 'PLK110_17.0.0.9999(CN01)', 37, True),
            ('PLK110', 'PLK110_17.0.0.0(CN01)', 37, True),
            ('PLK110', 'PLK110_17.0.0.00105(CN01)', 37, True),
            ('PLK110', 'PLK110_17.0.0.105(CN01)', 36, False),
            ('PLK110', 'PLK110_17.0.0.105(CN01)', 38, False),
            ('PLK110', 'PLK110_17.0.0.105(CN01)', 0, False),
            ('PLK110', 'PLK110_17.0.1.105(CN01)', 37, False),
            ('PLK110', 'PLK110_18.0.0.105(CN01)', 37, False),
            ('PLK110', 'PLK110_17.0.0.105(EX01)', 37, False),
            ('PLK110', 'PLK110_17.0.0.105', 37, False),
            ('PLK110', 'PLK110_17.0.0.(CN01)', 37, False),
            ('PLK110', 'PLK110_17.0.0.-105(CN01)', 37, False),
            ('PLK110', 'PLK110_17.0.0.+105(CN01)', 37, False),
            ('PLK110', 'PLK110_17.0.0.105.1(CN01)', 37, False),
            ('PLK110', 'PLK110_17.0.0.105beta(CN01)', 37, False),
            ('PLK110', 'PLK110_17.0.0.１０５(CN01)', 37, False),
            ('PLK110', 'PLK110_17.0.0.١٠٥(CN01)', 37, False),
            ('PLK110', 'PLK110_17.0.0. 105(CN01)', 37, False),
            ('PLK110', 'PLK110_17.0.0.105\n(CN01)', 37, False),
            ('PLK110', 'PLK110_17.0.0.105(CN01)extra', 37, False),
            ('PLK110', 'prefixPLK110_17.0.0.105(CN01)', 37, False),
            ('PLK110', 'updated-firmware', 37, False),
            ('PLK110', '', 37, False),
            ('OTHER', 'PLK110_17.0.0.105(CN01)', 37, False),
            ('plk110', 'PLK110_17.0.0.105(CN01)', 37, False),
            ('', '', 37, False),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shell = root / 'device.sh'
            generate(root, shell)
            java = root / 'java/local/omnicam/aura'
            (java / 'PolicyProbe.java').write_text('''
package local.omnicam.aura;
public class PolicyProbe {
    public static void main(String[] args) {
        System.out.print(DevicePolicy.matches(args[0], args[1], Integer.parseInt(args[2])));
    }
}
''')
            (root / 'probe.cpp').write_text('''
#include "device_policy.h"
#include <cstdlib>
#include <iostream>
int main(int argc, char **argv) {
    if (argc != 4) return 2;
    std::cout << (aura::devicePolicyMatches(argv[1], argv[2], std::atoi(argv[3])) ? "true" : "false");
}
''')
            shell_probe = '''
MODEL=$2
FIRMWARE_VALUE=$3
SDK_VALUE=$4
MODDIR=/test-module
getprop() {
    case "$1" in
        ro.product.model) printf '%s\\n' "$MODEL" ;;
        ro.build.display.id) printf '%s\\n' "$FIRMWARE_VALUE" ;;
        ro.build.version.sdk) printf '%s\\n' "$SDK_VALUE" ;;
    esac
}
if . "$1"; then printf true; else printf false; fi
'''
            subprocess.run(['javac', '-d', str(root / 'classes'), str(java / 'DevicePolicy.java'),
                            str(java / 'PolicyProbe.java')], check=True, capture_output=True)
            subprocess.run(['c++', '-std=c++17', '-I', str(root / 'cpp'), str(root / 'probe.cpp'),
                            '-o', str(root / 'probe')], check=True, capture_output=True)
            commands = {
                'native': [str(root / 'probe')],
                'java': ['java', '-cp', str(root / 'classes'), 'local.omnicam.aura.PolicyProbe'],
                'shell': ['sh', '-c', shell_probe, 'probe', str(shell)],
            }
            for model, firmware, sdk, expected in cases:
                for implementation, command in commands.items():
                    with self.subTest(implementation=implementation, model=model, firmware=firmware, sdk=sdk):
                        result = subprocess.run([*command, model, firmware, str(sdk)],
                                                capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout, str(expected).lower(), result.stderr)


if __name__ == '__main__':
    unittest.main()
