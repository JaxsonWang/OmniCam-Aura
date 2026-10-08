from pathlib import Path
from zipfile import ZipFile
import subprocess
import json
import os
from generate_device_policy import POLICY, render_shell

PROJECT = Path(__file__).resolve().parent.parent
MODULE = PROJECT / 'module'
PROPS = dict(line.split('=', 1) for line in (MODULE / 'module.prop').read_text().splitlines() if '=' in line)
VERSION = PROPS['version']
APK = MODULE / f'omnicam-aura-{VERSION}.apk'
ARCHIVE = PROJECT / f'OmniCam-Aura-{VERSION}-KSU.zip'
sdk_path = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
if not sdk_path:
    properties = PROJECT / 'local.properties'
    if properties.exists():
        for line in properties.read_text(encoding='utf-8').splitlines():
            if line.startswith('sdk.dir='):
                sdk_path = line.partition('=')[2].replace('\\:', ':').replace('\\\\', '\\')
                break
if not sdk_path:
    raise RuntimeError('Set ANDROID_HOME or ANDROID_SDK_ROOT, or create local.properties with sdk.dir')
build_tools = sorted((Path(sdk_path) / 'build-tools').glob('*'), reverse=True)
AAPT_NAME = 'aapt2.exe' if os.name == 'nt' else 'aapt2'
SIGNER_NAME = 'apksigner.bat' if os.name == 'nt' else 'apksigner'
BUILD_TOOLS = next((p for p in build_tools if (p / AAPT_NAME).exists() and (p / SIGNER_NAME).exists()), None)
if BUILD_TOOLS is None:
    raise RuntimeError('Android SDK build-tools with aapt2 and apksigner are required')

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

require((MODULE / 'device.sh').read_text() == render_shell(json.loads(POLICY.read_text())),
        'device.sh differs from the shared Java/native device policy; regenerate it')

with ZipFile(ARCHIVE) as bundle, ZipFile(APK) as apk:
    require(bundle.testzip() is None, 'Module archive CRC failed')
    names = bundle.namelist()
    require([n for n in names if n.endswith('.apk')] == [APK.name], 'Expected exactly one Aura APK')
    require(bundle.read(APK.name) == APK.read_bytes(), 'Packaged APK differs from build')
    require('assets/xposed_init' in apk.namelist(), 'LSPosed Java entry missing')
    require(apk.read('assets/xposed_init').strip() == b'local.omnicam.aura.ModuleEntry', 'Wrong LSPosed entry')
    require(apk.read('assets/native_init').strip() == b'libaura_native.so', 'Wrong native entry')
    require('lib/arm64-v8a/libaura_native.so' in apk.namelist(), 'GR/POP native library missing')
    require(not any(b'local.jiege.camera' in apk.read(n) for n in apk.namelist() if n.endswith('.dex')), 'Old package reference in Aura hooks')
    for removed in ('master_hncs/', 'unlock25mp/', 'audio_policy_volumes.xml'):
        require(not any(n.startswith('payload/' + removed) for n in names), f'Unrelated payload: {removed}')
    require(not any('/meishe_lut/JG_' in n or '/meishe_lut/LUT65_' in n or '/meishe_lut/LeicaM9' in n for n in names), 'Muse LUTs leaked into Aura')
    required = ('libAlgoInterface.so', 'libBasicTonePhoto.so', 'libBasicTonePhotoX9.so', 'libBasicTonePhotoX10.so', 'libmsnativefilter.so')
    require(all('system/odm/lib64/' + n in names for n in required), 'Capture backend missing')
    for name in ('qing_tou.bin', 'hu_po.bin', 'polaroid_sdr.mslut'):
        require('payload/meishe_lut/' + name in names, f'Missing LUT: {name}')
    for name in ('customize.sh', 'device.sh', 'clear-overrides.sh', 'mount-state.sh', 'post-fs-data.sh', 'service.sh',
                 'inverse-light.sh', 'action.sh', 'uninstall.sh'):
        require(bundle.read(name) == (MODULE / name).read_bytes(), f'Packaged module file mismatch: {name}')
    require(apk.read('assets/symbols-plk110.json') == (PROJECT / 'app/src/main/assets/symbols-plk110.json').read_bytes(), 'PLK110 symbol rules missing or outdated')
    require(not any(n.endswith('/settings.conf') for n in names), 'Persistent camera override settings must not be packaged')
    require('post-mount.sh' not in names, 'Duplicate library binds must not be packaged')

manifest = subprocess.check_output([str(BUILD_TOOLS / AAPT_NAME), 'dump', 'xmltree', str(APK), '--file', 'AndroidManifest.xml'], text=True, encoding='utf-8')
badging = subprocess.check_output([str(BUILD_TOOLS / AAPT_NAME), 'dump', 'badging', str(APK)], text=True, encoding='utf-8')
require("name='local.omnicam.aura'" in badging and "application-label:'OmniCam Aura'" in badging, 'APK identity mismatch')
require(f"versionName='{VERSION}'" in badging and f"versionCode='{PROPS['versionCode']}'" in badging, 'APK/module version mismatch')
resources = subprocess.check_output([str(BUILD_TOOLS / AAPT_NAME), 'dump', 'resources', str(APK)], text=True, encoding='utf-8')
for name in ('snap_switch_on', 'snap_switch_off', 'snap_switch_1m', 'snap_switch_2_5m', 'snap_switch_5m'):
    require('drawable/' + name in resources, f'GR snap focus icon was stripped: {name}')
for component in ('E: activity ', 'E: activity-alias ', 'E: provider ', 'E: service ', 'E: receiver '):
    require(component not in manifest, f'Unexpected UI/component: {component}')
