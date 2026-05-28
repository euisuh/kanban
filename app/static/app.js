const boardEl = document.querySelector("#board");
const form = document.querySelector("#card-form");
const titleInput = document.querySelector("#card-title-input");
const projectInput = document.querySelector("#card-project-input");
const priorityInput = document.querySelector("#card-priority-input");
const notesInput = document.querySelector("#card-notes-input");
const searchInput = document.querySelector("#search-input");
const projectFilter = document.querySelector("#project-filter");
const priorityFilter = document.querySelector("#priority-filter");
const columnTemplate = document.querySelector("#column-template");
const cardTemplate = document.querySelector("#card-template");
const backdrop = document.querySelector("#modal-backdrop");
const modal = document.querySelector("#modal");
const toast = document.querySelector("#toast");

let board = { settings: { background: { type: "none", value: "", fit: "cover" } }, columns: [], cards: [] };
let draggedId = null;
let activeCardId = null;
let toastTimer = null;
const modalPatchQueues = new Map();

// ── API ────────────────────────────────────────────────────────────

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

// ── Sort/filter ────────────────────────────────────────────────────

function cardsFor(columnId) {
  const query = searchInput.value.trim().toLowerCase();
  const project = projectFilter.value;
  const priority = priorityFilter.value;
  return board.cards
    .filter((c) => c.column === columnId)
    .filter((c) => !query || [c.title, c.notes, c.project].some((value) => String(value || "").toLowerCase().includes(query)))
    .filter((c) => !project || c.project === project)
    .filter((c) => !priority || String(c.priority) === priority)
    .sort((a, b) => (a.sortIndex ?? 0) - (b.sortIndex ?? 0) || a.createdAt - b.createdAt);
}

function allCardsFor(columnId) {
  return board.cards
    .filter((c) => c.column === columnId)
    .sort((a, b) => (a.sortIndex ?? 0) - (b.sortIndex ?? 0) || a.createdAt - b.createdAt);
}

// ── Render ─────────────────────────────────────────────────────────

