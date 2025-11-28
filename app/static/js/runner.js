// =====================================
// runner.js
// 负责：任务运行、状态监控、日志刷新、下载、结果列表
// =====================================

// const VERSION = '20251128';
import { state } from './state.js?v=20251128';
import { API } from './api.js?v=20251128';
import { UI } from './ui.js?v=20251128';



export function updateRunButtonState() {
  const canRun =
    state.sample_list_path &&
    UI.val("cfg").trim() &&
    state.reviewConfirmed;

  UI.setDisabled("btnRun", !canRun);
}


export const Runner = {

  pollTimer: null,
  usageTimer: null,
  pollIntervalMs: 3000,
  usageIntervalMs: 3000,
  autoPollEnabled: false,
  lastStatus: 'idle',
  wrapLines: true,

  // 初始化（在 app.js 调用）
  init() {
    UI.bindClick('btnRun', () => Runner.start());
    UI.bindClick('btnPollOnce', () => Runner.refresh());
    UI.bindClick('btnClearLog', () => UI.setText('logsBox', ''));
    UI.bindClick('btnCopyLog', () =>
      navigator.clipboard.writeText(UI.el('logsBox').textContent)
    );
    UI.bindClick('btnResults', () => Runner.showResults());

    // 下载
    UI.bindClick('btnDownload', () =>
      Runner.download(UI.val('dlPreset'), UI.val('dlFormat'))
    );

    // 自动轮询开关
    UI.bindChange('autoPoll', (e) => Runner.toggleAutoPoll(e.target.checked));
    UI.bindChange('toggleWrap', (e) => Runner.toggleWrap(e.target.checked));
    UI.bindClick("btnStop", async () => {
      if (!confirm("Stop the pipeline?")) return;

      UI.busy("btnStop", true);

      try {
        await API.stop();
        UI.toast("Pipeline stopped", "error");

        // ★ 立即停止轮询 ★
        Runner._stopAutoPollUI();

        // ★ 更新状态为 failed/stopped ★
        Runner._setStatus("failed");
        Runner.stopUsagePolling();
        Runner.setRunButtonRunning(false);

      } finally {
        UI.busy("btnStop", false);
      }
    });

    // 默认启用换行
    Runner.toggleWrap(true);
  },

  // ===============================
  // 运行任务
  // ===============================
  async start() {
    try {
      Runner.setRunButtonRunning(true);
      Runner.lastStatus = 'running';
      await API.runActive();
      Runner._setStatus('running');
      Runner.updateRunningUI(true);

      // 自动开始日志轮询
      UI.el('autoPoll').checked = true;
      Runner.toggleAutoPoll(true);

      UI.toast("ViiR pipeline started", "success");
    } catch (err) {
      UI.toast(err.message, "error");
      Runner.setRunButtonRunning(false);
    }
  },

  // ===============================
  // 手动刷新状态 + 日志
  // ===============================
  async refresh() {
    await Runner.updateStatus();
    await Runner.updateLogs();
    await Runner.updateUsage();
  },


  async updateUsage() {
    if (Runner.lastStatus !== 'running') return;
    try {
      const u = await API.usage();
      UI.setText("usageCPU", `${u.cpu}%`);
      UI.setText("usageMEM", `${u.mem}%`);
      UI.setText("usageTime", (u.runtime / 60).toFixed(1) + " min");
      Runner.setUsageColor("usageCPU", u.cpu);
      Runner.setUsageColorMem("usageMEM", u.mem);
    } catch {
      // ignore usage errors
    }
  },

  // ===============================
  // 轮询开关
  // ===============================
  toggleAutoPoll(enable) {
    if (enable) {
      if (Runner.autoPollEnabled) return;
      Runner.autoPollEnabled = true;
      Runner.refresh();
      Runner.pollTimer = setInterval(() => {
        Runner.updateStatus();
        Runner.updateLogs();
      }, Runner.pollIntervalMs);
      Runner.startUsagePolling();
    } else {
      if (!Runner.autoPollEnabled) return;
      Runner.autoPollEnabled = false;
      if (Runner.pollTimer) {
        clearInterval(Runner.pollTimer);
        Runner.pollTimer = null;
      }
      Runner.stopUsagePolling();
    }
  },


  // ===============================
  // 状态更新
  // ===============================
  async updateStatus() {
    try {
      const st = await API.getStatus();
      const status = st.status || 'idle';
      Runner.lastStatus = status;
      Runner._setStatus(status);
      Runner.setRunButtonRunning(status === 'running');
      Runner.updateRunningUI(status === 'running');
      if (status === 'running') {
        Runner.startUsagePolling();
        await Runner._updateProgressFromLogs();
      } else {
        Runner.stopUsagePolling();
        if (status === 'finished' || status === 'failed') {
          Runner._stopAutoPollUI();
        }
      }
    } catch (err) {
      UI.toast("Status error: " + err.message, "error");
    }
  },

  // pill 状态更新
  _setStatus(stat) {
    const map = { idle: 'pending', running: 'inprog', finished: 'completed', failed: 'failed' };

    const pillSys = UI.el('pillHealth') || null;
    const pillHeader = UI.el('pillStatus') || null;
    const pillPanel = UI.el('pillStatusPanel') || null;

    [pillSys, pillHeader, pillPanel].forEach((pill) => {
      if (pill) {
        pill.className = `pill status ${map[stat] || 'pending'}`;
        pill.textContent = stat;
      }
    });

    if (stat === 'finished') {
      const prog = UI.el('prog');
      if (prog) prog.style.width = '100%';
    }
  },

  // ===============================
  // 更新日志
  // ===============================
  async updateLogs() {
    try {
      const text = await API.getLogs(400);
      const merged = Runner.mergeLogLines(text);
      UI.setText('logsBox', merged);
    } catch (err) {
      UI.toast("Log error: " + err.message, "error");
    }
  },

  // 日志合并（去掉重复进度行）
  mergeLogLines(s) {
    const lines = s.split(/\r?\n/);
    const out = [];

    const keep = [
      /^succeeded\(\d+\)/,
      /^\s*\[\d+M\]\s*Kmers parsed\./,
      /^ROUND\s*=\s*\d+/
    ];

    let lastKey = '';
    for (const L of lines) {
      let k = '';
      for (const rx of keep) if (rx.test(L)) k = rx.toString();

      if (k) {
        if (out.length && lastKey === k) {
          out[out.length - 1] = L;  // 覆盖上一次
        } else {
          out.push(L);
        }
        lastKey = k;
      } else {
        out.push(L);
        lastKey = '';
      }
    }
    return out.join('\n');
  },

  // ===============================
  // 根据日志推断进度 %
  // ===============================
  async _updateProgressFromLogs() {
    try {
      const text = await API.getLogs(60);
      const m = text.match(/(\d+\.\d+)%\s+completed/gi);
      if (m) {
        const last = m[m.length - 1].match(/([\d.]+)/)[1];
        UI.el('prog').style.width = Math.min(100, Number(last)) + '%';
        return;
      }
    } catch {
      /* ignore */
    }
  },

  // ===============================
  // 下载
  // ===============================
  download(preset, fmt) {
    API.download(preset, fmt);
  },

  // ===============================
  // 结果列表
  // ===============================
  async showResults() {
    try {
      const arr = await API.listResults();
      const txt = arr.map(o => `${o.path} [${o.size}]`).join('\n');
      UI.setText('resultsBox', txt);
    } catch (err) {
      UI.toast(err.message, "error");
    }
  },

  startUsagePolling() {
    if (!Runner.autoPollEnabled) return;
    if (Runner.usageTimer) return;
    Runner.usageTimer = setInterval(() => Runner.updateUsage(), Runner.usageIntervalMs);
  },

  stopUsagePolling() {
    if (Runner.usageTimer) {
      clearInterval(Runner.usageTimer);
      Runner.usageTimer = null;
    }
  },

  _stopAutoPollUI() {
    if (Runner.pollTimer) {
      clearInterval(Runner.pollTimer);
      Runner.pollTimer = null;
    }
    Runner.autoPollEnabled = false;
    Runner.stopUsagePolling();
    const auto = UI.el('autoPoll');
    if (auto) auto.checked = false;
  },

  setRunButtonRunning(isRunning) {
    const btn = UI.el('btnRun');
    if (!btn) return;
    btn.disabled = !!isRunning;
    btn.classList.toggle('btn-disabled', !!isRunning);
    if (isRunning) {
      btn.textContent = "Running...";
    } else {
      btn.textContent = "Run ViiR";
    }
  },

  toggleWrap(enable) {
    Runner.wrapLines = enable;
    const log = UI.el('logsBox');
    if (!log) return;
    log.classList.toggle('log-nowrap', !enable);
  },

  setUsageColor(id, val) {
    const el = UI.el(id);
    if (!el) return;
    el.className = "";
    if (val < 40) el.classList.add("usage-green");
    else if (val < 70) el.classList.add("usage-yellow");
    else {
      el.classList.add("usage-red");
      if (val >= 90) el.classList.add("usage-critical");
    }
  },

  setUsageColorMem(id, val) {
    const el = UI.el(id);
    if (!el) return;
    el.className = "";
    if (val < 50) el.classList.add("usage-green");
    else if (val < 80) el.classList.add("usage-yellow");
    else {
      el.classList.add("usage-red");
      if (val >= 90) el.classList.add("usage-critical");
    }
  },

  updateRunningUI(isRunning) {
    const banner = UI.el('runStepBanner');
    if (banner) {
      const step4 = document.getElementById('wizard-step4');
      const onStep4 = step4?.classList.contains('active');
      banner.style.display = isRunning && onStep4 ? 'block' : 'none';
    }
    const runNav = document.querySelector('.nav-btn[data-target="run"]');
    if (runNav) {
      runNav.classList.toggle('nav-pulse', isRunning);
    }
  }
};
