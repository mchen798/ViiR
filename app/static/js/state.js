// =====================================
// state.js
// 维护全局运行状态，供各模块共享
// =====================================

export const state = {
  sample_list_path: "",
  run_id: "",
  reviewConfirmed: false,
  adapterPath: "/opt/viir/resources/adapters.fasta",
  pfamPath: "/opt/viir/resources/Pfam_IDs_list.txt"
};

export function resetReviewConfirmation() {
  state.reviewConfirmed = false;
}