function formatDate(ts) {
  return new Date(ts * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function formatShortDate(ts) {
  return new Date(ts * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function esc(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function projectColor(project) {
  const palette = [
    ["#e9f5ef", "#1f6d59"],
    ["#eef1fb", "#4e5fa8"],
    ["#fff1df", "#9b5a18"],
    ["#f7eaf1", "#9a3f67"],
    ["#e8f3f7", "#2d6778"],
    ["#f1edfb", "#6952a5"],
  ];
  let hash = 0;
  for (const ch of String(project)) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return palette[hash % palette.length];
}

function cssUrlValue(str) {
  return String(str)
    .replace(/[\0-\x1F\x7F]/g, "")
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"');
}

function render() {
  renderProjectFilter();
  boardEl.replaceChildren();
  board.columns.forEach((column) => {
    const node = columnTemplate.content.firstElementChild.cloneNode(true);
    const dropzone = node.querySelector(".dropzone");
    const columnCards = cardsFor(column.id);

    node.querySelector(".dot").style.background = column.accent;
    node.querySelector("h2").textContent = column.title;
    node.querySelector(".count").textContent = `${columnCards.length}/${allCardsFor(column.id).length}`;
    dropzone.dataset.column = column.id;

    dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
    dropzone.addEventListener("drop", async (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (!draggedId) return;
      try {
        await moveCard(draggedId, column.id, e.target.closest(".card")?.dataset.id || null);
      } catch (err) {
        console.error("Failed to move card:", err);
      }
    });

    columnCards.forEach((card) => dropzone.appendChild(renderCard(card)));
    if (columnCards.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-column";
      empty.textContent = "No cards";
      dropzone.appendChild(empty);
    }
    boardEl.appendChild(node);
  });
}

function renderProjectFilter() {
  const current = projectFilter.value;
  const projects = [...new Set(board.cards.map((card) => card.project).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  projectFilter.replaceChildren(new Option("All projects", ""));
  projects.forEach((project) => projectFilter.appendChild(new Option(project, project)));
  projectFilter.value = projects.includes(current) ? current : "";
}

function renderCard(card) {
  const node = cardTemplate.content.firstElementChild.cloneNode(true);
  const badge = node.querySelector(".priority-badge");
  const chip = node.querySelector(".project-chip");
  const titleEl = node.querySelector(".card-title");
  const notesEl = node.querySelector(".card-notes");
  const dateEl = node.querySelector(".card-date");
  const del = node.querySelector(".delete");

  node.dataset.id = card.id;
  badge.textContent = `p${card.priority}`;
  badge.className = `priority-badge priority-${card.priority}`;

  if (card.project) {
    chip.textContent = card.project;
    const [bg, fg] = projectColor(card.project);
    chip.style.background = bg;
    chip.style.color = fg;
    chip.style.display = "";
  } else {
    chip.style.display = "none";
    chip.style.removeProperty("background");
    chip.style.removeProperty("color");
  }

  titleEl.textContent = card.title;
  notesEl.textContent = card.notes;
  if (!card.notes) notesEl.style.display = "none";
  dateEl.textContent = `Updated ${formatShortDate(card.updatedAt || card.createdAt)}`;

  node.addEventListener("dragstart", () => { draggedId = card.id; node.classList.add("dragging"); });
  node.addEventListener("dragend", () => { draggedId = null; node.classList.remove("dragging"); });

  node.addEventListener("click", (e) => {
    if (e.target.closest(".delete")) return;
    openModal(card.id);
  });

  del.addEventListener("click", (e) => { e.stopPropagation(); deleteCard(card.id); });

  return node;
}

// ── CRUD ───────────────────────────────────────────────────────────

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

async function moveCard(id, columnId, beforeId) {
  if (beforeId === id) return;
  const card = board.cards.find((item) => item.id === id);
  if (!card) return;

  const ordered = allCardsFor(columnId).filter((item) => item.id !== id);
  const insertAt = beforeId ? ordered.findIndex((item) => item.id === beforeId) : -1;
  card.column = columnId;
  ordered.splice(insertAt >= 0 ? insertAt : ordered.length, 0, card);
  ordered.forEach((item, index) => { item.sortIndex = index; });
  render();

  await Promise.all(ordered.map((item) => updateCard(item.id, { column: item.column, sortIndex: item.sortIndex }, false)));
  render();
}

function showUndo(card) {
  if (toastTimer) clearTimeout(toastTimer);
  toast.replaceChildren();
  const label = document.createElement("span");
  label.textContent = "Card deleted";
  const undo = document.createElement("button");
  undo.type = "button";
  undo.textContent = "Undo";
  undo.addEventListener("click", async () => {
    if (toastTimer) clearTimeout(toastTimer);
    toast.classList.remove("open");
    const restored = await api("/api/cards", {
      method: "POST",
      body: JSON.stringify({
        title: card.title,
        notes: card.notes || "",
        project: card.project || "",
        priority: card.priority,
        column: card.column,
      }),
    });
    const withOrder = await updateCard(restored.id, { sortIndex: card.sortIndex ?? 0 }, false);
    board.cards.push(withOrder);
    render();
  });
  toast.append(label, undo);
  toast.classList.add("open");
  toastTimer = setTimeout(() => toast.classList.remove("open"), 6000);
}

// ── Modal ──────────────────────────────────────────────────────────

function openModal(cardId) {
  const card = board.cards.find((c) => c.id === cardId);
  if (!card) return;
  activeCardId = cardId;

  document.querySelector("#modal-title").value = card.title;
  document.querySelector("#modal-notes").value = card.notes;
  document.querySelector("#modal-project").value = card.project || "";
  document.querySelector("#modal-priority-badge").textContent = `P${card.priority}`;
  document.querySelector("#modal-priority-badge").className = `priority-badge priority-${card.priority}`;
  document.querySelector("#modal-project-chip").textContent = card.project || "";
  document.querySelector("#modal-project-chip").style.display = card.project ? "" : "none";
  document.querySelector("#modal-date").textContent = `Created ${formatDate(card.createdAt)} · Updated ${formatDate(card.updatedAt || card.createdAt)}`;

  // Priority buttons
  document.querySelectorAll(".priority-btn").forEach((btn) => {
    btn.classList.toggle("active", parseInt(btn.dataset.p) === card.priority);
  });

  // Column select
  const sel = document.querySelector("#modal-column");
  sel.innerHTML = board.columns
    .map((col) => `<option value="${esc(col.id)}"${col.id === card.column ? " selected" : ""}>${esc(col.title)}</option>`)
    .join("");

  backdrop.classList.add("open");
  document.querySelector("#modal-title").focus();
}

function closeModal() {
  backdrop.classList.remove("open");
  activeCardId = null;
}

function modalSave(patch) {
  const cardId = activeCardId;
  if (!cardId) return;
  const previous = modalPatchQueues.get(cardId) || Promise.resolve();
  const next = previous
    .catch(() => {})
    .then(() => updateCard(cardId, patch));
  modalPatchQueues.set(cardId, next);
  next
    .catch((err) => console.error("Failed to save card:", err))
    .finally(() => {
      if (modalPatchQueues.get(cardId) === next) modalPatchQueues.delete(cardId);
    });
}

// Modal event wiring
document.querySelector("#modal-close").addEventListener("click", closeModal);
backdrop.addEventListener("click", (e) => { if (e.target === backdrop) closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

document.querySelector("#modal-title").addEventListener("blur", (e) => {
  if (e.target.value.trim()) modalSave({ title: e.target.value.trim() });
});

document.querySelector("#modal-notes").addEventListener("blur", (e) => {
  modalSave({ notes: e.target.value });
});

document.querySelector("#modal-project").addEventListener("blur", (e) => {
  modalSave({ project: e.target.value.trim() });
  const chip = document.querySelector("#modal-project-chip");
  chip.textContent = e.target.value.trim();
  chip.style.display = e.target.value.trim() ? "" : "none";
});

document.querySelectorAll(".priority-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const p = parseInt(btn.dataset.p);
    document.querySelectorAll(".priority-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelector("#modal-priority-badge").textContent = `P${p}`;
    document.querySelector("#modal-priority-badge").className = `priority-badge priority-${p}`;
    modalSave({ priority: p });
  });
});

document.querySelector("#modal-column").addEventListener("change", (e) => {
  modalSave({ column: e.target.value });
});

// ── Form submit ────────────────────────────────────────────────────

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const title = titleInput.value.trim();
  const notes = notesInput.value.trim();
  const project = projectInput.value.trim();
  const priority = parseInt(priorityInput.value, 10);
  if (!title) return;
  try {
    const card = await api("/api/cards", {
      method: "POST",
      body: JSON.stringify({ title, notes, project, priority, column: board.columns[0]?.id || "backlog" }),
    });
    board.cards.push(card);
    titleInput.value = "";
    notesInput.value = "";
    projectInput.value = "";
    priorityInput.value = "4";
    titleInput.focus();
    render();
  } catch (err) {
    console.error("Failed to add card:", err);
  }
});

searchInput.addEventListener("input", render);
projectFilter.addEventListener("change", render);
priorityFilter.addEventListener("change", render);

document.addEventListener("keydown", (e) => {
  if (e.key === "/" && !e.target.closest("input, textarea, select")) {
    e.preventDefault();
    searchInput.focus();
  }
  if (e.key === "n" && !e.target.closest("input, textarea, select")) titleInput.focus();
});

// ── Background ─────────────────────────────────────────────────────

function applyBg(settings) {
  const { type, value, fit } = settings.background || {};
  if (type === "none" || !value) {
    document.body.classList.remove("has-bg-image");
    document.body.style.removeProperty("--board-bg-image");
    document.body.style.removeProperty("--board-bg-size");
  } else {
    const sizeMap = { cover: "cover", contain: "contain", center: "auto" };
    document.body.style.setProperty("--board-bg-image", `url("${cssUrlValue(value)}")`);
    document.body.style.setProperty("--board-bg-size", sizeMap[fit] || "cover");
    document.body.classList.add("has-bg-image");
  }
}

// Settings panel toggle
document.querySelector("#settings-toggle").addEventListener("click", () => {
  document.querySelector("#settings-panel").classList.toggle("open");
});

// Tab switching
document.querySelectorAll(".settings-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".settings-tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".settings-pane").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    document.querySelector(`#pane-${tab.dataset.tab}`).classList.add("active");
  });
});

// Fit buttons (both groups)
document.querySelectorAll(".settings-fit-group").forEach((group) => {
  group.querySelectorAll(".fit-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      group.querySelectorAll(".fit-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });
});

