// =====================================
// app.js
// 整个 Web-ViiR 应用的入口模块
// =====================================

import { Nav } from './navigation.js';
import { Uploader } from './uploader.js';
import { Config } from './config.js';
import { Runner, updateRunButtonState } from './runner.js';
import { API } from './api.js';
import { UI } from './ui.js';
import { Review } from './review.js';
import { Wizard } from './wizard.js';


export const App = {

  async init() {

    // 1) 初始化页面导航
    Nav.init();

    // 2) 初始化各个模块
    Uploader.init();
    Config.init();
    Runner.init();
    Review.init();

    // 3) 检查系统健康状态
    await App.updateHealthStatus();

    // 4) 加载最近任务（如果后台支持）
    await App.loadRecent();

    App.initWizardSteps();


    // 5) 启动全局错误处理
    App.registerGlobalErrorHandler();

    UI.toast("Web-ViiR loaded", "info");
    updateRunButtonState();
  },

  // ==========================
  // 系统健康状态：初始化右上角 pill
  // ==========================
  async updateHealthStatus() {
    try {
      const st = await API.getStatus();
      const map = { idle: 'pending', running: 'inprog', finished: 'completed', failed: 'failed' };

      const pill = UI.el('pillHealth');
      if (pill) {
        pill.className = `pill status ${map[st.status] || 'pending'}`;
        pill.textContent = st.status;
      }

    } catch (err) {
      UI.toast("Health check error: " + err.message, "error");
    }
  },




  


  // ==========================
  // Recent runs (主页卡片)
  // ==========================
  async loadRecent() {
    const box = UI.el('recent');
    if (!box) return;

    try {
      const arr = await API.listRuns();

      box.innerHTML = arr.slice(0, 6).map(x => {
        const st = x.status || 'pending';
        const cls = {
          finished: 'completed',
          running: 'inprog',
          failed: 'failed'
        }[st] || 'pending';

        return `
        <div class="row recent-item">
          <span class="k">${x.run}</span>
          <span class="pill status ${cls}">${st}</span>
        </div>`;
      }).join('');

    } catch {
      box.innerHTML = `<div class="hint">Recent unavailable</div>`;
    }
  },

  // ==========================
  // 全局错误捕获
  // ==========================
  registerGlobalErrorHandler() {
    window.onerror = (msg, src, line, col, err) => {
      UI.toast("Error: " + (err?.message || msg), "error");
      return false;
    };

    window.addEventListener("unhandledrejection", (e) => {
      UI.toast("Promise error: " + e.reason, "error");
    });
  }
};

App.initWizardSteps = function() {
  Wizard.init((step) => {
    if (step === 3) {
      Review.refresh();
    } else if (step === 4) {
      updateRunButtonState();
    }
    Runner.updateRunningUI(Runner.lastStatus === 'running');
  });
};


// 启动应用
window.addEventListener('DOMContentLoaded', () => {
  App.init();
});
