"""用受控 KernelSU bridge 验证网页交互合同，不代替原生管理器验收。"""

from html.parser import HTMLParser
from pathlib import Path
import subprocess
import unittest

PROJECT = Path(__file__).resolve().parent.parent
WEBROOT = PROJECT / 'module/webroot'

HARNESS = r'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html = fs.readFileSync('module/webroot/index.html', 'utf8');
const source = fs.readFileSync('module/webroot/app.js', 'utf8');
const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
const sample = {
  model: 'PLK110', androidSdk: 37, firmware: 'PLK110_17.0.0.105(CN01)',
  cameraVersion: '7.006.125', moduleVersion: '1.1.2', compatible: true,
  reason: '同系列版本，功能按运行时合同检查。', inverseLight: false,
  activeInverseLight: false,
};
const flush = () => new Promise((resolve) => setImmediate(resolve));

function createView({ bridge = true, clipboard = true, bridgeError = '' } = {}) {
  const elements = Object.fromEntries(ids.map((id) => [id, {
    textContent: '', dataset: {}, disabled: false, hidden: false, attributes: {}, listeners: {},
    setAttribute(name, value) { this.attributes[name] = value; },
    addEventListener(name, listener) { this.listeners[name] = listener; },
  }]));
  const calls = [];
  const replies = [];
  const copied = [];
  const timers = new Map();
  const clearedTimers = [];
  let timerCounter = 0;
  let clock = 0;
  function setTimeout(callback, delay) {
    const id = ++timerCounter;
    timers.set(id, { callback, deadline: clock + delay });
    return id;
  }
  function clearTimeout(id) {
    timers.delete(id);
    clearedTimers.push(id);
  }
  const window = {};
  if (bridge) window.ksu = { exec(command, options, callbackName) {
    if (bridgeError) throw new Error(bridgeError);
    assert.equal(options, '{}');
    calls.push(command);
    replies.push({ name: callbackName, callback: window[callbackName] });
  }};
  const navigator = clipboard ? { clipboard: { async writeText(text) { copied.push(text); } } } : {};
  const document = {
    querySelectorAll() { return Object.values(elements); },
    body: { setAttribute() {} },
  };
  for (const [id, element] of Object.entries(elements)) element.id = id;
  const context = vm.createContext({ window, document, navigator, console, Error, setTimeout, clearTimeout });
  new vm.Script(source, { filename: 'app.js' }).runInContext(context);
  return {
    elements, calls, copied, window, timers, clearedTimers,
    takeReply() { return replies.shift(); },
    async advance(milliseconds) {
      const target = clock + milliseconds;
      for (;;) {
        const due = [...timers.entries()]
          .filter(([, timer]) => timer.deadline <= target)
          .sort((left, right) => left[1].deadline - right[1].deadline)[0];
        if (!due) break;
        const [id, timer] = due;
        clock = timer.deadline;
        timers.delete(id);
        timer.callback();
        await flush();
      }
      clock = target;
    },
    async reply(errno, output, stderr = '') {
      const { name: callbackName } = replies.shift();
      assert.ok(callbackName, '必须存在待处理的 bridge 回调');
      window[callbackName](errno, typeof output === 'string' ? output : JSON.stringify(output), stderr);
      await flush();
      assert.equal(window[callbackName], undefined, '已完成回调必须移除');
    },
    click(id) { return elements[id].listeners.click(); },
  };
}
'''


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.resources = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if 'id' in attributes:
            self.ids.append(attributes['id'])
        if tag == 'script':
            self.resources.append(attributes.get('src'))
        if tag == 'link' and attributes.get('rel') == 'stylesheet':
            self.resources.append(attributes.get('href'))


class WebUiTests(unittest.TestCase):
    def run_js(self, code):
        result = subprocess.run(['node', '--input-type=module'], input=HARNESS + '\n' + code,
                                cwd=PROJECT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_html_has_unique_targets_and_only_bundled_resources(self):
        parser = PageParser()
        parser.feed((WEBROOT / 'index.html').read_text())
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        self.assertEqual(set(parser.resources), {'style.css', 'app.js'})
        for resource in parser.resources:
            self.assertTrue((WEBROOT / resource).is_file())
        self.assertIn("connect-src 'none'", (WEBROOT / 'index.html').read_text())
        self.assertNotIn('innerHTML', (WEBROOT / 'app.js').read_text())

    def test_status_and_explicit_on_off_preserve_active_state(self):
        self.run_js(r'''
