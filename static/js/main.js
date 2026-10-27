import { api } from "./api.js";
import { closeGhost, nextMemory, openGhost } from "./ghost.js";
import { renderAltar } from "./tree.js";

const state = {
  tree: null,
  suggestions: [],
  health: null,
  selectedId: null,
  creating: false,
};

const altar = document.getElementById("altar");
const candles = document.getElementById("candles");
const drawer = document.getElementById("drawer");
const scrim = document.getElementById("scrim");
const message = document.getElementById("story-message");

function setMessage(text, bad = false) {
  message.textContent = text || "";
  message.classList.toggle("bad", Boolean(bad));
}

function personById(id) {
  return state.tree?.people.find((person) => person.id === id) || null;
}

function statusLine(health) {
  if (!health) return "Lighting the candles…";
  const cutout =
    health.segmenter === "ready"
      ? "MediaPipe is here for photographs"
      : "colour-key cutouts (MediaPipe needs its system libraries)";
  if (health.llm === "mock") {
    return `Mock storyteller · no Gemma loaded · ${cutout}`;
  }
  if (!health.ollama_reachable) {
    return `Ollama isn't running · the altar still works · ${cutout}`;
  }
  if (!health.model_ready) {
    return `Ollama is up, but ${health.model} is not pulled yet · ${cutout}`;
  }
  return `Gemma · ${health.model} · on this computer · ${cutout}`;
}

function renderStatus() {
  document.getElementById("status").textContent = statusLine(state.health);
}

function renderCandles() {
  candles.replaceChildren();
  const lead = document.getElementById("gaps-lead");
  if (!state.suggestions.length) {
    lead.textContent = "No missing branches just now. The record is as full as the stories you have told.";
    return;
  }
  const gemma = state.suggestions.some((item) => item.source === "gemma");
  lead.textContent = gemma
    ? "Gemma rewrote these questions. The gaps themselves come from the tree."
    : "Places the record goes thin. A candle is a question for someone older, not a guess.";
  for (const item of state.suggestions) {
    const card = document.createElement("li");
    card.className = "candle-card";
    const stick = document.createElement("div");
    stick.className = "stick";
    stick.setAttribute("aria-hidden", "true");
    const flame = document.createElement("span");
    flame.className = "flame";
    stick.append(flame);
    const copy = document.createElement("div");
    const text = document.createElement("p");
    text.textContent = item.question;
    const open = document.createElement("button");
    open.type = "button";
    open.className = "text-btn";
    open.textContent = `Open ${item.person_name}`;
    open.addEventListener("click", () => openPerson(item.person_id));
    copy.append(text, open);
    card.append(stick, copy);
    candles.append(card);
  }
}

function renderTree() {
  renderAltar(altar, state.tree, { selectedId: state.selectedId, onSelect: openPerson });
}

function closeDrawer() {
  drawer.hidden = true;
  scrim.hidden = true;
  state.creating = false;
  drawer.replaceChildren();
}

function field(labelText, control) {
  const label = document.createElement("label");
  label.className = "field";
  const span = document.createElement("span");
  span.textContent = labelText;
  label.append(span, control);
  return label;
}

function input(value, attrs = {}) {
  const node = document.createElement("input");
  node.value = value ?? "";
  for (const [key, val] of Object.entries(attrs)) node.setAttribute(key, val);
  return node;
}

function relationRows(person) {
  const byId = Object.fromEntries(state.tree.people.map((item) => [item.id, item]));
  const rows = [];
  for (const id of person.parent_ids) {
    if (byId[id]) rows.push({ kind: "parent", other: byId[id], label: `Parent · ${byId[id].name}` });
  }
  for (const id of person.spouse_ids) {
    if (byId[id]) rows.push({ kind: "spouse", other: byId[id], label: `Spouse · ${byId[id].name}` });
  }
  for (const id of person.sibling_ids) {
    if (byId[id]) rows.push({ kind: "sibling", other: byId[id], label: `Sibling · ${byId[id].name}` });
  }
  for (const other of state.tree.people) {
    if (other.parent_ids.includes(person.id)) {
      rows.push({ kind: "child", other, label: `Child · ${other.name}` });
    }
  }
  return rows;
}

