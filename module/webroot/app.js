(() => {
  "use strict";

  const commands = Object.freeze({
    status: "sh /data/adb/modules/omnicam_aura/control.sh status",
    on: "sh /data/adb/modules/omnicam_aura/control.sh inverse on",
    off: "sh /data/adb/modules/omnicam_aura/control.sh inverse off",
    export: "sh /data/adb/modules/omnicam_aura/diagnostics.sh",
  });
  const elements = Object.fromEntries(
    [...document.querySelectorAll("[id]")].map((element) => [element.id, element]),
  );
  let currentStatus = null;
  let pending = false;
  let callbackCount = 0;
  let archivePath = "";

  function message(id, text, kind = "neutral") {
    elements[id].textContent = text;
    elements[id].dataset.kind = kind;
  }

  function updateButtons() {
    const bridgeAvailable = typeof window.ksu?.exec === "function";
    elements.refresh.disabled = pending || !bridgeAvailable;
    elements.export.disabled = pending || !bridgeAvailable;
    elements["copy-path"].disabled = pending || !archivePath;
    const canSetLight = !pending && bridgeAvailable && currentStatus?.model === "PLK110";
    elements["light-on"].disabled = !canSetLight || !currentStatus.compatible || currentStatus.inverseLight;
    elements["light-off"].disabled = !canSetLight || !currentStatus.inverseLight;
    document.body.setAttribute("aria-busy", String(pending));
  }

  function renderStatus(status) {
    const stringFields = ["model", "firmware", "cameraVersion", "moduleVersion", "reason"];
    if (
      !status ||
      stringFields.some((field) => typeof status[field] !== "string") ||
      !/^[0-9]+$/.test(String(status.androidSdk)) ||
      typeof status.compatible !== "boolean" ||
      typeof status.inverseLight !== "boolean" ||
      (status.activeInverseLight !== null && typeof status.activeInverseLight !== "boolean")
    ) {
      throw new Error("模块返回的状态格式不完整，请导出日志检查。");
    }
    currentStatus = status;
    message("module-version", `v${status.moduleVersion}`);
    message("model", status.model);
    message("firmware", status.firmware);
    message("android-sdk", String(status.androidSdk));
    message("camera-version", status.cameraVersion);
    message("compatibility", status.compatible ? "版本范围内" : "暂不支持", status.compatible ? "success" : "error");
    message("compatibility-reason", status.reason);
    message("selected-light", status.inverseLight ? "开启" : "关闭");
    message("active-light", status.activeInverseLight === null ? "未确认" : status.activeInverseLight ? "开" : "关");
    elements["light-on"].setAttribute("aria-pressed", String(status.inverseLight));
    elements["light-off"].setAttribute("aria-pressed", String(!status.inverseLight));
    elements["restart-note"].hidden = status.model !== "PLK110" || status.activeInverseLight === status.inverseLight;
    message("restart-note", status.activeInverseLight === null ? "系统挂载状态未确认；保存的选择在重启后应用。" : "选择已改变，重启手机后生效。");
    message("light-availability", status.model !== "PLK110" ? "此开关仅用于 PLK110。" : status.compatible ? "选择会保存，重启手机后生效。" : "当前版本不在支持范围内，可以关闭已保存的补光选择。");
  }

  // 沿用 KernelSU / KowSU 官方 exec 协议，仅允许上方四条固定命令。
  // https://github.com/tiann/KernelSU/blob/main/js/index.js
  // https://github.com/KOWX712/KernelSU/blob/master/js/index.js
  function execute(action) {
    return new Promise((resolve, reject) => {
      const callbackName = `aura_exec_${Date.now()}_${callbackCount++}`;
      let finished = false;
      const timer = setTimeout(() => {
        cleanup();
        reject(new Error("等待模块响应超时，执行结果未确认。请先刷新状态；本页不会自动重试。"));
      }, action === "export" ? 60000 : 20000);

      function cleanup() {
        finished = true;
        clearTimeout(timer);
        delete window[callbackName];
      }

      window[callbackName] = (errno, stdout, stderr) => {
        if (finished) return;
        cleanup();
        if (errno !== 0) {
          reject(new Error(`执行失败（${errno}）：${stderr || stdout || "模块未提供错误详情。"}`));
          return;
        }
        resolve(stdout);
      };
      try {
        window.ksu.exec(commands[action], "{}", callbackName);
      } catch (error) {
        if (finished) return;
        cleanup();
        reject(error);
      }
    });
  }

  async function runAction(messageId, progress, task) {
    if (pending) return;
    pending = true;
    updateButtons();
    message(messageId, progress);
    try {
      await task();
    } catch (error) {
      message(messageId, error instanceof Error ? error.message : String(error), "error");
    } finally {
      pending = false;
      updateButtons();
    }
  }

  async function refreshStatus() {
    await runAction("status-message", "正在读取状态…", async () => {
      currentStatus = null;
      message("compatibility", "正在读取");
      try {
        renderStatus(JSON.parse(await execute("status")));
      } catch (error) {
        message("compatibility", "读取失败", "error");
        message("compatibility-reason", "状态未能更新，可尝试刷新或导出诊断日志。", "error");
        throw error;
      }
      message("status-message", "状态已更新。");
    });
  }

  async function setInverseLight(enabled) {
    await runAction("light-message", "正在保存选择…", async () => {
      currentStatus = null;
      try {
        renderStatus(JSON.parse(await execute(enabled ? "on" : "off")));
      } catch (error) {
        message("selected-light", "未确认");
        message("light-availability", "保存结果未能确认，请刷新状态后再操作。", "error");
        throw error;
      }
      if (currentStatus.inverseLight !== enabled) {
        throw new Error("模块未返回预期的补光选择，请刷新状态或导出日志。");
      }
      message("light-message", `已保存为${enabled ? "开启" : "关闭"}，请重启手机使其生效。`, "success");
    });
  }

  async function exportLogs() {
    await runAction("export-message", "正在整理诊断日志，请稍候…", async () => {
      archivePath = "";
      elements["archive-result"].hidden = true;
      message("archive-path", "");
      message("copy-message", "");
      const result = (await execute("export")).trim();
      if (!/^\/[^\r\n\x00-\x1f]+\.tar\.gz$/.test(result)) {
        throw new Error("导出命令未返回单一有效归档路径，请查看模块执行日志。");
      }
      archivePath = result;
      message("archive-path", archivePath);
      elements["archive-result"].hidden = false;
      message("export-message", "诊断包已生成。请在文件管理器中找到下方文件并分享。", "success");
    });
  }

  elements.refresh.addEventListener("click", refreshStatus);
  elements["light-on"].addEventListener("click", () => setInverseLight(true));
  elements["light-off"].addEventListener("click", () => setInverseLight(false));
  elements.export.addEventListener("click", exportLogs);
  elements["copy-path"].addEventListener("click", () => runAction("copy-message", "正在复制…", async () => {
    if (!navigator.clipboard?.writeText) {
      throw new Error("当前管理器未开放剪贴板，请长按上方路径复制。");
    }
    await navigator.clipboard.writeText(archivePath);
    message("copy-message", "路径已复制。", "success");
  }));

  if (typeof window.ksu?.exec !== "function") {
    message("compatibility", "未连接管理器", "error");
    message("compatibility-reason", "请从 KernelSU / KowSU 管理器的模块网页打开此页面。", "error");
    message("light-availability", "连接管理器后可读取和修改补光选择。");
    updateButtons();
  } else {
    refreshStatus();
  }
})();
