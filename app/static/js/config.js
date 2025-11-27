// =====================================
// config.js
// 负责：config.yaml 的生成、编辑、保存
// =====================================

import { UI } from './ui.js';
import { API } from './api.js';
import { state, resetReviewConfirmation } from './state.js';
import { updateRunButtonState } from './runner.js';
import { Wizard } from './wizard.js';

export const Config = {

  // 初始化（app.js 中调用）
  init() {
    // Generate Preview 按钮
    UI.bindClick('btnGen', () => {    
      const yml = Config.generate();
      if (yml) {
        Config.onConfigInputChanged();
      }
      updateRunButtonState();
    });

    // Save Config 按钮
    UI.bindClick("btnSaveCfg", async () => {
      await Config.save();
      updateRunButtonState();
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
      cfgArea.addEventListener('input', () => Config.onConfigInputChanged());
    }

    UI.setVal('adapterPath', state.adapterPath);
    UI.setVal('pfamPath', state.pfamPath);

    UI.bindClick('toggleAdapter', () => Config.toggleViewer('viewAdapter', '/workspace/adapter.h'));
    UI.bindClick('togglePfam', () => Config.toggleViewer('viewPfam', '/workspace/pfam_list.txt'));
    Config.validateRequired();
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

    // 自动重新生成 YAML 预览
    const yml = this.generate();
    if (yml) {
      this.onConfigInputChanged();
    }
  },

  // ===============================
  // 从页面读取所有参数
  // ===============================
  _readInputs() {
    return {
      threads: Number(UI.val('threads') || 16),
      pvalue: Number(UI.val('pval') || 0.01),
      out: UI.val('outDir').trim() || 'viir_run_' + (state.run_id || '1'),
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
      `out: /workspace/${p.out}`,
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

    const pretty = yaml.split("\n").map(l => l ? `  ${l}` : l).join("\n");

    const cfgArea = UI.el('cfg');
    if (cfgArea) {
      cfgArea.value = pretty;
    } else {
      UI.setText('cfg', pretty);
    }
    Config.validateRequired();
    return pretty;
  },

  onConfigInputChanged() {
    Wizard.setDone(2, false);
    Wizard.enable(2);
    Wizard.setActive(2);
    Wizard.disableFrom(3);
    resetReviewConfirmation();
    Config.validateRequired();
    updateRunButtonState();
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
      const suffix = state.run_id || Date.now().toString();

      const result = await API.saveConfig(yml, suffix, true);

      UI.toast(`Config saved: ${result.path}`, "success");
      Wizard.markDone(2);
      Wizard.enable(3);
      Wizard.setDone(3, false);
      Wizard.setActive(3);
      Wizard.disableFrom(4);
      resetReviewConfirmation();
      updateRunButtonState();
      if (cfgArea) {
        cfgArea.classList.remove('flash');
        void cfgArea.offsetWidth; // force reflow
        cfgArea.classList.add('flash');
      }

    } catch (err) {
      UI.toast(err.message, "error");
    }

    UI.busy('btnSaveCfg', false);
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
    const showing = pre.style.display !== 'none';
    if (showing) {
      pre.style.display = 'none';
      return;
    }
    pre.textContent = "Loading...";
    pre.style.display = 'block';
    try {
      const txt = await API.readFile(path);
      pre.textContent = txt.slice(0, 10000) + (txt.length > 10000 ? "\n..." : "");
    } catch (err) {
      pre.textContent = `⚠️ Unable to load ${path}: ${err.message}`;
    }
  }
};
