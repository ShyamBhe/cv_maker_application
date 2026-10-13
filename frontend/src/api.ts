export type Item = { title: string; subtitle: string; period: string; bullets: string[]; level: number };
export type Kind = "text" | "entries" | "skills" | "list";
export type Section = { title: string; kind: Kind; text: string; items: Item[] };
export type CV = { name: string; title: string; email: string; phone: string; website: string; linkedin: string;
  template: "sidebar" | "classic" | "modern"; color: string; font: "sans" | "serif"; sections: Section[] };
export type User = { id: number; email: string; full_name: string; role: string };
export type AdminUser = User & { created_at: string; has_cv: boolean; cv_updated_at: string | null };

export const session = {
  get token() { return localStorage.getItem("token"); },
  set(t: string, u: User) { localStorage.setItem("token", t); localStorage.setItem("user", JSON.stringify(u)); },
  clear() { localStorage.removeItem("token"); localStorage.removeItem("user"); },
  get user(): User | null { const u = localStorage.getItem("user"); return u ? JSON.parse(u) : null; },
};

async function call(path: string, init: RequestInit = {}) {
  const r = await fetch("/api" + path, { ...init, headers: { "Content-Type": "application/json",
    ...(session.token ? { Authorization: `Bearer ${session.token}` } : {}) }, body: init.body });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(typeof e.detail === "string" ? e.detail : "Request failed"); }
  return r;
}
const json = async <T,>(p: string, i?: RequestInit) => (await call(p, i)).json() as Promise<T>;

export const api = {
  login: (email: string, password: string) => json<{ token: string; user: User }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (email: string, full_name: string, password: string) => json<{ token: string; user: User }>("/auth/register", { method: "POST", body: JSON.stringify({ email, full_name, password }) }),
  async preview(cv: CV) { return (await call("/preview", { method: "POST", body: JSON.stringify(cv) })).blob(); },
  async parse(file: File) {
    const f = new FormData(); f.append("file", file);
    const r = await fetch("/api/parse", { method: "POST", body: f });
    if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(typeof e.detail === "string" ? e.detail : "Could not read this PDF"); }
    return (await r.json()) as CV;
  },
  getCv: () => json<CV>("/cv"),
  saveCv: (cv: CV) => json<CV>("/cv", { method: "PUT", body: JSON.stringify(cv) }),
  users: () => json<AdminUser[]>("/admin/users"),
  userCv: (id: number) => json<CV>(`/admin/users/${id}/cv`),
  async download(path: string) {
    const blob = await (await call(path)).blob(); const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "cv.pdf"; a.click(); URL.revokeObjectURL(a.href);
  },
};
