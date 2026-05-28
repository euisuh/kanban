const boardEl = document.querySelector("#board");
const form = document.querySelector("#card-form");
const columnTemplate = document.querySelector("#column-template");
const cardTemplate = document.querySelector("#card-template");

let board = { columns: [], cards: [] };
let draggedId = null;

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

function cardsFor(columnId) {
  return board.cards.filter((card) => card.column === columnId);
}

function render() {
  boardEl.replaceChildren();

  board.columns.forEach((column) => {
    const node = columnTemplate.content.firstElementChild.cloneNode(true);
    const dropzone = node.querySelector(".dropzone");
    const columnCards = cardsFor(column.id);

    node.querySelector(".dot").style.background = column.accent;
    node.querySelector("h2").textContent = column.title;
    node.querySelector(".count").textContent = columnCards.length;
    dropzone.dataset.column = column.id;

    dropzone.addEventListener("dragover", (event) => {
      event.preventDefault();
      dropzone.classList.add("dragover");
    });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
    dropzone.addEventListener("drop", async (event) => {
      event.preventDefault();
      dropzone.classList.remove("dragover");
      if (!draggedId) return;
      await updateCard(draggedId, { column: column.id });
    });

    columnCards.forEach((card) => dropzone.appendChild(renderCard(card)));
    boardEl.appendChild(node);
  });
}

function renderCard(card) {
  const node = cardTemplate.content.firstElementChild.cloneNode(true);
  const title = node.querySelector(".card-title");
  const notes = node.querySelector(".card-notes");
  const del = node.querySelector(".delete");

  node.dataset.id = card.id;
  title.value = card.title;
  notes.value = card.notes;
  title.setAttribute("aria-label", "Card title");
  notes.setAttribute("aria-label", "Card notes");

  node.addEventListener("dragstart", () => {
    draggedId = card.id;
    node.classList.add("dragging");
  });
  node.addEventListener("dragend", () => {
    draggedId = null;
    node.classList.remove("dragging");
  });

  title.addEventListener("change", () => updateCard(card.id, { title: title.value }));
  notes.addEventListener("change", () => updateCard(card.id, { notes: notes.value }));
  del.addEventListener("click", () => deleteCard(card.id));

  return node;
}

async function updateCard(id, patch) {
  const updated = await api(`/api/cards/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
  board.cards = board.cards.map((card) => (card.id === id ? updated : card));
  render();
}

async function deleteCard(id) {
  await api(`/api/cards/${encodeURIComponent(id)}`, { method: "DELETE" });
  board.cards = board.cards.filter((card) => card.id !== id);
  render();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(form);
  const card = await api("/api/cards", {
    method: "POST",
    body: JSON.stringify({
      title: data.get("title"),
      notes: data.get("notes"),
      column: board.columns[0]?.id || "backlog",
    }),
  });
  board.cards.push(card);
  form.reset();
  render();
});

async function boot() {
  board = await api("/api/board");
  render();
}

boot().catch((error) => {
  boardEl.innerHTML = `<p class="error">${error.message}</p>`;
});
