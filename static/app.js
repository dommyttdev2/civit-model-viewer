(() => {
  const catalogSyncButton = document.querySelector("#catalog-sync");
  const catalogOverlay = document.querySelector("#catalog-loading-overlay");
  const catalogProgress = document.querySelector("#catalog-progress");
  const catalogProgressPhase = document.querySelector("#catalog-progress-phase");
  const catalogProgressCount = document.querySelector("#catalog-progress-count");
  const catalogProgressPercent = document.querySelector("#catalog-progress-percent");
  const catalogProgressMessage = document.querySelector("#catalog-progress-message");
  const catalogProgressError = document.querySelector("#catalog-progress-error");
  const catalogProgressActions = document.querySelector("#catalog-progress-actions");
  const catalogSyncRetry = document.querySelector("#catalog-sync-retry");
  const catalogSyncDismiss = document.querySelector("#catalog-sync-dismiss");
  let catalogPollTimer = null;
  let catalogWasRunning = catalogOverlay?.dataset.initialState === "running";

  const showCatalogOverlay = () => {
    catalogOverlay.hidden = false;
    catalogSyncButton.disabled = true;
  };

  const hideCatalogOverlay = () => {
    catalogOverlay.hidden = true;
    catalogSyncButton.disabled = false;
  };

  const renderCatalogStatus = (status) => {
    const total = Math.max(Number(status.total) || 1, 1);
    const completed = Math.min(Math.max(Number(status.completed) || 0, 0), total);
    const percent = Math.round((completed / total) * 100);
    catalogProgress.max = total;
    catalogProgress.value = completed;
    catalogProgressPhase.textContent = status.phase || "準備中";
    catalogProgressCount.textContent = `${completed} / ${total}`;
    catalogProgressPercent.textContent = `${percent}%`;
    catalogProgressMessage.textContent = status.message || "モデル情報を確認しています…";
    catalogProgressError.hidden = !status.error;
    catalogProgressError.textContent = status.error || "";
    catalogProgressActions.hidden = status.state !== "error";
  };

  const pollCatalogStatus = async () => {
    window.clearTimeout(catalogPollTimer);
    try {
      const response = await fetch("/api/catalog/status", { cache: "no-store" });
      if (!response.ok) throw new Error("同期状態を取得できませんでした");
      const status = await response.json();
      renderCatalogStatus(status);
      if (status.state === "running") {
        catalogWasRunning = true;
        showCatalogOverlay();
        catalogPollTimer = window.setTimeout(pollCatalogStatus, 650);
      } else if (status.state === "ready") {
        hideCatalogOverlay();
        if (catalogWasRunning) window.location.reload();
      } else if (status.state === "error") {
        catalogWasRunning = false;
        showCatalogOverlay();
        catalogSyncButton.disabled = false;
      } else {
        hideCatalogOverlay();
      }
    } catch (error) {
      renderCatalogStatus({
        state: "error",
        phase: "接続エラー",
        completed: 0,
        total: 1,
        message: "同期状態を確認できませんでした",
        error: error.message,
      });
      showCatalogOverlay();
      catalogSyncButton.disabled = false;
    }
  };

  const startCatalogSync = async () => {
    catalogWasRunning = true;
    showCatalogOverlay();
    renderCatalogStatus({
      state: "running",
      phase: "準備中",
      completed: 0,
      total: 1,
      message: "Civitaiへ接続しています…",
      error: null,
    });
    try {
      const response = await fetch("/api/catalog/sync", { method: "POST" });
      const status = await response.json();
      if (!response.ok) throw new Error(status.error || "同期を開始できませんでした");
      renderCatalogStatus(status);
      pollCatalogStatus();
    } catch (error) {
      renderCatalogStatus({
        state: "error",
        phase: "同期失敗",
        completed: 0,
        total: 1,
        message: "同期を開始できませんでした",
        error: error.message,
      });
    }
  };

  catalogSyncButton?.addEventListener("click", startCatalogSync);
  catalogSyncRetry?.addEventListener("click", startCatalogSync);
  catalogSyncDismiss?.addEventListener("click", () => {
    catalogWasRunning = false;
    hideCatalogOverlay();
  });
  if (catalogOverlay && catalogSyncButton) pollCatalogStatus();

  const form = document.querySelector("#collection-form");
  if (!form) return;

  const collectionCheckboxes = [...document.querySelectorAll(".collection-checkbox")];
  const selectAllCollections = document.querySelector("#select-all");
  const clearAllCollections = document.querySelector("#clear-all");
  const collectionCount = document.querySelector("#selection-count");
  const collectionStatus = document.querySelector("#selection-status");
  const itemPickerContent = document.querySelector("#item-picker-content");
  const itemPickerEmpty = document.querySelector("#item-picker-empty");
  const itemGroups = document.querySelector("#item-groups");
  const itemTools = document.querySelector("#item-selection-tools");
  const selectAllItems = document.querySelector("#item-select-all");
  const clearAllItems = document.querySelector("#item-clear-all");
  const itemSearch = document.querySelector("#item-search");
  const itemSearchEmpty = document.querySelector("#item-search-empty");
  const globalSearchStatus = document.querySelector("#global-search-status");
  const itemCount = document.querySelector("#item-selection-count");
  const itemStatus = document.querySelector("#item-picker-status");
  const resultsContent = document.querySelector("#results-content");
  const emptyManifest = document.querySelector("#empty-manifest");
  const resultGroups = document.querySelector("#result-groups");
  const resultSummary = document.querySelector("#result-summary");
  const copyButton = document.querySelector("#copy-json");
  const toast = document.querySelector("#toast");
  const templateName = document.querySelector("#template-name");
  const templateSave = document.querySelector("#template-save");
  const templateList = document.querySelector("#template-list");
  const templateLoad = document.querySelector("#template-load");
  const templateDelete = document.querySelector("#template-delete");
  const templateStatus = document.querySelector("#template-status");
  let catalog = null;
  let globalCatalog = null;
  let globalSearchMode = false;
  let currentExport = null;
  let loadTimer = null;
  let searchTimer = null;
  let requestSerial = 0;
  const selectedItemKeys = new Set();
  const templateStorageKey = "civitai-collection-lens.selection-templates.v1";

  const selectedCollectionIds = () =>
    collectionCheckboxes
      .filter((checkbox) => checkbox.checked)
      .map((checkbox) => Number(checkbox.value));

  const allCollectionIds = () =>
    collectionCheckboxes.map((checkbox) => Number(checkbox.value));

  const itemKey = (collectionId, item) => `${collectionId}:${item.modelId}`;
  const itemCheckboxes = () => [...document.querySelectorAll(".item-checkbox")];
  const normalizeSearch = (value) =>
    String(value || "").normalize("NFKC").toLocaleLowerCase("ja");

  const searchableItemText = (item) => {
    const versions = Array.isArray(item.versions) && item.versions.length
      ? item.versions
      : [item];
    const fileNames = versions.flatMap((version) =>
      Array.isArray(version.files)
        ? version.files.map((file) => file.name || "")
        : []
    );
    return normalizeSearch([item.modelName, ...fileNames].join("\n"));
  };

  const applyVersionToItem = (item, versionId) => {
    const versions = Array.isArray(item.versions) && item.versions.length
      ? item.versions
      : [item];
    const selectedVersion = versions.find(
      (version) => String(version.versionId) === String(versionId)
    );
    if (!selectedVersion) return false;
    item.versionId = selectedVersion.versionId;
    item.versionName = selectedVersion.versionName;
    item.modelUrl = selectedVersion.modelUrl;
    item.thumbnailUrl = selectedVersion.thumbnailUrl;
    item.thumbnailWidth = selectedVersion.thumbnailWidth;
    item.thumbnailHeight = selectedVersion.thumbnailHeight;
    item.trainedWords = selectedVersion.trainedWords;
    item.files = selectedVersion.files;
    delete item.error;
    return true;
  };

  const readTemplates = () => {
    try {
      const stored = JSON.parse(window.localStorage.getItem(templateStorageKey) || "[]");
      return Array.isArray(stored) ? stored : [];
    } catch (_error) {
      return [];
    }
  };

  let selectionTemplates = readTemplates();

  const writeTemplates = () => {
    try {
      window.localStorage.setItem(templateStorageKey, JSON.stringify(selectionTemplates));
      return true;
    } catch (_error) {
      showToast("テンプレートをブラウザへ保存できませんでした", true);
      return false;
    }
  };

  const renderTemplateList = (selectedId = "") => {
    templateList.replaceChildren();
    if (!selectionTemplates.length) {
      const empty = element("option", null, "保存済みテンプレートなし");
      empty.value = "";
      templateList.append(empty);
    } else {
      selectionTemplates.forEach((template) => {
        const option = element("option", null, template.name);
        option.value = template.id;
        templateList.append(option);
      });
      templateList.value = selectionTemplates.some(
        (template) => template.id === selectedId
      )
        ? selectedId
        : selectionTemplates[0].id;
    }
    const hasTemplate = Boolean(templateList.value);
    templateLoad.disabled = !hasTemplate;
    templateDelete.disabled = !hasTemplate;
    templateStatus.textContent = selectionTemplates.length
      ? `${selectionTemplates.length}件保存済み`
      : "ブラウザ内に保存します";
  };

  const currentTemplateState = () => {
    if (!catalog) return [];
    return catalog.collections.flatMap((collection) =>
      collection.items
        .filter((item) => selectedItemKeys.has(itemKey(collection.id, item)))
        .map((item) => ({
          collectionId: collection.id,
          modelId: item.modelId,
          versionId: item.versionId,
        }))
    );
  };

  const saveCurrentTemplate = () => {
    const name = templateName.value.trim();
    const items = currentTemplateState();
    if (!name) {
      showToast("テンプレート名を入力してください", true);
      templateName.focus();
      return;
    }
    if (!items.length) {
      showToast("保存するモデルを選択してください", true);
      return;
    }

    const existing = selectionTemplates.find(
      (template) => normalizeSearch(template.name) === normalizeSearch(name)
    );
    const saved = {
      id: existing?.id || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
      name,
      collectionIds: selectedCollectionIds(),
      items,
      savedAt: new Date().toISOString(),
    };
    selectionTemplates = existing
      ? selectionTemplates.map((template) => (template.id === existing.id ? saved : template))
      : [...selectionTemplates, saved];
    if (!writeTemplates()) return;
    renderTemplateList(saved.id);
    templateName.value = "";
    showToast(existing ? "テンプレートを更新しました" : "テンプレートを保存しました");
  };

  const updateCollectionSelection = () => {
    collectionCount.textContent = String(selectedCollectionIds().length);
  };

  const resetResults = () => {
    currentExport = null;
    resultGroups.replaceChildren();
    resultSummary.textContent = "";
    resultsContent.hidden = true;
    emptyManifest.hidden = false;
    copyButton.hidden = true;
  };

  const setPickerEmpty = (title, description) => {
    itemPickerEmpty.querySelector("h3").textContent = title;
    itemPickerEmpty.querySelector("p").textContent = description;
    itemPickerEmpty.hidden = false;
    itemPickerContent.hidden = true;
    itemTools.hidden = true;
  };

  const resetCatalog = () => {
    catalog = null;
    selectedItemKeys.clear();
    itemSearchEmpty.hidden = true;
    itemGroups.replaceChildren();
    itemCount.textContent = "0";
    itemStatus.textContent = "";
    setPickerEmpty(
      "コレクションを選択、または検索",
      "左側でコレクションを選ぶか、上部から全コレクションを検索してください。"
    );
    resetResults();
  };

  const showToast = (message, isError = false) => {
    toast.textContent = message;
    toast.classList.toggle("toast-error", isError);
    toast.hidden = false;
    window.clearTimeout(showToast.timeout);
    showToast.timeout = window.setTimeout(() => {
      toast.hidden = true;
    }, 3200);
  };

  const formatSize = (sizeKB) => {
    if (typeof sizeKB !== "number") return "サイズ不明";
    if (sizeKB >= 1024 * 1024) return `${(sizeKB / 1024 / 1024).toFixed(2)} GB`;
    return `${(sizeKB / 1024).toFixed(1)} MB`;
  };

  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const updateModelThumbnail = (frame, item) => {
    const image = frame.querySelector("img");
    const hasThumbnail = Boolean(item.thumbnailUrl);
    image.src = item.thumbnailUrl || "/static/model-placeholder.svg";
    image.alt = hasThumbnail ? `${item.modelName}のサムネイル` : "";
    image.width = Number(item.thumbnailWidth) || 320;
    image.height = Number(item.thumbnailHeight) || 400;
    image.dataset.fallback = hasThumbnail ? "false" : "true";
  };

  const createModelThumbnail = (item, className) => {
    const frame = element("span", className);
    const image = element("img");
    image.loading = "lazy";
    image.decoding = "async";
    image.addEventListener("error", () => {
      if (image.dataset.fallback === "true") return;
      image.dataset.fallback = "true";
      image.src = "/static/model-placeholder.svg";
      image.alt = "";
    });
    frame.append(image);
    updateModelThumbnail(frame, item);
    return frame;
  };

  const renderFile = (file) => {
    const row = element("div", "file-row");
    const identity = element("div", "file-identity");
    identity.append(element("span", "file-dot", file.primary ? "P" : "F"));
    const detail = element("div");
    detail.append(element("strong", "file-name", file.name));
    const metadata = [file.format, file.precision, formatSize(file.sizeKB)]
      .filter(Boolean)
      .join(" · ");
    detail.append(element("span", "file-meta", metadata));
    identity.append(detail);
    row.append(identity);
    return row;
  };

  const renderModel = (item, index) => {
    const card = element("article", "model-card");
    const header = element("div", "model-header");
    header.append(element("span", "model-index", String(index + 1).padStart(2, "0")));
    header.append(createModelThumbnail(item, "model-thumbnail"));
    const title = element("div");
    const heading = element("h4");
    const modelLink = element("a", "model-title-link", item.modelName);
    modelLink.href = item.modelUrl;
    modelLink.target = "_blank";
    modelLink.rel = "noopener noreferrer";
    heading.append(modelLink);
    title.append(heading);
    title.append(element("span", "version-label", `${item.versionName} · ID ${item.versionId}`));
    header.append(title);
    card.append(header);

    const columns = element("div", "model-columns");
    const files = element("div", "model-panel");
    files.append(element("h5", null, "FILES"));
    if (item.files.length) item.files.forEach((file) => files.append(renderFile(file)));
    else files.append(element("p", "empty-value", "ファイル情報を取得できませんでした"));

    const triggers = element("div", "model-panel trigger-panel");
    triggers.append(element("h5", null, "TRIGGER WORDS"));
    if (item.trainedWords.length) {
      const list = element("div", "trigger-list");
      item.trainedWords.forEach((word) => list.append(element("code", null, word)));
      triggers.append(list);
    } else {
      triggers.append(element("p", "empty-value", "登録なし"));
    }
    columns.append(files, triggers);
    card.append(columns);
    if (item.error) card.append(element("p", "item-error", item.error));
    return card;
  };

  const renderResults = (payload) => {
    resultGroups.replaceChildren();
    let totalItems = 0;
    let totalFiles = 0;
    payload.collections.forEach((collection) => {
      totalItems += collection.items.length;
      totalFiles += collection.items.reduce((sum, item) => sum + item.files.length, 0);
      const group = element("section", "result-group");
      const heading = element("div", "group-heading");
      heading.append(element("h3", null, collection.name));
      heading.append(element("span", null, `${collection.items.length} SELECTED`));
      group.append(heading);
      const models = element("div", "model-list");
      collection.items.forEach((item, index) => models.append(renderModel(item, index)));
      group.append(models);
      resultGroups.append(group);
    });
    resultSummary.textContent = `${payload.collections.length}コレクション · ${totalItems}モデル · ${totalFiles}ファイル`;
    resultsContent.hidden = false;
    emptyManifest.hidden = true;
    copyButton.hidden = false;
  };

  const selectedPayload = () => {
    if (!catalog) return null;
    const collections = catalog.collections
      .map((collection) => ({
        id: collection.id,
        name: collection.name,
        items: collection.items
          .filter((item) => selectedItemKeys.has(itemKey(collection.id, item)))
          .map((item) => {
            const { versions: _versions, ...selectedItem } = item;
            return selectedItem;
          }),
      }))
      .filter((collection) => collection.items.length > 0);
    const fileNames = new Set();
    collections.forEach((collection) => {
      collection.items.forEach((item) => {
        item.files.forEach((file) => {
          if (file.name) fileNames.add(file.name);
        });
      });
    });
    const files = [...fileNames].map((name) => ({ name }));
    return { generatedAt: catalog.generatedAt, files, collections };
  };

  const updateSelectedResults = () => {
    itemCount.textContent = String(selectedItemKeys.size);
    itemCheckboxes().forEach((checkbox) => {
      checkbox.checked = selectedItemKeys.has(checkbox.dataset.itemKey);
    });
    if (!selectedItemKeys.size) {
      itemStatus.textContent = "表示するアイテムを選択してください";
      resetResults();
      return;
    }
    currentExport = selectedPayload();
    itemStatus.textContent = `${selectedItemKeys.size}件を下部に表示中`;
    renderResults(currentExport);
  };

  const applyItemFilter = () => {
    if (!catalog) return;
    const query = normalizeSearch(itemSearch.value.trim());
    let visibleItems = 0;
    let totalItems = 0;

    document.querySelectorAll(".item-group").forEach((group) => {
      const options = [...group.querySelectorAll(".item-option")];
      const visibleInGroup = options.reduce((count, option) => {
        const matches = !query || option.dataset.searchText.includes(query);
        option.hidden = !matches;
        totalItems += 1;
        if (matches) visibleItems += 1;
        return count + (matches ? 1 : 0);
      }, 0);
      group.hidden = Boolean(query) && visibleInGroup === 0;
      const groupCount = group.querySelector(".item-group-count");
      if (groupCount) {
        groupCount.textContent = query
          ? `${visibleInGroup} / ${options.length} MODELS`
          : `${options.length} MODELS`;
      }
    });

    itemSearchEmpty.hidden = !query || visibleItems > 0;
    if (query) {
      const selectedStatus = selectedItemKeys.size
        ? ` · ${selectedItemKeys.size}件選択中`
        : "";
      itemStatus.textContent = `${visibleItems} / ${totalItems}件に一致${selectedStatus}`;
    } else if (selectedItemKeys.size) {
      itemStatus.textContent = `${selectedItemKeys.size}件を下部に表示中`;
    } else {
      itemStatus.textContent = `${totalItems}件から選択できます`;
    }
  };

  const renderItemOption = (collection, item) => {
    const option = element("div", "item-option");
    option.dataset.searchText = searchableItemText(item);
    const label = element("label", "item-option-select");
    const checkbox = element("input", "item-checkbox");
    const key = itemKey(collection.id, item);
    checkbox.type = "checkbox";
    checkbox.dataset.itemKey = key;
    checkbox.dataset.collectionId = String(collection.id);
    checkbox.checked = selectedItemKeys.has(key);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        selectedItemKeys.add(key);
        const parentCollection = collectionCheckboxes.find(
          (candidate) => Number(candidate.value) === Number(collection.id)
        );
        if (parentCollection) parentCollection.checked = true;
        updateCollectionSelection();
      } else selectedItemKeys.delete(key);
      updateSelectedResults();
      applyItemFilter();
    });

    const thumbnail = createModelThumbnail(item, "item-thumbnail");
    const marker = element("span", "item-option-marker", "✓");
    const copy = element("span", "item-option-copy");
    copy.append(element("strong", null, item.modelName));
    const versionSummary = element(
      "span",
      null,
      `${item.versionName} · VERSION ${item.versionId}`
    );
    copy.append(versionSummary);
    const facts = element("span", "item-option-facts");
    const fileFact = element(
      "small",
      null,
      `${item.files.length} FILE${item.files.length === 1 ? "" : "S"}`
    );
    const triggerFact = element(
      "small",
      null,
      `${item.trainedWords.length} TRIGGER${item.trainedWords.length === 1 ? "" : "S"}`
    );
    facts.append(fileFact, triggerFact);
    copy.append(facts);
    label.append(checkbox, thumbnail, copy, marker);

    const actions = element("div", "item-option-actions");
    const versionControl = element("label", "version-control");
    versionControl.append(element("span", null, "VERSION"));
    const versionSelect = element("select", "version-select");
    versionSelect.setAttribute("aria-label", `${item.modelName}のバージョン`);
    const versions = Array.isArray(item.versions) && item.versions.length
      ? item.versions
      : [item];
    versions.forEach((version) => {
      const choice = element(
        "option",
        null,
        `${version.versionName} · ${version.versionId}`
      );
      choice.value = String(version.versionId);
      versionSelect.append(choice);
    });
    versionSelect.value = String(item.versionId);
    versionSelect.disabled = versions.length < 2;
    versionControl.append(versionSelect);

    const link = element("a", "item-link", "CIVITAIで開く ↗");
    link.href = item.modelUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    versionSelect.addEventListener("change", () => {
      if (!applyVersionToItem(item, versionSelect.value)) return;

      versionSummary.textContent = `${item.versionName} · VERSION ${item.versionId}`;
      fileFact.textContent = `${item.files.length} FILE${item.files.length === 1 ? "" : "S"}`;
      triggerFact.textContent = `${item.trainedWords.length} TRIGGER${item.trainedWords.length === 1 ? "" : "S"}`;
      link.href = item.modelUrl;
      updateModelThumbnail(thumbnail, item);
      updateSelectedResults();
      applyItemFilter();
    });
    actions.append(versionControl, link);
    option.append(label, actions);
    return option;
  };

  const renderItemPicker = (payload) => {
    itemGroups.replaceChildren();
    const availableKeys = new Set();
    let totalItems = 0;

    payload.collections.forEach((collection) => {
      const group = element("section", "item-group");
      const heading = element("div", "item-group-heading");
      heading.append(element("h3", null, collection.name));
      heading.append(
        element("span", "item-group-count", `${collection.items.length} MODELS`)
      );
      group.append(heading);
      const list = element("div", "item-option-list");
      if (collection.items.length) {
        collection.items.forEach((item) => {
          totalItems += 1;
          availableKeys.add(itemKey(collection.id, item));
          list.append(renderItemOption(collection, item));
        });
      } else {
        list.append(element("p", "empty-collection", "表示できるモデルがありません。"));
      }
      group.append(list);
      itemGroups.append(group);
    });

    [...selectedItemKeys].forEach((key) => {
      if (!availableKeys.has(key)) selectedItemKeys.delete(key);
    });

    if (!totalItems) {
      setPickerEmpty(
        "表示できるアイテムがありません",
        "選択したコレクションには取得可能なモデルがありません。"
      );
      itemStatus.textContent = "0件";
      updateSelectedResults();
      return;
    }

    itemPickerEmpty.hidden = true;
    itemPickerContent.hidden = false;
    itemTools.hidden = false;
    itemStatus.textContent = `${totalItems}件から選択できます`;
    updateSelectedResults();
    applyItemFilter();
  };

  const loadSelection = async (
    collectionIds = selectedCollectionIds(),
    { globalSearch = false } = {}
  ) => {
    if (!collectionIds.length) {
      requestSerial += 1;
      collectionStatus.textContent = "コレクションを選択してください";
      collectionStatus.classList.remove("is-loading");
      resetCatalog();
      return;
    }

    const serial = ++requestSerial;
    collectionStatus.textContent = "Civitaiから取得中…";
    collectionStatus.classList.add("is-loading");
    itemStatus.textContent = "アイテムを読み込んでいます…";
    try {
      const response = await fetch("/api/selection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ collectionIds }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "取得に失敗しました。");
      if (serial !== requestSerial) return;
      catalog = payload;
      if (globalSearch) globalCatalog = payload;
      renderItemPicker(payload);
      const totalItems = payload.collections.reduce(
        (sum, collection) => sum + collection.items.length,
        0
      );
      collectionStatus.textContent = `${totalItems}件を読み込みました`;
      return true;
    } catch (error) {
      if (serial !== requestSerial) return;
      collectionStatus.textContent = "取得に失敗しました";
      itemStatus.textContent = "";
      showToast(error.message || "取得に失敗しました。", true);
      return false;
    } finally {
      if (serial === requestSerial) collectionStatus.classList.remove("is-loading");
    }
  };

  const scheduleLoad = () => {
    window.clearTimeout(loadTimer);
    loadTimer = window.setTimeout(loadSelection, 350);
  };

  const runGlobalSearch = async () => {
    const query = itemSearch.value.trim();
    if (!query) {
      globalSearchMode = false;
      globalSearchStatus.textContent = `${collectionCheckboxes.length}コレクションを横断検索します`;
      await loadSelection();
      return;
    }

    globalSearchMode = true;
    if (globalCatalog) {
      catalog = globalCatalog;
      renderItemPicker(globalCatalog);
      globalSearchStatus.textContent = "全コレクションの取得済みデータを検索中";
      return;
    }

    globalSearchStatus.textContent = "全コレクションを読み込んでいます…";
    const loaded = await loadSelection(allCollectionIds(), { globalSearch: true });
    if (loaded && itemSearch.value.trim()) {
      globalSearchStatus.textContent = "全コレクションを検索中";
      applyItemFilter();
    }
  };

  const scheduleGlobalSearch = () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(runGlobalSearch, 300);
  };

  const clearItemsForCollections = (collectionIds) => {
    const deselectedIds = new Set(collectionIds.map((id) => String(id)));
    [...selectedItemKeys].forEach((key) => {
      const collectionId = key.split(":", 1)[0];
      if (deselectedIds.has(collectionId)) selectedItemKeys.delete(key);
    });
    updateSelectedResults();
    applyItemFilter();
  };

  const applySelectedTemplate = async () => {
    const template = selectionTemplates.find(
      (candidate) => candidate.id === templateList.value
    );
    if (!template) return;

    const availableCollectionIds = new Set(
      collectionCheckboxes.map((checkbox) => Number(checkbox.value))
    );
    const collectionIds = template.collectionIds.filter((id) =>
      availableCollectionIds.has(Number(id))
    );
    if (!collectionIds.length) {
      showToast("テンプレートのコレクションが見つかりません", true);
      return;
    }

    collectionCheckboxes.forEach((checkbox) => {
      checkbox.checked = collectionIds.includes(Number(checkbox.value));
    });
    selectedItemKeys.clear();
    catalog = null;
    globalSearchMode = false;
    itemSearch.value = "";
    updateCollectionSelection();
    await loadSelection();
    if (!catalog) return;

    let restoredItems = 0;
    template.items.forEach((savedItem) => {
      const collection = catalog.collections.find(
        (candidate) => Number(candidate.id) === Number(savedItem.collectionId)
      );
      const item = collection?.items.find(
        (candidate) => Number(candidate.modelId) === Number(savedItem.modelId)
      );
      if (!collection || !item) return;
      applyVersionToItem(item, savedItem.versionId);
      selectedItemKeys.add(itemKey(collection.id, item));
      restoredItems += 1;
    });
    renderItemPicker(catalog);
    templateName.value = template.name;
    showToast(`${template.name}を適用しました（${restoredItems}件）`);
  };

  const deleteSelectedTemplate = () => {
    const template = selectionTemplates.find(
      (candidate) => candidate.id === templateList.value
    );
    if (!template) return;
    if (!window.confirm(`「${template.name}」を削除しますか？`)) return;
    selectionTemplates = selectionTemplates.filter(
      (candidate) => candidate.id !== template.id
    );
    if (!writeTemplates()) return;
    renderTemplateList();
    showToast("テンプレートを削除しました");
  };

  collectionCheckboxes.forEach((checkbox) =>
    checkbox.addEventListener("change", () => {
      if (!checkbox.checked) clearItemsForCollections([checkbox.value]);
      updateCollectionSelection();
      if (!globalSearchMode) scheduleLoad();
    })
  );
  selectAllCollections.addEventListener("click", () => {
    collectionCheckboxes.forEach((checkbox) => (checkbox.checked = true));
    updateCollectionSelection();
    if (!globalSearchMode) scheduleLoad();
  });
  clearAllCollections.addEventListener("click", () => {
    collectionCheckboxes.forEach((checkbox) => (checkbox.checked = false));
    clearItemsForCollections(allCollectionIds());
    updateCollectionSelection();
    if (!globalSearchMode) scheduleLoad();
  });

  selectAllItems.addEventListener("click", () => {
    itemCheckboxes()
      .filter((checkbox) => !checkbox.closest(".item-option").hidden)
      .forEach((checkbox) => {
        selectedItemKeys.add(checkbox.dataset.itemKey);
        const parentCollection = collectionCheckboxes.find(
          (candidate) =>
            Number(candidate.value) === Number(checkbox.dataset.collectionId)
        );
        if (parentCollection) parentCollection.checked = true;
      });
    updateCollectionSelection();
    updateSelectedResults();
    applyItemFilter();
  });
  clearAllItems.addEventListener("click", () => {
    clearItemsForCollections(allCollectionIds());
  });

  itemSearch.addEventListener("input", scheduleGlobalSearch);

  templateSave.addEventListener("click", saveCurrentTemplate);
  templateName.addEventListener("keydown", (event) => {
    if (event.key === "Enter") saveCurrentTemplate();
  });
  templateList.addEventListener("change", () => {
    const hasTemplate = Boolean(templateList.value);
    templateLoad.disabled = !hasTemplate;
    templateDelete.disabled = !hasTemplate;
  });
  templateLoad.addEventListener("click", applySelectedTemplate);
  templateDelete.addEventListener("click", deleteSelectedTemplate);

  copyButton.addEventListener("click", async () => {
    if (!currentExport) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(currentExport, null, 2));
      showToast("選択アイテムのJSONをコピーしました");
    } catch (_error) {
      showToast("クリップボードへのコピーに失敗しました", true);
    }
  });

  updateCollectionSelection();
  renderTemplateList();
})();
