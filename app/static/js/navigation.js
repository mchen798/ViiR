// ===========================
// navigation.js
// 控制首页 / Wizard / Run Panel
// ===========================
export const Nav = {

  // 当前激活的页面
  current: 'home',

  // 所有页面 ID
  pages: ['home', 'wizard', 'run'],

  // 初始化（在 app.js 里调用）
  init() {
    // 绑定所有菜单按钮
    document.querySelectorAll('.nav-btn[data-target]').forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.dataset.target;
        Nav.go(target);
      });
    });

    // 默认加载首页
    Nav.go('home');
  },

  // 切换页面
  go(page) {
    if (!Nav.pages.includes(page)) {
      console.warn(`Unknown page: ${page}`);
      return;
    }

    // 隐藏所有页面
    Nav.pages.forEach(p => {
      const sec = document.getElementById(`page-${p}`);
      if (sec) sec.classList.remove('active');
    });

    // 显示目标页面
    const tgt = document.getElementById(`page-${page}`);
    if (tgt) tgt.classList.add('active');

    Nav.current = page;

    // 更新导航按钮样式
    Nav.updateNavUI();

    // 滚动到顶部
    window.scrollTo({ top: 0, behavior: "smooth" });
  },

  // 高亮当前导航按钮
  updateNavUI() {
    document.querySelectorAll('.nav-btn[data-target]').forEach(btn => {
      const tgt = btn.dataset.target;
      if (tgt === Nav.current) {
        btn.classList.add('nav-active');
      } else {
        btn.classList.remove('nav-active');
      }
    });
  }
};
