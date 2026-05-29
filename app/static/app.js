/* ============================================================
   Kanban — Triage design system, vanilla JS
   ============================================================ */

// ── Design constants ─────────────────────────────────────────

const PRIORITIES = {
  1: { short: "P1", name: "Urgent", color: "#e0524d" },
  2: { short: "P2", name: "High",   color: "#e08a2f" },
  3: { short: "P3", name: "Medium", color: "#2b93e0" },
  4: { short: "P4", name: "Low",    color: "#7c8a99" },
};

const PROJECT_PALETTE = [
  "#2b93e0", "#8a6cd1", "#2f9268", "#e08a2f",
  "#e0524d", "#4f7fe0", "#19b0c9", "#9268a0",
];

const BG_PRESETS = [
  { id: "sky",  label: "Sky",  css: "linear-gradient(160deg,#dcebfb,#a9d2f2 55%,#6aa9e0)" },
  { id: "mist", label: "Mist", css: "linear-gradient(160deg,#eef4f9,#cfe0ee 55%,#9fbdd6)" },
  { id: "dusk", label: "Dusk", css: "linear-gradient(160deg,#d7e3f2,#9fb0d8 55%,#5d6aa0)" },
  { id: "teal", label: "Teal", css: "linear-gradient(160deg,#d6f0ef,#9ad6d4 55%,#4f9b9a)" },
];

