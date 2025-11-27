// =====================================
// wizard.js
// 控制四步向导的状态、激活与禁用
// =====================================

const Wizard = {
  steps: [],
  current: 1,
  onStepChange: null,

  init(onStepChange) {
    this.onStepChange = typeof onStepChange === "function" ? onStepChange : null;
    this.steps = Array.from(document.querySelectorAll(".wizard-step-item")).map((item) => {
      const step = Number(item.dataset.step);
      const panel = document.getElementById(`wizard-step${step}`);
      item.addEventListener("click", () => {
        if (item.classList.contains("disabled")) return;
        this.setActive(step);
      });
      return { step, item, panel, disabled: false };
    }).sort((a, b) => a.step - b.step);

    if (!this.steps.length) return;

    this.setActive(1);
    this.disableFrom(2);
  },

  setActive(step) {
    const target = this.steps.find((s) => s.step === step);
    if (!target || target.disabled) return;

    this.steps.forEach(({ item, panel }) => {
      item.classList.remove("active");
      panel?.classList.remove("active");
    });

    target.item.classList.add("active");
    target.panel?.classList.add("active");
    this.current = step;

    this.steps.forEach((s) => {
      if (s.step < step) {
        this.setDone(s.step, true);
        this.setDisabled(s.step, false);
      } else if (s.step > step) {
        this.setDone(s.step, false);
        this.setDisabled(s.step, true);
      } else {
        this.setDisabled(s.step, false);
      }
    });

    if (this.onStepChange) this.onStepChange(step);
  },

  setDone(step, flag = true) {
    const target = this.steps.find((s) => s.step === step);
    if (!target) return;
    target.item.classList.toggle("done", flag);
  },

  markDone(step) {
    this.setDone(step, true);
  },

  setDisabled(step, flag = true) {
    const target = this.steps.find((s) => s.step === step);
    if (!target) return;
    target.disabled = flag;
    target.item.classList.toggle("disabled", flag);
    if (flag) {
      target.item.classList.remove("active");
      target.panel?.classList.remove("active");
      if (this.current === step) {
        const prev = [...this.steps]
          .filter((s) => !s.disabled && s.step < step)
          .pop();
        if (prev) this.setActive(prev.step);
      }
    }
  },

  enable(step) {
    this.setDisabled(step, false);
  },

  disableFrom(step) {
    this.steps.forEach((entry) => {
      if (entry.step >= step) {
        this.setDone(entry.step, false);
        this.setDisabled(entry.step, true);
      }
    });
  }
};

export { Wizard };
