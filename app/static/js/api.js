// =========================
// api.js  统一封装所有后台 API
// =========================
export const API = {

  // ---- 通用 fetch 封装 ----
  async _json(url, method = 'GET', body = null) {
    const opt = { method, headers: {} };
    if (body) {
      opt.headers['Content-Type'] = 'application/json';
      opt.body = JSON.stringify(body);
    }
    const r = await fetch(url, opt);
    const t = await r.text();
    let j = null;
    try { j = JSON.parse(t); } catch { /* text only */ }

    if (!r.ok) {
      throw new Error(j?.detail || t || `HTTP ${r.status}`);
    }
    return j ?? t;
  },

  async _text(url) {
    const r = await fetch(url);
    const t = await r.text();
    if (!r.ok) throw new Error(t || `HTTP ${r.status}`);
    return t;
  },

  // =====================================
  // 1. Status / Logs / Results
  // =====================================

  getStatus() {
    return this._json('/status');
  },

  getLogs(tail = 200) {
    return this._text(`/logs?tail=${tail}`);
  },

  listResults() {
    return this._json('/results');
  },

  listRuns() {
    return this._json('/list_runs');
  },

  // =====================================
  // 2. Uploading FASTQ Groups (N / V)
  // =====================================


  async stop() {
    const r = await fetch("/stop", { method: "POST" });
    return r.json();
  },

  // ========== Resource Usage ==========
  async usage() {
    const r = await fetch('/usage');
    if (!r.ok) throw new Error("usage failed");
    return await r.json();
  },


  async uploadFastq(group, batch, files) {
    const fd = new FormData();
    fd.append('group', group);
    fd.append('batch', batch);
    for (const f of files) fd.append('files', f);

    const r = await fetch('/api/upload_fastq', { method: 'POST', body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || 'upload failed');
    return j;
  },

  // =====================================
  // 3. sample_list.txt 构建与预览
  // =====================================

  prepareFastq(N, V) {
    return this._json('/prepare_fastq', 'POST', { N, V });
  },

  readFile(path) {
    return this._text('/read_file?path=' + encodeURIComponent(path));
  },

  // =====================================
  // 4. Config 相关
  // =====================================

  saveConfig(yml, suffix, activate = true) {
    return this._json('/save_config', 'POST', { yml, suffix, activate });
  },

  // =====================================
  // 5. Running the pipeline
  // =====================================

  runActive() {
    return this._json('/run_active', 'POST');
  },



  // =====================================
  // 6. Download 成品文件
  // =====================================

  download(preset, format) {
    // 使用 location.href 触发浏览器下载
    const u = `/download2?preset=${encodeURIComponent(preset)}&format=${encodeURIComponent(format)}&strategy=file`;
    window.location.href = u;
  }
};