function projectColor(name) {
  let h = 0;
  for (const ch of String(name)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PROJECT_PALETTE[h % PROJECT_PALETTE.length];
}

// ── API ───────────────────────────────────────────────────────

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(body.error || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ── State ─────────────────────────────────────────────────────

let board = { settings: { background: { type: "none", value: "", fit: "cover" } }, columns: [], cards: [] };
let dragId = null;
let dropInfo = null;   // { colId, beforeId, index }
let activeCardId = null;
let toastTimer = null;

// filter state
let searchQuery = "";
let projFilter = new Set();
let priFilter  = new Set();

// background panel draft state
let bgDraft = { mode: "none", value: "", scrim: 30, uploadDataUrl: "" };

// ── Quick-add parser ──────────────────────────────────────────

function parseQuickAdd(raw) {
  let text = raw;
  let notes = "";
  let project = "";
  let priority = 3;

  const pipeIdx = text.indexOf("|");
  if (pipeIdx !== -1) {
    notes = text.slice(pipeIdx + 1).trim();
    text  = text.slice(0, pipeIdx).trim();
  }

  text = text.replace(/@(\S+)/g, (_, w) => { project = w.trim(); return ""; }).trim();
  text = text.replace(/\bp([1-4])\b/gi, (_, n) => { priority = parseInt(n, 10); return ""; }).trim();
  text = text.replace(/\s{2,}/g, " ").trim();

  return { title: text, notes, project, priority };
}

// ── Filtering / sorting ───────────────────────────────────────

function cardsFor(columnId) {
  const q = searchQuery.trim().toLowerCase();
  return board.cards
    .filter((c) => c.column === columnId)
    .filter((c) => !projFilter.size || projFilter.has(c.project || ""))
    .filter((c) => !priFilter.size  || priFilter.has(c.priority))
    .filter((c) => {
      if (!q) return true;
      return [c.title, c.notes, c.project]
        .some((v) => String(v || "").toLowerCase().includes(q));
    })
    .sort((a, b) => (a.sortIndex ?? 0) - (b.sortIndex ?? 0) || a.createdAt - b.createdAt);
}

function allCardsFor(columnId) {
  return board.cards
    .filter((c) => c.column === columnId)
    .sort((a, b) => (a.sortIndex ?? 0) - (b.sortIndex ?? 0) || a.createdAt - b.createdAt);
}

// ── Render ────────────────────────────────────────────────────

const boardEl      = document.getElementById("board");
const columnTpl    = document.getElementById("column-template");
const cardTpl      = document.getElementById("card-template");
const searchInput  = document.getElementById("search-input");
const projGroup    = document.getElementById("proj-filter-group");
const priGroup     = document.getElementById("pri-filter-group");
const clearBtn     = document.getElementById("clear-filters");

function formatShortDate(ts) {
  return new Date(ts * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatDate(ts) {
  return new Date(ts * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function renderProjFilterChips() {
  // keep the lbl span, remove previous chips
  const existing = projGroup.querySelectorAll(".fchip");
  existing.forEach((el) => el.remove());

  const projects = [...new Set(board.cards.map((c) => c.project).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  for (const name of projects) {
    const color = projectColor(name);
    const btn = document.createElement("button");
    btn.className = "fchip";
    btn.type = "button";
    btn.dataset.on = projFilter.has(name) ? "1" : "0";
    btn.style.setProperty("--chip-color", color);
    btn.innerHTML = `<i class="swatch" style="background:${color}"></i>${esc(name)}`;
    btn.addEventListener("click", () => {
      projFilter.has(name) ? projFilter.delete(name) : projFilter.add(name);
      render();
    });
    projGroup.appendChild(btn);
  }
}

function renderPriFilterChips() {
  const existing = priGroup.querySelectorAll(".fchip");
  existing.forEach((el) => el.remove());

  for (const [num, p] of Object.entries(PRIORITIES)) {
    const pri = parseInt(num, 10);
    const btn = document.createElement("button");
    btn.className = "fchip";
    btn.type = "button";
    btn.dataset.on = priFilter.has(pri) ? "1" : "0";
    btn.style.setProperty("--chip-color", p.color);
    btn.innerHTML = `<i class="swatch" style="background:${p.color};border-radius:50%"></i>${p.short}`;
    btn.addEventListener("click", () => {
      priFilter.has(pri) ? priFilter.delete(pri) : priFilter.add(pri);
      render();
    });
    priGroup.appendChild(btn);
  }
}

function renderCard(card) {
  const node = cardTpl.content.firstElementChild.cloneNode(true);
  const col = board.columns.find((c) => c.id === card.column);
  const pri = PRIORITIES[card.priority] || PRIORITIES[4];
  const projColor = card.project ? projectColor(card.project) : "#7c8a99";

  node.dataset.id = card.id;
  node.style.setProperty("--pri-color", pri.color);
  node.style.setProperty("--proj-color", projColor);
  node.style.setProperty("--st-color", col ? col.accent : "#7c8a99");

  node.querySelector(".title").textContent = card.title;

  // status pill
  const sname = node.querySelector(".sname");
  sname.textContent = col ? col.title : "";

  // desc / notes
  const descEl = node.querySelector(".desc");
  if (card.notes && card.notes.trim()) {
    descEl.textContent = card.notes;
  } else {
    descEl.remove();
  }

  // project chip
  node.querySelector(".pname").textContent = card.project || "—";

  // priority
  node.querySelector(".pshort").textContent = pri.short;

  // drag
  node.addEventListener("dragstart", (e) => {
    dragId = card.id;
    node.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    try { e.dataTransfer.setData("text/plain", card.id); } catch (_) {}
  });
  node.addEventListener("dragend", () => {
    dragId = null;
    dropInfo = null;
    node.classList.remove("dragging");
    render();
  });

  node.addEventListener("click", () => openModal(card.id));

  return node;
}

function render() {
  renderProjFilterChips();
  renderPriFilterChips();

  const anyFilter = projFilter.size || priFilter.size || searchQuery.trim();
  clearBtn.hidden = !anyFilter;

  boardEl.replaceChildren();

  for (const col of board.columns) {
    const colNode = columnTpl.content.firstElementChild.cloneNode(true);
    const tag   = colNode.querySelector(".tag");
    const nameEl = colNode.querySelector(".name");
    const countEl = colNode.querySelector(".count");
    const cards  = colNode.querySelector(".col-cards");

    tag.style.background = col.accent || "#7c8a99";
    nameEl.textContent  = col.title;

    const visible = cardsFor(col.id);
    const total   = allCardsFor(col.id).length;
    countEl.textContent = anyFilter ? `${visible.length}/${total}` : total;

    colNode.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      colNode.classList.add("drag-over");

      // compute drop index from cursor Y
      const cardEls = [...cards.querySelectorAll(".card:not(.dragging)")];
      let index = cardEls.length;
      let beforeId = null;
      for (let i = 0; i < cardEls.length; i++) {
        const r = cardEls[i].getBoundingClientRect();
        if (e.clientY < r.top + r.height / 2) {
          index = i;
          beforeId = cardEls[i].dataset.id;
          break;
        }
      }
      dropInfo = { colId: col.id, index, beforeId };
      renderDropLine(cards, cardEls, index);
    });

    colNode.addEventListener("dragleave", (e) => {
      if (!colNode.contains(e.relatedTarget)) {
        colNode.classList.remove("drag-over");
        dropInfo = null;
        removeDropLine(cards);
      }
    });

    colNode.addEventListener("drop", async (e) => {
      e.preventDefault();
      colNode.classList.remove("drag-over");
      removeDropLine(cards);
      const id = dragId || e.dataTransfer.getData("text/plain");
      const info = dropInfo && dropInfo.colId === col.id ? dropInfo : { colId: col.id, index: total, beforeId: null };
      dragId = null;
      dropInfo = null;
      if (!id) { render(); return; }
      try { await moveCard(id, col.id, info.beforeId); } catch (err) { console.error(err); render(); }
    });

    // render cards with optional empty state
    if (visible.length === 0) {
      const empty = document.createElement("div");
      empty.className = "col-empty";
      empty.textContent = anyFilter ? "No matching cards" : "Drag cards here";
      cards.appendChild(empty);
    } else {
      for (const card of visible) {
        cards.appendChild(renderCard(card));
      }
    }

    boardEl.appendChild(colNode);
  }
}

function renderDropLine(cards, cardEls, index) {
  removeDropLine(cards);
  const line = document.createElement("div");
  line.className = "drop-line";
  line.id = "__drop-line";
  if (index >= cardEls.length) {
    cards.appendChild(line);
  } else {
    cards.insertBefore(line, cardEls[index]);
  }
}

function removeDropLine(cards) {
  const line = cards.querySelector("#__drop-line");
  if (line) line.remove();
}

// ── CRUD ──────────────────────────────────────────────────────

async function updateCard(id, patch, shouldRender = true) {
  const updated = await api(`/api/cards/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
  board.cards = board.cards.map((c) => (c.id === id ? updated : c));
  if (shouldRender) render();
  return updated;
}

async function deleteCard(id) {
  const removed = board.cards.find((c) => c.id === id);
  if (!removed) return;
  if (activeCardId === id) closeModal();
  await api(`/api/cards/${encodeURIComponent(id)}`, { method: "DELETE" });
  board.cards = board.cards.filter((c) => c.id !== id);
  render();
  showUndo(removed);
}

async function moveCard(id, colId, beforeId) {
  if (beforeId === id) return;
  const card = board.cards.find((c) => c.id === id);
  if (!card) return;

  const ordered = allCardsFor(colId).filter((c) => c.id !== id);
  const insertAt = beforeId ? ordered.findIndex((c) => c.id === beforeId) : -1;
  card.column = colId;
  ordered.splice(insertAt >= 0 ? insertAt : ordered.length, 0, card);
  ordered.forEach((c, i) => { c.sortIndex = i; });
  render();

  await Promise.all(ordered.map((c) =>
    updateCard(c.id, { column: c.column, sortIndex: c.sortIndex }, false)
  ));
  render();
}

// ── Toast ─────────────────────────────────────────────────────

const toastEl = document.getElementById("toast");

function showUndo(card) {
  if (toastTimer) clearTimeout(toastTimer);
  toastEl.replaceChildren();
  const label = document.createElement("span");
  label.textContent = "Card deleted";
  const undoBtn = document.createElement("button");
  undoBtn.type = "button";
  undoBtn.textContent = "Undo";
  undoBtn.addEventListener("click", async () => {
    if (toastTimer) clearTimeout(toastTimer);
    toastEl.hidden = true;
    try {
      const restored = await api("/api/cards", {
        method: "POST",
        body: JSON.stringify({
          title:    card.title,
          notes:    card.notes || "",
          project:  card.project || "",
          priority: card.priority,
          column:   card.column,
        }),
      });
      const withOrder = await updateCard(restored.id, { sortIndex: card.sortIndex ?? 0 }, false);
      board.cards.push(withOrder);
      render();
    } catch (err) {
      console.error("Undo failed:", err);
      showToast("Undo failed — card could not be restored");
    }
  });
  toastEl.append(label, undoBtn);
  toastEl.hidden = false;
  toastTimer = setTimeout(() => { toastEl.hidden = true; }, 5000);
}

function showToast(msg) {
  if (toastTimer) clearTimeout(toastTimer);
  toastEl.replaceChildren();
  toastEl.append(document.createTextNode(msg));
  toastEl.hidden = false;
  toastTimer = setTimeout(() => { toastEl.hidden = true; }, 2200);
}

// ── Modal ─────────────────────────────────────────────────────

const modalOverlay  = document.getElementById("modal-overlay");
const modalStatus   = document.getElementById("modal-status-badge");
const modalTitle    = document.getElementById("modal-title");
const modalNotes    = document.getElementById("modal-notes");
const modalProjChoose = document.getElementById("modal-proj-choose");
const modalPriChoose  = document.getElementById("modal-pri-choose");
const modalClose    = document.getElementById("modal-close");
const modalCancel   = document.getElementById("modal-cancel");
const modalSave     = document.getElementById("modal-save");
const modalDelete   = document.getElementById("modal-delete");

let modalDraft = null;

function openModal(cardId) {
  const card = board.cards.find((c) => c.id === cardId);
  if (!card) return;
  activeCardId = cardId;
  modalDraft = { ...card };

  const col = board.columns.find((c) => c.id === card.column);
  modalStatus.style.setProperty("--st-color", col ? col.accent : "#7c8a99");
  modalStatus.innerHTML = `<i class="sdot"></i>${esc(col ? col.title : card.column)}`;

  modalTitle.value = card.title;
  modalNotes.value  = card.notes || "";

  // project chips
  const projects = [...new Set(board.cards.map((c) => c.project).filter(Boolean))].sort();
  if (card.project && !projects.includes(card.project)) projects.unshift(card.project);

  modalProjChoose.replaceChildren();
  for (const name of projects) {
    const color = projectColor(name);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.on = (modalDraft.project === name) ? "1" : "0";
    btn.style.setProperty("--ch-color", color);
    btn.innerHTML = `<i class="swatch" style="background:${color}"></i>${esc(name)}`;
    btn.addEventListener("click", () => {
      modalDraft.project = name;
      modalProjChoose.querySelectorAll("button").forEach((b) => {
        b.dataset.on = b === btn ? "1" : "0";
      });
    });
    modalProjChoose.appendChild(btn);
  }

  // priority chips
  modalPriChoose.replaceChildren();
  for (const [num, p] of Object.entries(PRIORITIES)) {
    const pri = parseInt(num, 10);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.on = (modalDraft.priority === pri) ? "1" : "0";
    btn.style.setProperty("--ch-color", p.color);
    btn.innerHTML = `<i class="swatch" style="background:${p.color};border-radius:50%"></i>${p.short} <small style="opacity:.6;font-size:10px">${p.name}</small>`;
    btn.addEventListener("click", () => {
      modalDraft.priority = pri;
      modalPriChoose.querySelectorAll("button").forEach((b) => {
        b.dataset.on = b === btn ? "1" : "0";
      });
    });
    modalPriChoose.appendChild(btn);
  }

  modalOverlay.hidden = false;
  modalTitle.focus();
}

function closeModal() {
  modalOverlay.hidden = true;
  activeCardId = null;
  modalDraft = null;
}

async function saveModal() {
  if (!modalDraft || !activeCardId) return;
  const title = modalTitle.value.trim() || "Untitled";
  const notes = modalNotes.value;
  try {
    await updateCard(activeCardId, {
      title,
      notes,
      project:  modalDraft.project || "",
      priority: modalDraft.priority,
    });
    closeModal();
  } catch (err) {
    console.error("Failed to save card:", err);
  }
}

modalClose.addEventListener("click", closeModal);
modalCancel.addEventListener("click", closeModal);
modalSave.addEventListener("click", saveModal);
modalDelete.addEventListener("click", async () => {
  if (!activeCardId) return;
  const id = activeCardId;
  closeModal();
  await deleteCard(id);
});
modalOverlay.addEventListener("mousedown", (e) => {
  if (e.target === modalOverlay) closeModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (!modalOverlay.hidden) closeModal();
    if (!bgOverlay.hidden) closeBgPanel();
  }
});

// ── Background panel ──────────────────────────────────────────

const bgOverlay   = document.getElementById("bg-overlay");
const bgBody      = document.getElementById("bg-body");
const bgClose     = document.getElementById("bg-close");
const bgCancel    = document.getElementById("bg-cancel");
const bgApply     = document.getElementById("bg-apply");
const bgFileInput = document.getElementById("bg-file-input");
const bgToggleBtn = document.getElementById("bg-toggle");

function applyBg(settings) {
  const { type, value, fit } = settings.background || {};
  const layer = document.getElementById("bg-layer");
  if (!layer) return;

  if (type === "none" || !value) {
    layer.dataset.on = "0";
    layer.style.background = "";
    return;
  }

  let css = "";
  if (type === "url" || type === "upload") css = `url("${cssUrl(value)}")`;
  else if (type === "preset") {
    const preset = BG_PRESETS.find((p) => p.id === value);
    if (preset) css = preset.css;
  }

  if (css) {
    layer.style.background = css;
    layer.style.backgroundSize = type === "preset" ? "cover" : (fit === "contain" ? "contain" : fit === "center" ? "auto" : "cover");
    layer.style.backgroundPosition = "center";
    layer.dataset.on = "1";
  }
}

function renderBgPanel() {
  bgBody.replaceChildren();

  // mode buttons
  const modes = [
    { id: "none",   label: "None",   icon: '<path d="M5 5 15 15M15 5 5 15" /><circle cx="10" cy="10" r="7.5"/>' },
    { id: "preset", label: "Preset", icon: '<rect x="3" y="4" width="14" height="12" rx="2"/><circle cx="7.5" cy="8.5" r="1.5"/><path d="m4 14 4-3.5 4 3 3-2.5 3 2.5"/>' },
    { id: "url",    label: "URL",    icon: '<path d="M8 12a3 3 0 0 0 4.2 0l2.3-2.3a3 3 0 0 0-4.2-4.2L11 6"/><path d="M12 8a3 3 0 0 0-4.2 0L5.5 10.3a3 3 0 0 0 4.2 4.2L11 13"/>' },
    { id: "upload", label: "Upload", icon: '<path d="M10 13V4M6.5 7.5 10 4l3.5 3.5"/><path d="M4 13v2.5a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V13"/>' },
  ];

  const modesDiv = document.createElement("div");
  modesDiv.className = "bg-modes";

  for (const m of modes) {
    const btn = document.createElement("button");
    btn.className = "bg-mode";
    btn.type = "button";
    btn.dataset.on = bgDraft.mode === m.id ? "1" : "0";
    btn.innerHTML = `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${m.icon}</svg>${m.label}`;
    btn.addEventListener("click", () => {
      bgDraft.mode = m.id;
      if (m.id === "upload") bgFileInput.click();
      renderBgPanel();
    });
    modesDiv.appendChild(btn);
  }
  bgBody.appendChild(modesDiv);

  // mode-specific content
  if (bgDraft.mode === "preset") {
    const field = document.createElement("div");
    field.className = "field";
    const lbl = document.createElement("label");
    lbl.textContent = "Choose a preset";
    const grid = document.createElement("div");
    grid.className = "bg-presets";
    for (const p of BG_PRESETS) {
      const btn = document.createElement("button");
      btn.className = "bg-preset";
      btn.type = "button";
      btn.title = p.label;
      btn.dataset.on = bgDraft.value === p.id ? "1" : "0";
      btn.style.background = p.css;
      btn.addEventListener("click", () => {
        bgDraft.value = p.id;
        grid.querySelectorAll(".bg-preset").forEach((b) => {
          b.dataset.on = b === btn ? "1" : "0";
        });
      });
      grid.appendChild(btn);
    }
    field.append(lbl, grid);
    bgBody.appendChild(field);
  }

  if (bgDraft.mode === "url") {
    const field = document.createElement("div");
    field.className = "field";
    const lbl = document.createElement("label");
    lbl.textContent = "Image URL";
    const inp = document.createElement("input");
    inp.type = "text";
    inp.value = bgDraft.value || "";
    inp.placeholder = "https://…/photo.jpg";
    inp.addEventListener("input", () => { bgDraft.value = inp.value; });
    field.append(lbl, inp);
    bgBody.appendChild(field);
  }

  if (bgDraft.mode === "upload") {
    const field = document.createElement("div");
    field.className = "field";
    const lbl = document.createElement("label");
    lbl.textContent = "Uploaded image";
    const dz = document.createElement("div");
    dz.className = "drop-upload";
    if (bgDraft.uploadDataUrl) {
      const img = document.createElement("img");
      img.src = bgDraft.uploadDataUrl;
      img.style.cssText = "max-width:100%;max-height:130px;border-radius:8px";
      dz.appendChild(img);
    } else {
      dz.innerHTML = `<svg style="width:22px;height:22px;display:block;margin:0 auto 8px" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13V4M6.5 7.5 10 4l3.5 3.5"/><path d="M4 13v2.5a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V13"/></svg>Drop an image or click to browse`;
    }
    dz.addEventListener("click", () => bgFileInput.click());
    dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("over"); });
    dz.addEventListener("dragleave", () => dz.classList.remove("over"));
    dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("over"); handleBgFile(e.dataTransfer.files[0]); });
    field.append(lbl, dz);
    bgBody.appendChild(field);
  }

  // scrim slider
  if (bgDraft.mode !== "none") {
    const field = document.createElement("div");
    field.className = "field";
    const lbl = document.createElement("label");
    lbl.textContent = `Darken for legibility — ${bgDraft.scrim}%`;
    const row = document.createElement("div");
    row.className = "scrim-row";
    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = "0"; slider.max = "80"; slider.value = String(bgDraft.scrim);
    slider.addEventListener("input", () => {
      bgDraft.scrim = Number(slider.value);
      lbl.textContent = `Darken for legibility — ${bgDraft.scrim}%`;
      document.getElementById("bg-layer").style.setProperty("--bg-scrim", `rgba(12,24,36,${bgDraft.scrim / 100})`);
    });
    row.appendChild(slider);
    field.append(lbl, row);
    bgBody.appendChild(field);
  }
}

let _bgFileToken = 0;
function handleBgFile(file) {
  if (!file || !file.type.startsWith("image/")) return;
  const token = ++_bgFileToken;
  const reader = new FileReader();
  reader.onload = (ev) => {
    if (token !== _bgFileToken) return; // stale — newer selection in progress
    bgDraft.uploadDataUrl = ev.target.result;
    renderBgPanel();
  };
  reader.readAsDataURL(file);
}

bgFileInput.addEventListener("change", (e) => handleBgFile(e.target.files[0]));

function openBgPanel() {
  const bg = board.settings?.background || { type: "none", value: "", fit: "cover" };
  bgDraft = {
    mode:          bg.type === "image" ? "upload" : bg.type,
    value:         bg.value || "",
    scrim:         30,
    uploadDataUrl: bg.type === "upload" ? bg.value : "",
  };
  renderBgPanel();
  bgOverlay.hidden = false;
}

function closeBgPanel() {
  bgOverlay.hidden = true;
}

async function applyBgPanel() {
  let type  = bgDraft.mode;
  let value = bgDraft.value || "";
  let fit   = "cover";

  if (type === "upload") {
    if (!bgDraft.uploadDataUrl) { closeBgPanel(); return; }
    try {
      const blob = await fetch(bgDraft.uploadDataUrl).then((r) => r.blob());
      if (!blob.type.startsWith("image/")) throw new Error("Not an image");
      const fd = new FormData();
      fd.append("file", blob, "background" + (blob.type === "image/png" ? ".png" : ".jpg"));
      const res = await fetch("/api/upload", { method: "POST", body: fd });
      if (!res.ok) throw new Error("Upload failed");
      const { path } = await res.json();
      type = "upload"; value = path;
    } catch (err) {
      console.error(err);
      showToast("Upload failed: " + err.message);
      return;
    }
  }

  if (type === "none") value = "";

  try {
    const settings = await api("/api/board/settings", {
      method: "PATCH",
      body: JSON.stringify({ background: { type, value, fit } }),
    });
    board.settings = { background: settings.background };
    applyBg(board.settings);
    closeBgPanel();
  } catch (err) {
    console.error("Failed to apply background:", err);
  }
}

bgToggleBtn.addEventListener("click", openBgPanel);
bgClose.addEventListener("click", closeBgPanel);
bgCancel.addEventListener("click", closeBgPanel);
bgApply.addEventListener("click", applyBgPanel);
bgOverlay.addEventListener("mousedown", (e) => {
  if (e.target === bgOverlay) closeBgPanel();
});

// ── Quick-add ─────────────────────────────────────────────────

const cardForm   = document.getElementById("card-form");
const quickAddEl = document.getElementById("quick-add");
const qaPreview  = document.getElementById("qa-preview");

function renderQaPreview(raw) {
  if (!raw.trim()) { qaPreview.classList.add("hidden"); return; }
  const { title, project, priority, notes } = parseQuickAdd(raw);
  if (!title) { qaPreview.classList.add("hidden"); return; }

  const pri     = PRIORITIES[priority] || PRIORITIES[3];
  const pColor  = project ? projectColor(project) : "#7c8a99";

  qaPreview.replaceChildren();

  const lead = document.createElement("span");
  lead.className = "lead";
  lead.textContent = "Adds";

  const ttl = document.createElement("span");
  ttl.className = "ttl";
  ttl.textContent = title;

  const grow = document.createElement("span");
  grow.className = "grow";

  const projChip = document.createElement("span");
  projChip.className = "proj-chip";
  projChip.style.setProperty("--proj-color", pColor);
  projChip.innerHTML = `<i class="pj"></i>${esc(project || "(default)")}`;

  const priChip = document.createElement("span");
  priChip.className = "pri";
  priChip.style.setProperty("--pri-color", pri.color);
  priChip.innerHTML = `<i class="pdot"></i>${pri.short}`;

  const to = document.createElement("span");
  to.className = "to";
  to.textContent = "→ Backlog";

  qaPreview.append(lead, ttl, grow, projChip, priChip, to);
  qaPreview.classList.remove("hidden");
}

quickAddEl.addEventListener("input", () => renderQaPreview(quickAddEl.value));

cardForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const raw = quickAddEl.value.trim();
  if (!raw) return;
  const { title, project, priority, notes } = parseQuickAdd(raw);
  if (!title) return;

  const firstCol = board.columns[0];
  try {
    const card = await api("/api/cards", {
      method: "POST",
      body: JSON.stringify({
        title,
        notes: notes || "",
        project: project || "",
        priority,
        column: firstCol?.id || "backlog",
      }),
    });
    board.cards.push(card);
    quickAddEl.value = "";
    qaPreview.classList.add("hidden");
    render();
    showToast("Added to " + (firstCol?.title || "Backlog"));
  } catch (err) {
    console.error("Failed to add card:", err);
  }
});

