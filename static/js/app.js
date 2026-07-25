document.addEventListener("DOMContentLoaded", () => {
  bindDatePresets();
  bindLiveFilters();
  bindAllocationControls(document);
  bindDynamicRows();
  bindReceiptTotal();
  bindMarketComboboxes();
  bindRowActions(document);
  bindConfirmForms();
  bindCopyButtons();
  bindFactorTooltips();
  bindAvatarUploads();
  bindAvatarChoices();
  bindAvatarDialogs();
  bindCharts();
  bindCategoryAssignmentPage();
  bindFormActionStates();
});
document.addEventListener("click", (event) => {
  const row = event.target.closest(".receipt-item-row[data-href]");
  if (!row || event.target.closest("a, button, input, select, textarea")) return;
  window.location.href = row.dataset.href;
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const row = event.target.closest(".receipt-item-row[data-href]");
  if (!row) return;
  event.preventDefault();
  window.location.href = row.dataset.href;
});
