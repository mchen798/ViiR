// =====================================
// uploader.js
// 负责：N / V 文件选择 + 上传 + sample_list 构建 + 预览
// =====================================

import { API } from './api.js';
import { UI } from './ui.js';
import { Config } from './config.js';
import { state, resetReviewConfirmation } from './state.js';
import { updateRunButtonState } from './runner.js';
import { Wizard } from './wizard.js';

export const Uploader = {

  // 保存状态
  state: {
    run_id: "",
    sample_list_path: "",
    Nbatch: "",
    Vbatch: ""
  },

  // 初始化（在 app.js 调用）
  init() {
    // 绑定 Pick 按钮
    UI.bindClick('pickN', () => UI.triggerFile('fileN'));
    UI.bindClick('pickV', () => UI.triggerFile('fileV'));

    // 文件选择预览
    UI.bindChange('fileN', (e) => Uploader._showPicked('filesN', e.target.files));
    UI.bindChange('fileV', (e) => Uploader._showPicked('filesV', e.target.files));

    // 构建 sample_list
    UI.bindClick('btnBuildList', () => Uploader.buildSampleList());
  },


  // ===============================
  // 文件列表预览
  // ===============================
  _showPicked(outputId, files) {
    const box = document.getElementById(outputId);
    box.textContent = [...files].map(f => f.name).join(', ') || '(none)';
  },


  // ===============================
  // 上传一个组（N 或 V）
  // ===============================
  async _uploadGroup(group, batch, fileInputId, displayId) {
    if (!batch) return; // 批次留空 = 跳过该组

    const input = document.getElementById(fileInputId);
    if (!input.files.length) return;

    const j = await API.uploadFastq(group, batch, input.files);

    const box = document.getElementById(displayId);
    box.textContent = `✓ Uploaded ${j.count} files → ${j.dir}`;

    return j;
  },


  // ===============================
  // 主流程：上传 N/V + 构建 sample_list
  // ===============================
  async buildSampleList() {
    UI.busy('btnBuildList', true, 'Working...');

    try {
      // 1. 获取当前批次
      this.state.Nbatch = UI.val('batchN');
      this.state.Vbatch = UI.val('batchV');

      const N = this.state.Nbatch?.trim();
      const V = this.state.Vbatch?.trim();

      // 2. 上传 N / V（如果有）
      await this._uploadGroup('N', N, 'fileN', 'filesN');
      await this._uploadGroup('V', V, 'fileV', 'filesV');

      // 3. 请求后台 prepare_fastq
      const resp = await API.prepareFastq(N, V);

      this.state.sample_list_path = resp.sample_list;
      this.state.run_id = resp.run_id;
      state.sample_list_path = resp.sample_list;
      state.run_id = resp.run_id;
      resetReviewConfirmation();
      UI.setVal('runId', resp.run_id);

      Wizard.markDone(1);
      Wizard.enable(2);
      Wizard.setDone(2, false);
      Wizard.setActive(2);
      Wizard.disableFrom(3);

      // ★ 触发：Run 按钮状态更新
      updateRunButtonState();
      
      // 4. sample_list.txt 预览
      let preview = "(preview unavailable)";
      try {
        preview = await API.readFile(resp.sample_list);
      } catch (e) {
        preview = "(cannot read preview)";
      }

      UI.setText('samplePreview', preview);

      // 5. 触发 Config 自动更新
      Config.updateFromUploaderState(this.state);

      UI.toast("Sample list created");

    } catch (err) {
      UI.toast(err.message, "error");
    }

    UI.busy('btnBuildList', false);
  }
};