scope = (PROJECT / 'app/src/main/res/values/arrays.xml').read_text(encoding='utf-8')
require('com.oplus.camera' in scope and 'com.coloros.gallery3d' in scope and '<item>android</item>' not in scope, 'Scope mismatch')
algo = json.loads((MODULE / 'payload/oplus_camera_algo_switch_config').read_bytes())
pma_entries = json.loads((MODULE / 'payload/oplus_camera_config').read_bytes())
pma_hdr = next(entry for entry in pma_entries
               if entry['VendorTag'] == 'com.oplus.camera.capture.hdr.cap.mode.value')
require(int(pma_hdr['Count']) == len(pma_hdr['Value'].split(',')),
        'PMA110 capture HDR count differs from the effective mode list')
for mode in ('common', 'portrait', 'aiHighPixel'):
    group = next(g for g in algo['aps_capture_configs'] if g['mode'] == mode)
    for camera in (0, 1):
        entity = next(e for e in group['entity'] if e['id'] == camera)
        require(entity['aps_algo_color_palette'] == 1, f'Palette capture node missing: {mode}/{camera}')
for script in ('post-fs-data.sh', 'service.sh'):
    text = (MODULE / script).read_text(encoding='utf-8')
    for removed in ('master_hncs', 'unlock25mp', 'audio_policy_volumes', 'InsensorZoom'):
        require(removed not in text, f'Unrelated mount/staging: {removed}')
plk = MODULE / 'profiles/PLK110/config'
unit = json.loads((plk / 'camera_unit_config').read_bytes())
require(unit['camera_id_list'] == ['0', '1', '2', '3', '4'], 'PLK110 sensor IDs changed')
require('rear_ultra_tele' not in unit['mode_type_list'], 'PMA110 lens leaked into PLK110')
require(not (plk / 'oplus_camera_aps_config').exists(), 'PLK110 must use stock APS hardware parameters')
plk_entries = {entry['VendorTag']: entry for entry in json.loads((plk / 'oplus_camera_config').read_bytes())}
plk_values = {key: entry['Value'] for key, entry in plk_entries.items()}
plk_preview_hdr = plk_entries['com.oplus.camera.preview.hdr.cap.mode.value']
require('gr' in plk_preview_hdr['Value'].split(','), 'PLK110 GR HDR preview mode is missing')
require(int(plk_preview_hdr['Count']) == len(plk_preview_hdr['Value'].split(',')),
        'PLK110 preview HDR count differs from the effective mode list')
require('com.oplus.camera.preview.hdr.display.transform.sdr.mode.value' not in plk_entries,
        'PLK110 must keep native HDR output instead of forcing SDR display transform')
require(not (int(plk_values.get('com.oplus.feature.colorful.screen.torch.config', '0'), 2) & 4), 'PLK110 must keep stock inverse-light behavior by default')
decision = json.loads((plk / 'oplus_camera_preview_decision_config.json').read_bytes())
master_or_gr = {
    'eq': ['captureMode', 'APS_CAPMODE_MASTER'],
    'eq1': ['captureMode', 'APS_CAPMODE_GRMODE'],
}


def count_decision(value, expected):
    count = int(isinstance(value, dict) and value.get('or') == expected)
    if isinstance(value, dict):
        count += sum(count_decision(child, expected) for child in value.values())
    elif isinstance(value, list):
        count += sum(count_decision(child, expected) for child in value)
    return count


decision_targets = (
    (decision['multiAlgo']['prerequisites'], 'PREREQUISITES_MASTER'),
    (decision['singleAlgo']['algo'], 'SINGLE_ALGO_BASIC_TONE'),
    (decision['singleAlgo']['algo'], 'SINGLE_ALGO_RECTIFY'),
    (decision['singleAlgo']['algo'], 'SINGLE_ALGO_HDR_TRANSFROM'),
)
for entries, mode in decision_targets:
    modes = [entry for entry in entries if entry['mode'] == mode]
    require(len(modes) == 1 and count_decision(modes[0]['condition'], master_or_gr) == 1,
            f'PLK110 {mode} must extend exactly one MASTER condition to GRMODE')
require(count_decision(decision, master_or_gr) == len(decision_targets),
        'PLK110 decision table contains an unexpected MASTER/GRMODE extension')
mask_rules = json.loads((PROJECT / 'app/src/main/assets/symbols.json').read_bytes())['camera']
mask_rules.update(json.loads((PROJECT / 'app/src/main/assets/symbols-plk110.json').read_bytes())['camera'])
require(all(name in mask_rules for name in ('PreviewMask.draw', 'PreviewMask.canvas', 'PreviewMask.program',
    'PreviewMask.shader', 'PreviewMask.shaderValid')), 'POP inverse-mask shader fingerprints are missing')
with ZipFile(APK) as apk:
    dex = b''.join(apk.read(name) for name in apk.namelist() if name.endswith('.dex'))
    require(all(value in dex for value in (b'PreviewMaskShader', b'texture_vertex_shader_inverse_mask',
        b'draw_inverse_mask_shader', b'canvas constructor hook installed')), 'POP inverse-mask constructor hook is missing')
with ZipFile(ARCHIVE) as bundle:
    for name in ('camera_unit_config', 'camera_unit_feature_config.protobuf', 'oplus_camera_config',
                 'oplus_camera_algo_switch_config', 'oplus_camera_preview_decision_config.json'):
        require(bundle.read('profiles/PLK110/config/' + name) == (plk / name).read_bytes(), f'PLK110 profile mismatch: {name}')
signer = ['cmd', '/c'] if os.name == 'nt' else []
subprocess.run([*signer, str(BUILD_TOOLS / SIGNER_NAME), 'verify', str(APK)], check=True)
print('PASS: signed headless Aura APK; camera/gallery scope; GR/POP backends; PMA110 palette nodes; PLK110 profile and symbol rules; packaged scripts match source')