const view = createView();
assert.ok(view.elements.export.disabled);
assert.equal(view.calls[0], 'sh /data/adb/modules/omnicam_aura/control.sh status');
await view.reply(0, sample);
assert.equal(view.elements.model.textContent, 'PLK110');
assert.equal(view.elements['light-on'].disabled, false);
assert.equal(view.elements['light-off'].disabled, true);
assert.equal(view.elements['restart-note'].hidden, true);
view.click('light-on');
view.click('light-on');
view.click('export');
assert.equal(view.calls.length, 2, '待处理时不能重复执行或启动另一操作');
assert.equal(view.calls[1], 'sh /data/adb/modules/omnicam_aura/control.sh inverse on');
await view.reply(0, { ...sample, inverseLight: true });
assert.equal(view.elements['selected-light'].textContent, '开启');
assert.equal(view.elements['active-light'].textContent, '关');
assert.equal(view.elements['restart-note'].hidden, false);
assert.match(view.elements['light-message'].textContent, /重启/);
view.click('light-off');
assert.equal(view.calls[2], 'sh /data/adb/modules/omnicam_aura/control.sh inverse off');
await view.reply(0, sample);
assert.equal(view.elements['selected-light'].textContent, '关闭');
assert.equal(view.elements['restart-note'].hidden, true);
''')

    def test_incompatible_device_allows_export_and_disabling_selected_light(self):
        self.run_js(r'''
const view = createView();
await view.reply(0, { ...sample, compatible: false, inverseLight: true, activeInverseLight: null });
assert.equal(view.elements['light-on'].disabled, true);
assert.equal(view.elements['light-off'].disabled, false);
assert.equal(view.elements.export.disabled, false);
view.click('refresh');
await view.reply(0, { ...sample, model: 'PMA110' });
assert.equal(view.elements['light-on'].disabled, true);
assert.equal(view.elements['light-off'].disabled, true);
''')

    def test_status_failure_does_not_prevent_diagnostics_and_can_refresh(self):
        self.run_js(r'''
const view = createView();
await view.reply(1, '', '固件无法读取');
assert.equal(view.elements['status-message'].dataset.kind, 'error');
assert.match(view.elements['status-message'].textContent, /固件无法读取/);
assert.equal(view.elements['light-on'].disabled, true);
assert.equal(view.elements.export.disabled, false);
view.click('refresh');
await view.reply(0, sample);
assert.equal(view.elements['light-on'].disabled, false);
''')

    def test_invalid_or_incomplete_status_is_never_reported_success(self):
        self.run_js(r'''
for (const response of ['broken json', { ...sample, inverseLight: 'true' },
                        { ...sample, activeInverseLight: undefined }]) {
  const view = createView();
  await view.reply(0, response);
  assert.equal(view.elements['status-message'].dataset.kind, 'error');
  assert.equal(view.elements['light-on'].disabled, true);
  assert.equal(view.elements.export.disabled, false);
}
''')

    def test_light_failure_invalidates_choice_until_refresh(self):
        self.run_js(r'''
const view = createView();
await view.reply(0, sample);
view.click('light-on');
await view.reply(1, '', '保存失败');
assert.equal(view.elements['light-message'].dataset.kind, 'error');
assert.match(view.elements['light-message'].textContent, /保存失败/);
assert.equal(view.elements['selected-light'].textContent, '未确认');
assert.equal(view.elements['light-on'].disabled, true);
assert.equal(view.elements['light-off'].disabled, true);
view.click('refresh');
await view.reply(0, sample);
view.click('light-on');
await view.reply(0, sample);
assert.equal(view.elements['light-message'].dataset.kind, 'error');
assert.match(view.elements['light-message'].textContent, /未返回预期/);
''')

    def test_export_result_and_copy_use_only_confirmed_archive_path(self):
        self.run_js(r'''
