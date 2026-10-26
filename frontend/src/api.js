import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export const api = axios.create({ baseURL: API_BASE });

export const mediaUrl = (kind, filename) =>
  `${API_BASE}/media/${kind}/${filename}`;

export const fetchStats = () => api.get("/stats").then((r) => r.data);

export const fetchProjects = (params = {}) =>
  api.get("/projects", { params }).then((r) => r.data);

export const fetchFlagged = (minLevel = "medium") =>
  api.get("/projects/flagged", { params: { min_level: minLevel } }).then((r) => r.data);

export const fetchProjectDetail = (id) =>
  api.get(`/projects/${id}`).then((r) => r.data);

export const submitProgress = (formData) =>
  api.post("/submissions", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then((r) => r.data);