function activeFit(groupId) {
  return document.querySelector(`#${groupId} .fit-btn.active`)?.dataset.fit || "cover";
}

// File preview
document.querySelector("#bg-file").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    const img = document.querySelector("#preview-upload");
    img.src = ev.target.result;
    img.removeAttribute("hidden");
    img.classList.add("visible");
  };
  reader.readAsDataURL(file);
});

// URL preview
document.querySelector("#bg-url").addEventListener("input", (e) => {
  const img = document.querySelector("#preview-url");
  if (e.target.value.startsWith("http")) {
    img.src = e.target.value;
    img.removeAttribute("hidden");
    img.classList.add("visible");
  } else {
    img.setAttribute("hidden", "");
    img.classList.remove("visible");
  }
});

// Apply upload
document.querySelector("#apply-upload").addEventListener("click", async () => {
  const file = document.querySelector("#bg-file").files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  let uploadResult;
  try {
    const res = await fetch("/api/upload", { method: "POST", body: fd });
    if (!res.ok) { alert("Upload failed"); return; }
    uploadResult = await res.json();
  } catch (err) {
    alert("Upload failed: " + err.message);
    return;
  }
  const { path } = uploadResult;
  const fit = activeFit("fit-group-upload");
  try {
    const settings = await api("/api/board/settings", {
      method: "PATCH",
      body: JSON.stringify({ background: { type: "upload", value: path, fit } }),
    });
    board.settings = { background: settings.background };
    applyBg(board.settings);
    document.querySelector("#settings-panel").classList.remove("open");
  } catch (err) {
    alert("Failed to apply background: " + err.message);
  }
});