const view = createView();
await view.reply(0, sample);
view.click('export');
assert.equal(view.calls[1], 'sh /data/adb/modules/omnicam_aura/diagnostics.sh');
const archive = '/storage/emulated/0/Download/OmniCam-Aura/OmniCam-Aura-20261009-123456-abcdefgh.tar.gz';
await view.reply(0, archive + '\n');
assert.equal(view.elements['archive-path'].textContent, archive);
assert.equal(view.elements['archive-result'].hidden, false);
assert.equal(view.elements['copy-path'].disabled, false);
await view.click('copy-path');
assert.deepEqual(view.copied, [archive]);
assert.equal(view.elements['copy-message'].dataset.kind, 'success');
view.click('export');
await view.reply(1, '', '空间不足');
assert.equal(view.elements['archive-result'].hidden, true);
assert.equal(view.elements['copy-path'].disabled, true);
assert.equal(view.elements['export-message'].dataset.kind, 'error');
''')

    def test_invalid_archive_output_is_not_shareable(self):
        self.run_js(r'''
for (const output of ['', 'relative.tar.gz', '/tmp/a.tar.gz\n/tmp/b.tar.gz',
                      '/tmp/a.tar.gz\nextra', '/tmp/a.zip']) {
  const view = createView();
  await view.reply(0, sample);
  view.click('export');
  await view.reply(0, output);
  assert.equal(view.elements['archive-result'].hidden, true);
  assert.equal(view.elements['copy-path'].disabled, true);
  assert.equal(view.elements['export-message'].dataset.kind, 'error');
}
''')

    def test_missing_clipboard_has_visible_failure_without_fake_success(self):
        self.run_js(r'''
const view = createView({ clipboard: false });
await view.reply(0, sample);
view.click('export');
await view.reply(0, '/sdcard/Download/OmniCam-Aura/a.tar.gz');
await view.click('copy-path');
assert.equal(view.elements['copy-message'].dataset.kind, 'error');
assert.match(view.elements['copy-message'].textContent, /未开放剪贴板/);
''')

    def test_bridge_absence_and_bridge_exception_remain_visible(self):
        self.run_js(r'''
const absent = createView({ bridge: false });
assert.equal(absent.elements.export.disabled, true);
assert.equal(absent.elements.refresh.disabled, true);
assert.equal(absent.elements.compatibility.textContent, '未连接管理器');
assert.equal(absent.calls.length, 0);
const failed = createView({ bridgeError: 'bridge denied' });
await flush();
assert.equal(failed.elements['status-message'].dataset.kind, 'error');
assert.match(failed.elements['status-message'].textContent, /bridge denied/);
assert.equal(Object.keys(failed.window).filter((key) => key.startsWith('aura_exec_')).length, 0);
assert.equal(failed.timers.size, 0);
assert.equal(failed.clearedTimers.length, 1);
''')

    def test_missing_status_callback_times_out_and_late_reply_cannot_change_state(self):
        self.run_js(r'''
const view = createView();
const late = view.takeReply();
await view.advance(19999);
assert.equal(view.elements.refresh.disabled, true);
await view.advance(1);
assert.equal(view.window[late.name], undefined);
assert.equal(view.timers.size, 0);
assert.equal(view.clearedTimers.length, 1);
assert.equal(view.elements.refresh.disabled, false);
assert.equal(view.elements.export.disabled, false);
assert.equal(view.elements['light-on'].disabled, true);
assert.equal(view.elements['status-message'].dataset.kind, 'error');
assert.match(view.elements['status-message'].textContent, /超时.*执行结果未确认.*先刷新/);
assert.equal(view.calls.length, 1, '超时后不得自动重试');
view.click('refresh');
late.callback(0, JSON.stringify({ ...sample, model: 'LATE' }), '');
await flush();
assert.equal(view.elements.refresh.disabled, true, '旧回调不能解除新请求的等待状态');
assert.notEqual(view.elements.model.textContent, 'LATE');
await view.reply(0, sample);
assert.equal(view.elements.model.textContent, 'PLK110');
assert.equal(view.elements['status-message'].dataset.kind, 'neutral');
''')

    def test_missing_light_callback_requires_refresh_before_another_selection(self):
        self.run_js(r'''
