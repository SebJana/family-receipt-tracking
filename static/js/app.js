document.addEventListener("DOMContentLoaded", () => {
  bindPersistedFilters();
  bindDatePresets();
  bindLiveFilters();
  bindAllocationControls(document);
  bindDynamicRows();
  bindReceiptActionLocations();
  bindReceiptTotal();
  bindMarketComboboxes();
  bindRowActions(document);
  bindConfirmForms();
  bindPromptBuyerSelectors();
  bindCopyButtons();
  bindFactorTooltips();
  bindAvatarUploads();
  bindAvatarChoices();
  bindAvatarDialogs();
  bindCharts();
  bindCategoryAssignmentPage();
  bindSearchClearFields();
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

document.addEventListener("livefilter:update", (event) => {
  bindConfirmForms(event.target);
  bindSearchClearFields(event.target);
  bindFormActionStates(event.target);
});
