/**
 * Lay the altar out by generation.
 * Elders sit on the top shelf. Spouses stand beside each other.
 * Lines are drawn after layout, from parents down to a child.
 */

function generationOf(people) {
  const gen = new Map(people.map((person) => [person.id, 0]));
  for (let pass = 0; pass < people.length + 2; pass += 1) {
    let changed = false;
    for (const person of people) {
      for (const parentId of person.parent_ids) {
        if (!gen.has(parentId)) continue;
        const next = gen.get(parentId) + 1;
        if (next > gen.get(person.id)) {
          gen.set(person.id, next);
          changed = true;
        }
      }
    }
    for (const person of people) {
      if (person.parent_ids.length) continue;
      let target = gen.get(person.id);
      for (const otherId of [...person.spouse_ids, ...person.sibling_ids]) {
        if (gen.has(otherId) && gen.get(otherId) > target) target = gen.get(otherId);
      }
      if (target !== gen.get(person.id)) {
        gen.set(person.id, target);
        changed = true;
      }
    }
    if (!changed) break;
  }
  return gen;
}

function parentScore(person, parentPos) {
  const scores = person.parent_ids.map((id) => parentPos.get(id)).filter((score) => score != null);
  if (!scores.length) return null;
  return scores.reduce((sum, score) => sum + score, 0) / scores.length;
}

function layoutRows(people) {
  if (!people.length) return [];
  const gen = generationOf(people);
  const maxGen = Math.max(...gen.values());
  const rows = [];
  let parentPos = new Map();
  for (let level = 0; level <= maxGen; level += 1) {
    const members = people.filter((person) => gen.get(person.id) === level);
    const seen = new Set();
    const units = [];
    for (const person of members) {
      if (seen.has(person.id)) continue;
      const spouse = members.find((other) => person.spouse_ids.includes(other.id) && !seen.has(other.id));
      const unit = spouse ? [person, spouse] : [person];
      unit.forEach((item) => seen.add(item.id));
      unit.sort((a, b) => {
        const left = parentScore(a, parentPos);
        const right = parentScore(b, parentPos);
        if (left == null && right != null) return 1;
        if (right == null && left != null) return -1;
        return (a.birth_year || 9999) - (b.birth_year || 9999);
      });
      const scores = unit.map((item) => parentScore(item, parentPos)).filter((score) => score != null);
      const birth = Math.min(...unit.map((item) => item.birth_year || 9999));
      const key = scores.length ? Math.min(...scores) : 1000 + birth;
      units.push({ unit, key, birth });
    }
    units.sort((a, b) => a.key - b.key || a.birth - b.birth);
    const row = units.flatMap((item) => item.unit);
    rows.push(row);
    parentPos = new Map(row.map((person, index) => [person.id, index]));
  }
  return rows;
}

function yearsOf(person) {
  if (person.birth_year && person.death_year) return `${person.birth_year} – ${person.death_year}`;
  if (person.birth_year) return `${person.birth_year} –`;
  if (person.death_year) return `died ${person.death_year}`;
  return "";
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key === "class") node.className = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) node.append(child);
  return node;
}

function nicho(person, narratorId, selectedId, onSelect) {
  const frameChildren = [];
  if (person.photo_url) {
    const img = el("img", {
      src: `${person.photo_url}?v=${person.photo_mtime || 0}`,
      alt: `Portrait of ${person.name}`,
    });
    frameChildren.push(img);
  } else {
    frameChildren.push(el("span", { class: "monogram" }, [person.name.slice(0, 1)]));
  }
  const button = el(
    "button",
    {
      class: `nicho${person.id === selectedId ? " selected" : ""}`,
      type: "button",
      "data-id": person.id,
    },
    [
      el("span", { class: "candle", "aria-hidden": "true" }, [el("span", { class: "flame" })]),
      el("span", { class: "frame" }, frameChildren),
      el("span", { class: "pname" }, [person.name]),
    ],
  );
  const years = yearsOf(person);
  if (years) button.append(el("span", { class: "pyears" }, [years]));
  if (person.id === narratorId) button.append(el("span", { class: "keeper" }, ["keeper of the altar"]));
  button.addEventListener("click", () => onSelect(person.id));
  return button;
}

function drawLinks(root) {
  const svg = root.querySelector("svg.links");
  if (!svg) return;
  svg.setAttribute("width", String(root.scrollWidth));
  svg.setAttribute("height", String(root.scrollHeight));
  svg.replaceChildren();
  const box = root.getBoundingClientRect();
  const place = (node) => {
    const rect = node.getBoundingClientRect();
    return {
      cx: rect.left - box.left + root.scrollLeft + rect.width / 2,
      top: rect.top - box.top + root.scrollTop,
      bottom: rect.bottom - box.top + root.scrollTop,
    };
  };
  for (const card of root.querySelectorAll(".nicho")) {
    const personId = card.getAttribute("data-id");
    const person = root._peopleById?.[personId];
    if (!person || !person.parent_ids.length) continue;
    const parents = person.parent_ids
      .map((id) => root.querySelector(`.nicho[data-id="${CSS.escape(id)}"]`))
      .filter(Boolean)
      .map(place);
    if (!parents.length) continue;
    const child = place(card);
    const x = parents.reduce((sum, point) => sum + point.cx, 0) / parents.length;
    const y = Math.max(...parents.map((point) => point.bottom));
    const mid = (y + child.top) / 2;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", `M ${x} ${y} C ${x} ${mid}, ${child.cx} ${mid}, ${child.cx} ${child.top}`);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "rgba(228, 162, 58, 0.55)");
    path.setAttribute("stroke-width", "1.5");
    svg.append(path);
  }
}

export function renderAltar(root, tree, { selectedId, onSelect }) {
  root._peopleById = Object.fromEntries(tree.people.map((person) => [person.id, person]));
  root.replaceChildren();
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "links");
  svg.setAttribute("aria-hidden", "true");
  root.append(svg);
  if (!tree.people.length) {
    root.append(el("p", { class: "empty" }, ["The altar is quiet. Tell a story to light the first candle."]));
    return;
  }
  for (const row of layoutRows(tree.people)) {
    const shelf = el("div", { class: "shelf" });
    for (const person of row) shelf.append(nicho(person, tree.narrator_id, selectedId, onSelect));
    root.append(shelf);
  }
  const redraw = () => drawLinks(root);
  requestAnimationFrame(redraw);
  if (root._onResize) window.removeEventListener("resize", root._onResize);
  root._onResize = () => requestAnimationFrame(redraw);
  window.addEventListener("resize", root._onResize);
}
