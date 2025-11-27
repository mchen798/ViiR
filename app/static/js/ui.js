// =====================================
// ui.js
// 负责：所有 DOM 操作、按钮忙碌状态、Toast 提示
// =====================================
export const UI = {

  // 获取元素
  el(id) {
    return document.getElementById(id);
  },

  // 绑定点击事件
  bindClick(id, fn) {
    const el = UI.el(id);
    if (el) el.addEventListener('click', fn);
  },

  // 绑定 change 事件
  bindChange(id, fn) {
    const el = UI.el(id);
    if (el) el.addEventListener('change', fn);
  },

  // 获取输入值
  val(id) {
    const el = UI.el(id);
    return el?.value ?? '';
  },

  // 设置输入值
  setVal(id, v) {
    const el = UI.el(id);
    if (el) el.value = v;
  },

  // 设置文本
  setText(id, txt) {
    const el = UI.el(id);
    if (el) el.textContent = txt;
  },

  // 触发隐藏的文件 input
  triggerFile(id) {
    const el = UI.el(id);
    if (el) el.click();
  },

  // 显示 / 隐藏元素
  toggle(id, show = true) {
    const el = UI.el(id);
    if (el) el.style.display = show ? "" : "none";
  },

  // 按钮忙碌状态
  busy(id, yes, txtGo = "Working...", txtIdle = null) {
    const btn = UI.el(id);
    if (!btn) return;

    btn.disabled = !!yes;

    if (yes) {
      btn.dataset.oldText = btn.textContent;
      btn.textContent = txtGo;
    } else {
      btn.textContent = txtIdle || btn.dataset.oldText || btn.textContent;
    }
  },
  setDisabled(id, yes) {
    const el = UI.el(id);
    if (el) el.disabled = yes;
  },


  // 统一的 Toast 提示（右上角悬浮）
  toast(msg, type = "info") {
    const div = document.createElement("div");
    div.className = `toast toast-${type}`;
    div.textContent = msg;

    document.body.appendChild(div);

    // 动画显示
    setTimeout(() => div.classList.add('show'), 10);

    // 自动隐藏
    setTimeout(() => {
      div.classList.remove('show');
      setTimeout(() => div.remove(), 400);
    }, 3000);
  }

};
