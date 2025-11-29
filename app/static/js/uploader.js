// =====================================
// uploader.js
// 负责：N / V 文件选择 + 上传 + sample_list 构建 + 预览
// =====================================

// const VERSION = '20251128';
import { API } from '/static/js/api.js?v=20251128';
import { UI } from '/static/js/ui.js?v=20251128';
import { Config } from '/static/js/config.js?v=20251128';
import { state, resetReviewConfirmation } from '/static/js/state.js?v=20251128';
import { updateRunButtonState } from '/static/js/runner.js?v=20251128';
import { Wizard } from '/static/js/wizard.js?v=20251128';

export const Uploader = {

  internal: {
    run_id: "",
    sample_list_path: "",
    mode: "new",
    groups: {
      N: { files: [], uploaded: false, status: "N group upload: not started" },
      V: { files: [], uploaded: false, status: "V group upload: not started" },
    }
  },
  usageTimer: null,

  // 初始化（在 app.js 调用）
  init() {
    console.log("[Web-ViiR] Uploader.init");
    // 模式切换
    document.querySelectorAll('input[name="datasetMode"]').forEach(r => {
      r.addEventListener('change', (e) => Uploader.switchMode(e.target.value));
    });

    // 绑定 Pick 按钮
    UI.bindClick('pickN', () => UI.triggerFile('fileN'));
    UI.bindClick('pickV', () => UI.triggerFile('fileV'));

    // Drag & Drop
    Uploader._initDropZone('dropN', 'N', 'fileN');
    Uploader._initDropZone('dropV', 'V', 'fileV');

    // 上传按钮
    UI.bindClick('uploadN', () => Uploader.uploadGroup('N'));
    UI.bindClick('uploadV', () => Uploader.uploadGroup('V'));

    // 文件选择预览
    UI.bindChange('fileN', (e) => Uploader.onFilesSelected('N', e.target.files));
    UI.bindChange('fileV', (e) => Uploader.onFilesSelected('V', e.target.files));

    // 构建 sample_list
    UI.bindClick('btnBuildList', () => Uploader.buildSampleList());

    // 预览
    UI.bindClick('toggleSamplePreview', () => Uploader.previewSampleList());

    // 现有数据集
    UI.bindClick('btnLoadExisting', () => Uploader.loadExistingDataset());

    // 跳转配置
    UI.bindClick('btnGoConfig', () => Uploader.goToConfig());

    Uploader.switchMode("new");
    Uploader.refreshExistingList();
    Uploader._updateBuildButton();
    console.log("Uploader.init() ready");
  },

  switchMode(mode) {
    this.internal.mode = mode;
    UI.toggle('panel-new-dataset', mode === "new");
    UI.toggle('panel-existing-dataset', mode === "existing");
    Uploader._updateBuildButton();
    console.log("[Uploader] switchMode", mode);
  },

  // ===============================
  // 文件选择
  // ===============================
  onFilesSelected(group, files) {
    const boxId = group === "N" ? "filesN" : "filesV";
    const box = document.getElementById(boxId);
    const names = [...files].map(f => f.name);
    box.textContent = names.join(', ') || '(none)';
    this.internal.groups[group].files = [...files];
    this.internal.groups[group].uploaded = false;
    this._setStatus(group, `${group} group: ${names.length} file(s) ready to upload`, "info");
    this._suggestRunId(names);
    this._resetProgressUI(group);
    console.log("[Uploader] onFilesSelected", group, names);
  },

  // ===============================
  // 上传一个组（N 或 V）
  // ===============================
  async uploadGroup(group) {
    console.log("[Uploader] uploadGroup start", group);
    if (this.internal.mode !== "new") return;
    const info = this.internal.groups[group];
    if (!info.files.length) {
      UI.toast(`Please pick ${group} FASTQ first`, "error");
      return;
    }
    const batchInputId = group === "N" ? "batchN" : "batchV";
    const files = info.files;
    const batch = UI.val(batchInputId).trim() || group;
    const fd = new FormData();
    fd.append('group', group);
    fd.append('batch', batch);
    files.forEach(f => fd.append('files', f));

    const start = Date.now();
    this._setStatus(group, `${group} uploading...`, "info");
    this._log(`${group}: uploading ${files.length} file(s) to batch ${batch}`);
    try {
      const axiosInstance = window.axios;
      let resp;

      if (axiosInstance) {
        resp = await axiosInstance.post('/api/upload_fastq', fd, {
          onUploadProgress: (e) => {
            if (!e.total) return;
            const pct = ((e.loaded / e.total) * 100).toFixed(1);
            const dt = (Date.now() - start) / 1000;
            const speed = e.loaded / (dt || 1); // bytes/s
            const remaining = e.total - e.loaded;
            const eta = remaining / (speed || 1);
            Uploader._setUploadProgress(pct, e.loaded, e.total, speed, eta, group);
            Uploader._setStatus(group, `${group} uploading... ${pct}%`, "info");
          }
        });
      } else {
        resp = await new Promise((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          xhr.open('POST', '/api/upload_fastq');
          xhr.upload.onprogress = (e) => {
            if (!e.lengthComputable) return;
            const pct = ((e.loaded / e.total) * 100).toFixed(1);
            const dt = (Date.now() - start) / 1000;
            const speed = e.loaded / (dt || 1);
            const remaining = e.total - e.loaded;
            const eta = remaining / (speed || 1);
            Uploader._setUploadProgress(pct, e.loaded, e.total, speed, eta, group);
            Uploader._setStatus(group, `${group} uploading... ${pct}%`, "info");
          };
          xhr.onerror = () => reject(new Error("Upload failed (network error)"));
          xhr.onreadystatechange = () => {
            if (xhr.readyState === XMLHttpRequest.DONE) {
              if (xhr.status >= 200 && xhr.status < 300) {
                try {
                  const data = JSON.parse(xhr.responseText || '{}');
                  resolve({ data });
                } catch (e) {
                  reject(new Error("Upload succeeded but response invalid"));
                }
              } else {
                const msg = xhr.responseText || `HTTP ${xhr.status}`;
                reject(new Error(msg));
              }
            }
          };
          xhr.send(fd);
        });
      }

      this.internal.groups[group].uploaded = true;
      state.uploadDone = this.internal.groups.N.uploaded && this.internal.groups.V.uploaded;
      const uploadDir = resp?.data?.dir || '';
      this._setStatus(group, `${group} upload finished → ${uploadDir}`, "success");
      UI.setDisabled(`pick${group}`, true);
      this._log(`${group}: uploaded to ${uploadDir}`);
      this._updateBuildButton();
    } catch (err) {
      console.error("[Uploader] uploadGroup error", err);
      this._setStatus(group, `${group} upload failed: ${err.message}`, "error");
      this._setUploadProgress(0,0,0,0,0,group);
    }
  },


  // ===============================
  // 主流程：上传 N/V + 构建 sample_list
  // ===============================
  async buildSampleList() {
    console.log("[Uploader] buildSampleList start");
    if (this.internal.mode === "existing") {
      UI.toast("Load existing dataset and go to configuration.", "info");
      return;
    }

    if (!state.uploadDone) {
      UI.toast("Please upload FASTQ first", "error");
      return;
    }

    const rid = UI.val('runId').trim();
    if (!rid) {
      Uploader._suggestRunId([]);
    }

    UI.busy('btnBuildList', true, 'Working...');
    Uploader._showPrepareIndicator(true);
    Uploader._startUsagePolling();

    try {
      // 1. 获取当前批次
      const N = UI.val('batchN').trim() || "N";
      const V = UI.val('batchV').trim() || "V";

      // 3. 请求后台 prepare_fastq
      const resp = await API.prepareFastq(N, V);

      this.internal.sample_list_path = resp.sample_list;
      this.internal.run_id = resp.run_id;
      state.sample_list_path = resp.sample_list;
      state.run_id = resp.run_id;
      resetReviewConfirmation();
      UI.setVal('runId', resp.run_id);

      // 4. sample_list.txt 预览
      let preview = "(preview unavailable)";
      try {
        preview = await API.readFile(resp.sample_list);
      } catch (e) {
        preview = "(cannot read preview)";
      }

      UI.setText('samplePreview', preview);
      const pre = document.getElementById('samplePreview');
      if (pre) pre.style.display = 'block';
      const toggle = document.getElementById('toggleSamplePreview');
      if (toggle) toggle.textContent = "Hide sample list preview";

      // 5. 触发 Config 自动更新
      Config.updateFromUploaderState({ run_id: resp.run_id, sample_list_path: resp.sample_list });

      UI.toast("Sample list created");
      UI.setText('prepareStatus', `Finished! sample_list: ${resp.sample_list}`);
      this._updateBuildButton();

    } catch (err) {
      console.error("[Uploader] buildSampleList error", err);
      UI.toast(err.message, "error");
    } finally {
      Uploader._showPrepareIndicator(false);
      Uploader._stopUsagePolling();
      UI.busy('btnBuildList', false);
    }
  },

  _suggestRunId(fileNames) {
    const current = UI.val('runId').trim();
    if (current) return;
    const ts = new Date();
    const y = ts.getFullYear();
    const m = String(ts.getMonth() + 1).padStart(2, '0');
    const d = String(ts.getDate()).padStart(2, '0');
    const stamp = `${y}${m}${d}`; // date-first for easy sorting

    let base = (fileNames && fileNames[0]) ? fileNames[0].replace(/\.(fq|fastq)(\.gz)?$/i,'') : "task";
    base = base.replace(/[^A-Za-z0-9_-]+/g, '_').slice(0,40) || "task";
    UI.setVal('runId', `${stamp}_${base}`);
  },

  _setUploadProgress(pct, loaded, total, speed, eta, group) {
    const bar = document.getElementById(`uploadProg${group}`);
    const wrap = document.getElementById(`uploadProgBar${group}`);
    const text = document.getElementById(`uploadProgText${group}`);
    if (wrap) wrap.style.display = 'block';
    if (bar) bar.style.width = `${Math.min(100, pct)}%`;

    if (text) {
      if (pct >= 100) {
        text.textContent = `${group || ''} Upload completed ✔`;
      } else {
        const mbLoaded = (loaded/1024/1024).toFixed(1);
        const mbTotal = (total/1024/1024).toFixed(1);
        const speedMb = (speed/1024/1024).toFixed(2);
        const etaSec = Math.max(0, eta || 0);
        text.textContent = `${pct}% • ${mbLoaded}/${mbTotal} MiB • ${speedMb} MiB/s • ETA ${etaSec.toFixed(1)}s`;
      }
    }
  },

  _resetProgressUI(group) {
    const bar = document.getElementById(`uploadProg${group || ''}`);
    const wrap = document.getElementById(`uploadProgBar${group || ''}`);
    const text = document.getElementById(`uploadProgText${group || ''}`);
    if (bar) bar.style.width = '0%';
    if (wrap) wrap.style.display = 'none';
    if (text) text.textContent = '';
    Uploader._updateBuildButton();
  },

  _showPrepareIndicator(show) {
    const bar = document.getElementById('prepareProgBar');
    const status = document.getElementById('prepareStatus');
    if (status) status.textContent = show ? "Preparing sample_list..." : "";
    if (bar) bar.style.display = show ? 'block' : 'none';
  },

  _startUsagePolling() {
    if (this.usageTimer) return;
    this.usageTimer = setInterval(async () => {
      try {
        const u = await API.usage();
        UI.setText('prepareUsage', `CPU ${u.cpu}% • MEM ${u.mem}%`);
      } catch { /* ignore */ }
    }, 1000);
  },

  _stopUsagePolling() {
    if (this.usageTimer) {
      clearInterval(this.usageTimer);
      this.usageTimer = null;
    }
    UI.setText('prepareUsage', '');
  },

  previewSampleList() {
    const pre = document.getElementById('samplePreview');
    const toggle = document.getElementById('toggleSamplePreview');
    if (!pre || !toggle) return;
    if (!state.sample_list_path && !this.internal.sample_list_path) {
      UI.toast("No sample_list available yet", "error");
      return;
    }
    const show = pre.style.display === 'none' || pre.style.display === '';
    if (show) {
      const path = state.sample_list_path || this.internal.sample_list_path;
      API.readFile(path).then(txt => {
        pre.textContent = txt;
        pre.style.display = 'block';
        toggle.textContent = "Hide sample list preview";
      }).catch(() => {
        pre.textContent = "(cannot read sample_list)";
        pre.style.display = 'block';
      });
    } else {
      pre.style.display = 'none';
      toggle.textContent = "Show sample list preview";
    }
  },

  goToConfig() {
    console.log("[Uploader] goToConfig");
    const rid = UI.val('runId').trim();
    const sl = state.sample_list_path || this.internal.sample_list_path;
    if (!rid || !sl) {
      UI.toast("run_id or sample_list missing", "error");
      return;
    }
    state.run_id = rid;
    state.sample_list_path = sl;
    resetReviewConfirmation();
    Config.updateFromUploaderState({ run_id: rid, sample_list_path: sl });
    Wizard.markDone(1);
    Wizard.enable(2);
    Wizard.setDone(2, false);
    Wizard.setActive(2);
    Wizard.disableFrom(3);
    updateRunButtonState();
    UI.toast("Step 1 completed. Proceed to configuration.", "success");
  },

  async refreshExistingList() {
    try {
      const list = await API._json('/list_sample_lists');
      const sel = document.getElementById('existingRunSelect');
      if (!sel) return;
      sel.innerHTML = list.map(item => `<option value="${item.sample_list_path}" data-run="${item.run_id}">${item.run_id}</option>`).join('');
    } catch {
      /* ignore */
    }
  },

  async loadExistingDataset() {
    console.log("[Uploader] loadExistingDataset");
    this.switchMode("existing");
    const sel = document.getElementById('existingRunSelect');
    if (!sel || !sel.value) {
      UI.toast("No dataset selected", "error");
      return;
    }
    const runId = sel.selectedOptions[0]?.dataset.run || "";
    const path = sel.value;
    state.run_id = runId;
    state.sample_list_path = path;
    this.internal.run_id = runId;
    this.internal.sample_list_path = path;
    resetReviewConfirmation();
    UI.setText('existingStatus', `Loaded dataset: ${runId}`);
    UI.setVal('runId', runId);
    this._updateBuildButton();
  },

  _setStatus(group, text, type="info") {
    const el = document.getElementById(group === "N" ? "statusN" : "statusV");
    if (!el) return;
    el.textContent = text;
    el.className = `small status-text ${type}`;
  },

  _updateBuildButton() {
    const enabledNew = (this.internal.groups.N.uploaded && this.internal.groups.V.uploaded) && this.internal.mode === "new";
    const enabledExisting = (!!state.sample_list_path || !!this.internal.sample_list_path) && this.internal.mode === "existing";
    UI.setDisabled('btnBuildList', !enabledNew);
    UI.setDisabled('btnGoConfig', !(enabledNew || enabledExisting));
  },

  _log(msg) {
    const box = document.getElementById('uploadLog');
    if (!box) return;
    const now = new Date();
    const stamp = now.toLocaleTimeString();
    if (box.textContent === '(no uploads yet)') box.textContent = '';
    box.textContent += `[${stamp}] ${msg}\n`;
    box.scrollTop = box.scrollHeight;
  },

  _initDropZone(zoneId, group, inputId) {
    const zone = document.getElementById(zoneId);
    const input = document.getElementById(inputId);
    if (!zone || !input) return;
    const prevent = (e) => { e.preventDefault(); e.stopPropagation(); };
    ['dragenter','dragover','dragleave','drop'].forEach(ev => {
      zone.addEventListener(ev, prevent);
    });
    ['dragenter','dragover'].forEach(ev => zone.addEventListener(ev, () => zone.classList.add('dragover')));
    ['dragleave','drop'].forEach(ev => zone.addEventListener(ev, () => zone.classList.remove('dragover')));
    zone.addEventListener('click', () => input.click());
    zone.addEventListener('drop', (e) => {
      const files = e.dataTransfer?.files;
      if (!files?.length) return;
      Uploader.onFilesSelected(group, files);
    });
  }
};