// Apply URL
document.querySelector("#apply-url").addEventListener("click", async () => {
  const value = document.querySelector("#bg-url").value.trim();
  if (!value.startsWith("http")) { alert("Enter a valid URL starting with http"); return; }
  const fit = activeFit("fit-group-url");
  try {
    const settings = await api("/api/board/settings", {
      method: "PATCH",
      body: JSON.stringify({ background: { type: "url", value, fit } }),
    });
    board.settings = { background: settings.background };
    applyBg(board.settings);
    document.querySelector("#settings-panel").classList.remove("open");
  } catch (err) {
    alert("Failed to apply background: " + err.message);
  }
});

// Apply none
document.querySelector("#apply-none").addEventListener("click", async () => {
  try {
    const settings = await api("/api/board/settings", {
      method: "PATCH",
      body: JSON.stringify({ background: { type: "none", value: "", fit: "cover" } }),
    });
    board.settings = { background: settings.background };
    applyBg(board.settings);
    document.querySelector("#settings-panel").classList.remove("open");
  } catch (err) {
    alert("Failed to apply background: " + err.message);
  }
});

// ── Boot ───────────────────────────────────────────────────────────

async function boot() {
  board = await api("/api/board");
  if (board.settings) applyBg(board.settings);
  render();
}

boot().catch((err) => {
  const p = document.createElement("p");
  p.style.cssText = "color:red;padding:20px";
  p.textContent = err.message;
  boardEl.appendChild(p);
});
