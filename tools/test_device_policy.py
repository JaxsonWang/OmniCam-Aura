"""编译并执行同源生成的 Java / C++ 白名单，避免只验证文本相似。"""

from pathlib import Path
import subprocess
import tempfile
import unittest

from generate_device_policy import generate


class DevicePolicyTests(unittest.TestCase):
    def test_java_and_native_accept_the_same_supported_combinations(self):
        cases = [('PMA110', 'original-firmware', True), ('PMA110', 'another-firmware', True),
                 ('PLK110', 'PLK110_17.0.0.102(CN01)', True), ('PLK110', 'updated-firmware', False),
                 ('OTHER', 'PLK110_17.0.0.102(CN01)', False), ('', '', False)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generate(root)
            java = root / 'java/local/omnicam/aura'
            (java / 'PolicyProbe.java').write_text('''
package local.omnicam.aura;
public class PolicyProbe {
    public static void main(String[] args) {
        System.out.print(DevicePolicy.matches(args[0], args[1]));
    }
}
''')
            (root / 'probe.cpp').write_text('''
#include "device_policy.h"
#include <iostream>
int main(int argc, char **argv) {
    if (argc != 3) return 2;
    std::cout << (aura::devicePolicyMatches(argv[1], argv[2]) ? "true" : "false");
}
''')
            subprocess.run(['javac', '-d', str(root / 'classes'), str(java / 'DevicePolicy.java'),
                            str(java / 'PolicyProbe.java')], check=True, capture_output=True)
            subprocess.run(['c++', '-std=c++17', '-I', str(root / 'cpp'), str(root / 'probe.cpp'),
                            '-o', str(root / 'probe')], check=True, capture_output=True)
            for model, firmware, expected in cases:
                with self.subTest(model=model, firmware=firmware):
                    for command in ([str(root / 'probe')], ['java', '-cp', str(root / 'classes'), 'local.omnicam.aura.PolicyProbe']):
                        actual = subprocess.check_output([*command, model, firmware], text=True)
                        self.assertEqual(actual, str(expected).lower())


if __name__ == '__main__':
    unittest.main()