function renderDrawer() {
  drawer.replaceChildren();
  const person = state.creating ? null : personById(state.selectedId);
  if (!state.creating && !person) {
    closeDrawer();
    return;
  }
  drawer.hidden = false;
  scrim.hidden = false;

  const top = document.createElement("div");
  top.className = "drawer-top";
  const close = document.createElement("button");
  close.type = "button";
  close.className = "text-btn";
  close.textContent = "Close";
  close.addEventListener("click", closeDrawer);
  top.append(close);
  drawer.append(top);

  const title = document.createElement("h2");
  title.id = "drawer-title";
  title.textContent = person ? person.name : "Someone new";
  drawer.append(title);

  if (person) {
    const portrait = document.createElement("div");
    portrait.className = "portrait-edit";
    const frame = document.createElement("div");
    frame.className = "frame";
    if (person.photo_url) {
      const img = document.createElement("img");
      img.src = `${person.photo_url}?v=${person.photo_mtime || 0}`;
      img.alt = "";
      frame.append(img);
    } else {
      const mono = document.createElement("div");
      mono.className = "monogram";
      mono.textContent = person.name.slice(0, 1);
      frame.append(mono);
    }
    const file = document.createElement("input");
    file.type = "file";
    file.accept = "image/*";
    file.addEventListener("change", async () => {
      const chosen = file.files && file.files[0];
      if (!chosen) return;
      try {
        const updated = await api.uploadPhoto(person.id, chosen);
        replacePerson(updated);
        setMessage(`Photograph kept for ${updated.name}.`);
        renderTree();
        renderDrawer();
      } catch (error) {
        setMessage(error.message, true);
      }
    });
    const fileLabel = field("Photograph", file);
    portrait.append(frame, fileLabel);
    drawer.append(portrait);

    const sit = document.createElement("button");
    sit.type = "button";
    sit.className = "btn solid";
    sit.textContent = "Sit with them";
    sit.disabled = !person.photo_url;
    sit.addEventListener("click", () => openGhost(person));
    drawer.append(sit);
    if (!person.photo_url) {
      const hint = document.createElement("p");
      hint.className = "fine";
      hint.textContent = "Add a photograph to bring them into the room.";
      drawer.append(hint);
    }
  }

  const form = document.createElement("form");
  const name = input(person?.name || "", { required: "true", maxlength: "80" });
  const origin = input(person?.origin || "", { maxlength: "80" });
  const birth = input(person?.birth_year ?? "", { type: "number", min: "1800", max: "2100" });
  const death = input(person?.death_year ?? "", { type: "number", min: "1800", max: "2100" });
  const gender = document.createElement("select");
  for (const [value, label] of [
    ["", "Leave unsaid"],
    ["female", "She / her"],
    ["male", "He / him"],
  ]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    if ((person?.gender || "") === value) option.selected = true;
    gender.append(option);
  }
  const bio = document.createElement("textarea");
  bio.rows = 3;
  bio.value = person?.bio || "";
  form.append(
    field("Name", name),
    field("Where they were from", origin),
    (() => {
      const wrap = document.createElement("div");
      wrap.className = "field row";
      wrap.append(field("Birth year", birth), field("Death year", death));
      return wrap;
    })(),
    field("Words for them, if you want the questions to use she or he", gender),
    field("A line about them", bio),
  );

  const memoriesWrap = document.createElement("div");
  const memoriesTitle = document.createElement("h3");
  memoriesTitle.textContent = "Memories";
  const list = document.createElement("ul");
  list.className = "memory-list";
  const memories = [...(person?.memories || [])];
  const drawMemories = () => {
    list.replaceChildren();
    memories.forEach((memory, index) => {
      const item = document.createElement("li");
      const text = document.createElement("span");
      text.textContent = memory;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "text-btn";
      remove.textContent = "Remove";
      remove.addEventListener("click", () => {
        memories.splice(index, 1);
        drawMemories();
      });
      item.append(text, remove);
      list.append(item);
    });
  };
  drawMemories();
  const memoryInput = input("", { placeholder: "One small story", maxlength: "400" });
  const addMemory = document.createElement("button");
  addMemory.type = "button";
  addMemory.className = "btn ghost";
  addMemory.textContent = "Keep this memory";
  addMemory.addEventListener("click", () => {
    const text = memoryInput.value.trim();
    if (!text) return;
    memories.push(text);
    memoryInput.value = "";
    drawMemories();
  });
  memoriesWrap.append(memoriesTitle, list, field("Add a memory", memoryInput), addMemory);
  form.append(memoriesWrap);

  const actions = document.createElement("div");
  actions.className = "drawer-actions";
  const save = document.createElement("button");
  save.type = "submit";
  save.className = "btn solid";
  save.textContent = person ? "Save" : "Place them on the altar";
  actions.append(save);
  if (person) {
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "btn ghost danger";
    remove.textContent = "Take them off the altar";
    remove.addEventListener("click", async () => {
      if (!confirm(`Take ${person.name} off the altar?`)) return;
      try {
        await api.deletePerson(person.id);
        state.selectedId = null;
        closeDrawer();
        await reload();
        setMessage(`${person.name} is no longer on the altar.`);
      } catch (error) {
        setMessage(error.message, true);
      }
    });
    actions.append(remove);
  }
  form.append(actions);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = {
      name: name.value.trim(),
      origin: origin.value.trim() || null,
      birth_year: birth.value ? Number(birth.value) : null,
      death_year: death.value ? Number(death.value) : null,
      gender: gender.value || null,
      bio: bio.value.trim(),
      memories,
    };
    if (!body.name) {
      setMessage("They need a name.", true);
      return;
    }
    try {
      if (person) {
        const updated = await api.updatePerson(person.id, body);
        replacePerson(updated);
        setMessage(`Saved ${updated.name}.`);
        renderTree();
        renderCandlesFromServer();
        renderDrawer();
      } else {
        const created = await api.createPerson(body);
        state.creating = false;
        state.selectedId = created.id;
        await reload();
        openPerson(created.id);
        setMessage(`${created.name} is on the altar.`);
      }
    } catch (error) {
      setMessage(error.message, true);
    }
  });
  drawer.append(form);

  if (!person) return;

  const relTitle = document.createElement("h3");
  relTitle.textContent = "How they are tied in";
  const relList = document.createElement("ul");
  relList.className = "links-edit";
  for (const row of relationRows(person)) {
    const item = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = row.label;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "text-btn";
    remove.textContent = "Unlink";
    remove.addEventListener("click", async () => {
      try {
        state.tree = await api.removeRelation(person.id, { kind: row.kind, other_id: row.other.id });
        renderTree();
        renderCandlesFromServer();
        renderDrawer();
      } catch (error) {
        setMessage(error.message, true);
      }
    });
    item.append(label, remove);
    relList.append(item);
  }
  const add = document.createElement("div");
  add.className = "add-rel";
  const kind = document.createElement("select");
  for (const [value, label] of [
    ["parent", "Add a parent"],
    ["child", "Add a child"],
    ["spouse", "Add a spouse"],
    ["sibling", "Add a sibling"],
  ]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    kind.append(option);
  }
  const other = document.createElement("select");
  for (const candidate of state.tree.people.filter((item) => item.id !== person.id)) {
    const option = document.createElement("option");
    option.value = candidate.id;
    option.textContent = candidate.name;
    other.append(option);
  }
  const link = document.createElement("button");
  link.type = "button";
  link.className = "btn ghost";
  link.textContent = "Link";
  link.disabled = other.options.length === 0;
  link.addEventListener("click", async () => {
    try {
      state.tree = await api.addRelation(person.id, { kind: kind.value, other_id: other.value });
      renderTree();
      renderCandlesFromServer();
      renderDrawer();
    } catch (error) {
      setMessage(error.message, true);
    }
  });
  add.append(kind, other, link);
  drawer.append(relTitle, relList, add);
}

