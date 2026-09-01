(() => {
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
  const itemCount = document.querySelector("#item-selection-count");
  const itemStatus = document.querySelector("#item-picker-status");
  const resultsContent = document.querySelector("#results-content");
  const emptyManifest = document.querySelector("#empty-manifest");
  const resultGroups = document.querySelector("#result-groups");
  const resultSummary = document.querySelector("#result-summary");
  const copyButton = document.querySelector("#copy-json");
  const toast = document.querySelector("#toast");
  let catalog = null;
  let currentExport = null;
  let loadTimer = null;
  let requestSerial = 0;
  const selectedItemKeys = new Set();

  const selectedCollectionIds = () =>
    collectionCheckboxes
      .filter((checkbox) => checkbox.checked)
      .map((checkbox) => Number(checkbox.value));

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
    itemSearch.value = "";
    itemSearchEmpty.hidden = true;
    itemGroups.replaceChildren();
    itemCount.textContent = "0";
    itemStatus.textContent = "";
    setPickerEmpty(
      "先にコレクションを選択",
      "選択したコレクションに含まれるモデルをここへ並べます。"
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
    checkbox.checked = selectedItemKeys.has(key);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) selectedItemKeys.add(key);
      else selectedItemKeys.delete(key);
      updateSelectedResults();
      applyItemFilter();
    });

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
    label.append(checkbox, marker, copy);

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
      const selectedVersion = versions.find(
        (version) => String(version.versionId) === versionSelect.value
      );
      if (!selectedVersion) return;
      item.versionId = selectedVersion.versionId;
      item.versionName = selectedVersion.versionName;
      item.modelUrl = selectedVersion.modelUrl;
      item.trainedWords = selectedVersion.trainedWords;
      item.files = selectedVersion.files;
      delete item.error;

      versionSummary.textContent = `${item.versionName} · VERSION ${item.versionId}`;
      fileFact.textContent = `${item.files.length} FILE${item.files.length === 1 ? "" : "S"}`;
      triggerFact.textContent = `${item.trainedWords.length} TRIGGER${item.trainedWords.length === 1 ? "" : "S"}`;
      link.href = item.modelUrl;
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

  const loadSelection = async () => {
    const collectionIds = selectedCollectionIds();
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
      renderItemPicker(payload);
      const totalItems = payload.collections.reduce(
        (sum, collection) => sum + collection.items.length,
        0
      );
      collectionStatus.textContent = `${totalItems}件を読み込みました`;
    } catch (error) {
      if (serial !== requestSerial) return;
      collectionStatus.textContent = "取得に失敗しました";
      itemStatus.textContent = "";
      showToast(error.message || "取得に失敗しました。", true);
    } finally {
      if (serial === requestSerial) collectionStatus.classList.remove("is-loading");
    }
  };

  const scheduleLoad = () => {
    window.clearTimeout(loadTimer);
    loadTimer = window.setTimeout(loadSelection, 350);
  };

  collectionCheckboxes.forEach((checkbox) =>
    checkbox.addEventListener("change", () => {
      updateCollectionSelection();
      scheduleLoad();
    })
  );
  selectAllCollections.addEventListener("click", () => {
    collectionCheckboxes.forEach((checkbox) => (checkbox.checked = true));
    updateCollectionSelection();
    scheduleLoad();
  });
  clearAllCollections.addEventListener("click", () => {
    collectionCheckboxes.forEach((checkbox) => (checkbox.checked = false));
    updateCollectionSelection();
    scheduleLoad();
  });

  selectAllItems.addEventListener("click", () => {
    itemCheckboxes()
      .filter((checkbox) => !checkbox.closest(".item-option").hidden)
      .forEach((checkbox) => selectedItemKeys.add(checkbox.dataset.itemKey));
    updateSelectedResults();
    applyItemFilter();
  });
  clearAllItems.addEventListener("click", () => {
    selectedItemKeys.clear();
    updateSelectedResults();
    applyItemFilter();
  });

  itemSearch.addEventListener("input", applyItemFilter);

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
})();