for (const enabled of [true, false]) {
  const view = createView();
  await view.reply(0, { ...sample, inverseLight: !enabled, activeInverseLight: !enabled });
  view.click(enabled ? 'light-on' : 'light-off');
  const late = view.takeReply();
  await view.advance(20000);
  assert.equal(view.window[late.name], undefined);
  assert.equal(view.timers.size, 0);
  assert.equal(view.elements.refresh.disabled, false);
  assert.equal(view.elements['light-on'].disabled, true);
  assert.equal(view.elements['light-off'].disabled, true);
  assert.equal(view.elements['selected-light'].textContent, '未确认');
  assert.match(view.elements['light-message'].textContent, /超时.*执行结果未确认.*先刷新/);
  assert.equal(view.calls.length, 2, '超时后不得重发补光命令');
  view.click('refresh');
  await view.reply(0, { ...sample, inverseLight: enabled, activeInverseLight: !enabled });
  late.callback(0, JSON.stringify({ ...sample, inverseLight: !enabled }), '');
  await flush();
  assert.equal(view.elements['selected-light'].textContent, enabled ? '开启' : '关闭');
  assert.equal(view.elements['light-message'].dataset.kind, 'error', '迟到回调不能伪造保存成功');
}
''')

    def test_missing_export_callback_has_longer_deadline_and_no_late_archive(self):
        self.run_js(r'''
const view = createView();
await view.reply(0, sample);
view.click('export');
const late = view.takeReply();
await view.advance(59999);
assert.equal(view.elements.export.disabled, true);
await view.advance(1);
assert.equal(view.window[late.name], undefined);
assert.equal(view.timers.size, 0);
assert.equal(view.elements.refresh.disabled, false);
assert.equal(view.elements.export.disabled, false);
assert.equal(view.elements['archive-result'].hidden, true);
assert.equal(view.elements['copy-path'].disabled, true);
assert.match(view.elements['export-message'].textContent, /超时.*执行结果未确认/);
late.callback(0, '/sdcard/Download/OmniCam-Aura/late.tar.gz', '');
await flush();
assert.equal(view.elements['archive-result'].hidden, true);
assert.equal(view.elements['archive-path'].textContent, '');
assert.equal(view.elements['export-message'].dataset.kind, 'error');
assert.equal(view.calls.length, 2, '超时后不得自动重新导出');
''')

    def test_completed_commands_clear_timers_for_success_and_failure(self):
        self.run_js(r'''
const view = createView();
assert.equal(view.timers.size, 1);
await view.reply(0, sample);
assert.equal(view.timers.size, 0);
assert.equal(view.clearedTimers.length, 1);
await view.advance(60000);
assert.equal(view.elements['status-message'].textContent, '状态已更新。');
view.click('export');
assert.equal(view.timers.size, 1);
await view.reply(1, '', '导出失败');
assert.equal(view.timers.size, 0);
assert.equal(view.clearedTimers.length, 2);
await view.advance(60000);
assert.match(view.elements['export-message'].textContent, /导出失败/);
assert.doesNotMatch(view.elements['export-message'].textContent, /超时/);
''')

    def test_native_output_is_rendered_as_text(self):
        self.run_js(r'''
const view = createView();
const injected = '<img src=x onerror=alert(1)>';
await view.reply(0, { ...sample, reason: injected });
assert.equal(view.elements['compatibility-reason'].textContent, injected);
''')


if __name__ == '__main__':
    unittest.main()