function replacePerson(updated) {
  state.tree.people = state.tree.people.map((person) => (person.id === updated.id ? updated : person));
}

function openPerson(id) {
  state.creating = false;
  state.selectedId = id;
  renderTree();
  renderDrawer();
}

async function renderCandlesFromServer() {
  const payload = await api.suggestions();
  state.suggestions = payload.suggestions;
  renderCandles();
  if (payload.llm === "ready") {
    api.review().then((reviewed) => {
      state.suggestions = reviewed.suggestions;
      renderCandles();
    }).catch(() => {});
  }
}

async function reload() {
  state.tree = await api.tree();
  renderTree();
  await renderCandlesFromServer();
}

document.getElementById("story-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = document.getElementById("story-text").value.trim();
  if (!text) {
    setMessage("Tell a little of the story first.", true);
    return;
  }
  const button = document.getElementById("story-submit");
  button.disabled = true;
  const original = button.textContent;
  button.textContent = "Listening…";
  setMessage("");
  try {
    const result = await api.story(text);
    state.tree = result.tree;
    renderTree();
    await renderCandlesFromServer();
    if (state.selectedId) renderDrawer();
    setMessage(result.message);
    document.getElementById("story-text").value = "";
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
});

document.getElementById("add-person").addEventListener("click", () => {
  state.creating = true;
  state.selectedId = null;
  renderTree();
  renderDrawer();
});

scrim.addEventListener("click", closeDrawer);

document.getElementById("reset").addEventListener("click", async () => {
  if (!confirm("Replace the altar with the fictional sample family? Your changes on this computer will be cleared.")) {
    return;
  }
  state.tree = await api.reset();
  state.selectedId = null;
  closeDrawer();
  renderTree();
  await renderCandlesFromServer();
  setMessage("The fictional Adeyemi ofrenda is back.");
});

document.getElementById("ghost-close").addEventListener("click", closeGhost);
document.getElementById("memory-next").addEventListener("click", nextMemory);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeGhost();
    closeDrawer();
  }
});

const boot = async () => {
  try {
    state.health = await api.health();
    renderStatus();
    await reload();
  } catch (error) {
    setMessage(error.message, true);
  }
};

boot();
