// =====================================
// config.js
// 负责：config.yaml 的生成、编辑、保存
// =====================================
import { UI } from '/static/js/ui.js?v=20251128';
import { API } from '/static/js/api.js?v=20251128';
import { state, resetReviewConfirmation } from '/static/js/state.js?v=20251128';
import { updateRunButtonState } from '/static/js/runner.js?v=20251128';
import { Wizard } from '/static/js/wizard.js?v=20251128';
import { Review } from '/static/js/review.js?v=20251128';

export const Config = {
  templateBase: "",
  generated: false,
  saved: false,
  _internalUpdating: false,

  // 初始化（app.js 中调用）
  init() {
    state.configSaved = false;
    // Generate Preview 按钮
    UI.bindClick('btnGen', () => {    
      const yml = Config.generate();
      updateRunButtonState();
    });

    // Save Config 按钮
    UI.bindClick("btnSaveCfg", async () => {
      await Config.save();
      updateRunButtonState();
    });
    UI.bindClick("btnNextStep3", () => {
      Config.goToReview();
    });

    // 监控输入变化
    [
      'threads',
      'pval',
      'outDir',
      'ssType',
      'maxMem',
      'adapterPath',
      'pfamPath'
    ].forEach((id) => {
      const el = UI.el(id);
      if (el) {
        el.addEventListener('input', () => Config.onConfigInputChanged());
        el.addEventListener('change', () => Config.onConfigInputChanged());
      }
    });

    const cfgArea = UI.el('cfg');
    if (cfgArea) {
      cfgArea.addEventListener('input', () => {
        if (Config._internalUpdating) return;
        Config.onConfigInputChanged();
      });
    }

    UI.setVal('adapterPath', state.adapterPath);
    UI.setVal('pfamPath', state.pfamPath);

    UI.bindClick('toggleAdapter', () => Config.toggleViewer('viewAdapter', '/opt/viir/resources/adapters.fasta'));
    UI.bindClick('togglePfam', () => Config.toggleViewer('viewPfam', '/opt/viir/resources/Pfam_IDs_list.txt'));
    Config.validateRequired();
    Config._applyOutPrefix(true);
    Config._setStateDirty("Fill parameters, then Generate → Save.");
  },

  // ===============================
  // 由 uploader.js 更新状态
  // ===============================
  updateFromUploaderState(up) {
    if (!up) return;
    // 自动设置到 input
    if (up.run_id) {
      UI.setVal('runId', up.run_id);
    }
    Config._applyOutPrefix(true);

    // 自动重新生成 YAML 预览
    this.generate();
  },

  // ===============================
  // 从页面读取所有参数
  // ===============================
  _readInputs() {
    // 确保输出目录有默认前缀
    Config._applyOutPrefix(false);
    return {
      threads: Number(UI.val('threads') || 16),
      pvalue: Number(UI.val('pval') || 0.01),
      out: UI.val('outDir').trim() || Config._buildOutPrefix(),
      ssType: UI.val('ssType'),
      maxMemory: UI.val('maxMem') || '64G'
    };
  },

  // ===============================
  // 生成 YAML 字符串
  // ===============================
  generate() {
    const p = this._readInputs();
    const st = state;

    if (!st.sample_list_path) {
      UI.toast("Sample list not ready", "error");
      return;
    }

    const adapterInput = UI.val('adapterPath').trim();
    const pfamInput = UI.val('pfamPath').trim();

    if (adapterInput) {
      state.adapterPath = adapterInput;
    }
    if (pfamInput) {
      state.pfamPath = pfamInput;
    }

    UI.setVal('adapterPath', state.adapterPath);
    UI.setVal('pfamPath', state.pfamPath);

    const yaml = [
      `out: ${p.out}`,
      `fastq-list: ${st.sample_list_path}`,
      `threads: ${p.threads}`,
      `adapter: ${state.adapterPath}`,
      `pfam: ${state.pfamPath}`,
      `hmm-folder: /opt/viir/resources/hmm_models`,
      `SS-lib-type: ${p.ssType}`,
      `blastndb: /opt/viir/resources/ViiR_DB`,
      `pvalue: ${p.pvalue}`,
      `max-memory: ${p.maxMemory}`
    ].join("\n");

    const pretty = yaml;

    const cfgArea = UI.el('cfg');
    if (cfgArea) {
      Config._internalUpdating = true;
      cfgArea.value = pretty;
      Config._internalUpdating = false;
    } else {
      UI.setText('cfg', pretty);
    }
    Config._setStateGenerated();
    return pretty;
  },

  onConfigInputChanged() {
    Config._setStateDirty("Parameters changed. Please generate config again.");
  },


  
  // ===============================
  // 保存 YAML 到后台
  // ===============================
  async save() {
    try {
      UI.busy('btnSaveCfg', true, 'Saving...');

      const cfgArea = UI.el('cfg');
      const yml = cfgArea?.value.trim();
      if (!yml) {
        throw new Error("Config content is empty");
      }
      if (!Config._isYamlValid(yml)) {
        throw new Error("Config YAML looks invalid");
      }
      const suffix = Config._buildSuffix();

      const result = await API.saveConfig(yml, suffix, true);

      UI.toast(`Config saved: ${result.path}`, "success");
      Config._setStateSaved(`Config saved. You can proceed to Step 3. Path: ${result.path}`);
      if (cfgArea) {
        cfgArea.classList.remove('flash');
        void cfgArea.offsetWidth; // force reflow
        cfgArea.classList.add('flash');
      }

    } catch (err) {
      UI.toast(err.message, "error");
    }

    UI.busy('btnSaveCfg', false);
    Config._updateSaveButton();
  },

  validateRequired() {
    document.querySelectorAll('.form-row[data-required="true"]').forEach(row => {
      const input = row.querySelector('input, select');
      if (!input) return;
      const empty = !(input.value && input.value.toString().trim());
      if (empty) {
        input.classList.add('required-empty');
        row.classList.add('required-empty');
      } else {
        input.classList.remove('required-empty');
        row.classList.remove('required-empty');
      }
    });
  },

  async toggleViewer(preId, path) {
    const pre = UI.el(preId);
    if (!pre) return;
    const showing = pre.style.display !== 'none' && pre.style.display !== '';
    if (showing) {
      pre.style.display = 'none';
      return;
    }
    pre.textContent = "Loading...";
    pre.style.display = 'block';
    pre.scrollTop = 0;
    try {
      const txt = await API.readFile(path);
      pre.textContent = txt.slice(0, 10000) + (txt.length > 10000 ? "\n..." : "");
    } catch (err) {
      pre.textContent = `⚠️ Unable to load ${path}: ${err.message}`;
    }
  },

  goToReview() {
    Wizard.markDone(2);
    Wizard.enable(3);
    Wizard.setActive(3);
    Wizard.disableFrom(4);
    Config._toggleNext(false);
    Review.refresh();
  },

  _toggleNext(show) {
    UI.toggle('btnNextStep3', !!show);
  },
  _updateSaveButton() {
    const cfgArea = UI.el('cfg');
    const txt = cfgArea?.value.trim() || "";
    const ok = Config.generated && Config._isYamlValid(txt);
    UI.setDisabled('btnSaveCfg', !ok);
  },

  _setStatus(msg) {
    UI.setText('cfgStatus', msg || '');
  },

  _setStateDirty(msg) {
    Config.generated = false;
    Config.saved = false;
    state.configSaved = false;
    Wizard.setDone(2, false);
    Wizard.enable(2);
    Wizard.setActive(2);
    Wizard.disableFrom(3);
    resetReviewConfirmation();
    Config.validateRequired();
    updateRunButtonState();
    Config._toggleNext(false);
    Config._setStatus(msg || "Parameters changed. Please generate config again.");
    Config._updateSaveButton();
  },

  _setStateGenerated() {
    Config.generated = true;
    Config.saved = false;
    state.configSaved = false;
    Config.validateRequired();
    Config._toggleNext(false);
    Config._setStatus("Config generated (not yet saved).");
    Config._updateSaveButton();
  },

  _setStateSaved(msg) {
    Config.generated = true;
    Config.saved = true;
    state.configSaved = true;
    Wizard.markDone(2);
    Wizard.enable(3);
    Wizard.disableFrom(4);
    Config._toggleNext(true);
    Review.refresh();
    window.scrollTo({ top: 0, behavior: 'smooth' });
    resetReviewConfirmation();
    updateRunButtonState();
    Config._setStatus(msg || "Config saved. You can proceed to Step 3.");
  },

  _isYamlValid(txt) {
    if (!txt) return false;
    return /^\s*\w[\w_-]*\s*:/m.test(txt);
  },

  _buildSuffix() {
    const ts = new Date();
    const y = ts.getFullYear();
    const m = String(ts.getMonth() + 1).padStart(2, '0');
    const d = String(ts.getDate()).padStart(2, '0');
    const hh = String(ts.getHours()).padStart(2, '0');
    const mm = String(ts.getMinutes()).padStart(2, '0');
    const ss = String(ts.getSeconds()).padStart(2, '0');
    const stamp = `${y}${m}${d}-${hh}${mm}${ss}`;

    const baseInput = this.templateBase || UI.val('runId').trim() || state.run_id || 'config';
    const base = Config._sanitize(baseInput) || "config";
    return `${base}_${stamp}`;
  },

  _sanitize(name) {
    return (name || "").replace(/[^A-Za-z0-9_-]+/g, "_").slice(0, 80);
  },

  _buildOutPrefix() {
    const ts = new Date();
    const y = ts.getFullYear();
    const m = String(ts.getMonth() + 1).padStart(2, '0');
    const d = String(ts.getDate()).padStart(2, '0');
    const hh = String(ts.getHours()).padStart(2, '0');
    const mm = String(ts.getMinutes()).padStart(2, '0');
    return `viir_run_${y}${m}${d}-${hh}${mm}`;
  },

  _applyOutPrefix(force) {
    const current = UI.val('outDir').trim();
    if (!current || force) {
      const prefix = Config._buildOutPrefix();
      UI.setVal('outDir', prefix);
    }
  }
};
