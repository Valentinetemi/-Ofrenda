async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: options.body && !(options.body instanceof FormData) ? { "Content-Type": "application/json" } : undefined,
    ...options,
  });
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!response.ok) {
    const detail = data && data.detail ? data.detail : `Request failed (${response.status})`;
    const error = new Error(typeof detail === "string" ? detail : "Something went wrong.");
    error.status = response.status;
    throw error;
  }
  return data;
}

export const api = {
  health: () => request("/api/health"),
  tree: () => request("/api/tree"),
  suggestions: () => request("/api/suggestions"),
  review: () => request("/api/suggestions/review", { method: "POST" }),
  story: (text) => request("/api/stories", { method: "POST", body: JSON.stringify({ text }) }),
  createPerson: (body) => request("/api/people", { method: "POST", body: JSON.stringify(body) }),
  updatePerson: (id, body) => request(`/api/people/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deletePerson: (id) => request(`/api/people/${id}`, { method: "DELETE" }),
  addRelation: (id, body) => request(`/api/people/${id}/relationships`, { method: "POST", body: JSON.stringify(body) }),
  removeRelation: (id, body) =>
    request(`/api/people/${id}/relationships`, { method: "DELETE", body: JSON.stringify(body) }),
  uploadPhoto: (id, file) => {
    const body = new FormData();
    body.append("file", file);
    return request(`/api/people/${id}/photo`, { method: "POST", body });
  },
  motion: () => request("/api/ghost/motion"),
  reset: () => request("/api/reset", { method: "POST" }),
};
