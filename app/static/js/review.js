


// const VERSION = '20251128';
import { UI } from './ui.js?v=20251128';
import { API } from './api.js?v=20251128';
import { state } from './state.js?v=20251128';
import { updateRunButtonState } from './runner.js?v=20251128';
import { Wizard } from './wizard.js?v=20251128';

export const Review = {

  init() {
    UI.bindClick("btnConfirmRun", () => Review.confirm());
  },

  async refresh() {

    // Sample list
    if (state.sample_list_path) {
      try {
        const s = await API.readFile(state.sample_list_path);
        UI.setText("reviewSample", s.slice(0, 5000));
        UI.setText("reviewSampleWarn", "");
      } catch (_) {
        UI.setText("reviewSample", "(Unable to load sample_list)");
        UI.setText("reviewSampleWarn", "⚠️");
      }
    } else {
      UI.setText("reviewSample", "(No sample_list)");
      UI.setText("reviewSampleWarn", "⚠️");
    }

    // Config
    const cfgTxt = UI.val("cfg");
    UI.setText("reviewConfig", cfgTxt || "(empty)");
    UI.setText("reviewConfigWarn", cfgTxt ? "" : "⚠️");

    // Pfam & Adapters
    try {
      const pf = await API.readFile(state.pfamPath || UI.val('pfamPath'));
      UI.setText("reviewPfam", pf.slice(0, 4000));
    } catch {
      UI.setText("reviewPfam", "(Unable to load pfam list)");
    }
    try {
      const ad = await API.readFile(state.adapterPath || UI.val('adapterPath'));
      UI.setText("reviewAdapter", ad.slice(0, 4000));
    } catch {
      UI.setText("reviewAdapter", "(Unable to load adapters)");
    }

    // Key Values
    UI.setText("reviewOut", UI.val("outDir"));
    UI.setText("reviewThreads", UI.val("threads"));
    UI.setText("reviewPval", UI.val("pval"));
    UI.setText("reviewLibtype", UI.val("ssType"));
    UI.setText("reviewMem", UI.val("maxMem"));
  },

  confirm() {
    if (!state.sample_list_path) {
      UI.toast("Sample list missing", "error");
      return;
    }

    const cfg = UI.val("cfg").trim();
    if (!cfg) {
      UI.toast("Config is empty", "error");
      return;
    }

    state.reviewConfirmed = true;
    Wizard.markDone(3);
    Wizard.enable(4);
    Wizard.setActive(4);
    UI.toast("Configuration confirmed. You may now run the pipeline.", "success");
    updateRunButtonState();
  }
};