// ── Filters ───────────────────────────────────────────────────

searchInput.addEventListener("input", () => {
  searchQuery = searchInput.value;
  render();
});

clearBtn.addEventListener("click", () => {
  searchQuery = "";
  projFilter.clear();
  priFilter.clear();
  searchInput.value = "";
  render();
});

// ── Theme toggle ──────────────────────────────────────────────

const themeBtn = document.getElementById("theme-toggle");
themeBtn.addEventListener("click", () => {
  const html = document.documentElement;
  html.dataset.theme = html.dataset.theme === "dark" ? "light" : "dark";
});

// ── Keyboard shortcuts ────────────────────────────────────────

document.addEventListener("keydown", (e) => {
  if (e.target.closest("input, textarea, select")) return;
  if (e.key === "/") { e.preventDefault(); searchInput.focus(); }
  if (e.key === "n") quickAddEl.focus();
});

// ── Utilities ─────────────────────────────────────────────────

function esc(str) {
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function cssUrl(str) {
  return String(str)
    .replace(/[\0-\x1F\x7F]/g, "")
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"');
}

// ── Boot ──────────────────────────────────────────────────────

async function boot() {
  board = await api("/api/board");
  if (board.settings) applyBg(board.settings);

  // apply saved theme if stored in board settings (optional extension)
  // Default is light from html attr
  render();
}

boot().catch((err) => {
  const p = document.createElement("p");
  p.style.cssText = "color:var(--p1);padding:20px";
  p.textContent = err.message;
  document.getElementById("board").appendChild(p);
});
