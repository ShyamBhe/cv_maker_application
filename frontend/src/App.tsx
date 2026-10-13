import { useEffect, useRef, useState, type ChangeEvent } from "react";
import sample from "./sample.json";
import Editor, { blankItem } from "./Editor";
import { api, session, type CV, type User, type AdminUser } from "./api";

const blank = (): CV => ({ name: "", title: "", email: "", phone: "", website: "", linkedin: "", template: "sidebar", color: "#5b9ac6", font: "sans", sections: [
  { title: "Profile", kind: "text", text: "", items: [] }, { title: "Employment", kind: "entries", text: "", items: [blankItem()] },
  { title: "Education", kind: "entries", text: "", items: [blankItem()] }, { title: "Skills", kind: "skills", text: "", items: [blankItem()] },
  { title: "Languages", kind: "list", text: "", items: [] }] });
const loadDraft = (): CV | null => { try { const d = localStorage.getItem("draft"); return d ? JSON.parse(d) : null; } catch { return null; } };

function Auth({ onDone, onClose }: { onDone: (u: User) => void; onClose: () => void }) {
  const [reg, setReg] = useState(true); const [f, setF] = useState({ email: "", name: "", pw: "" }); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true); setErr("");
    try { const r = reg ? await api.register(f.email, f.name, f.pw) : await api.login(f.email, f.pw); session.set(r.token, r.user); onDone(r.user); }
    catch (e) { setErr((e as Error).message); setBusy(false); }
  };
  return (<div className="overlay" role="dialog" aria-modal="true" aria-label="Log in or register"><div className="auth">
    <button className="link x" onClick={onClose} aria-label="Close">✕</button>
    <h2>{reg ? "Create a free account" : "Log in"}</h2>
    <p className="muted">An account is needed to download your CV as a PDF. Your CV is saved to your account, and site administrators can view it.</p>
    {reg && <label>Full name<input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></label>}
    <label>Email<input type="email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} /></label>
    <label>Password (10+ characters)<input type="password" value={f.pw} onChange={e => setF({ ...f, pw: e.target.value })} /></label>
    {err && <p className="err" role="alert">{err}</p>}
    <button disabled={busy} onClick={submit}>{reg ? "Register and download" : "Log in and download"}</button>
    <button className="link" onClick={() => { setReg(!reg); setErr(""); }}>{reg ? "I already have an account" : "Create an account"}</button></div></div>);
}

function Admin() {
  const [users, setUsers] = useState<AdminUser[]>([]); const [sel, setSel] = useState<AdminUser | null>(null); const [cv, setCv] = useState<CV>(blank());
  useEffect(() => { api.users().then(setUsers); }, []);
  const open = async (u: AdminUser) => { setSel(u); setCv(await api.userCv(u.id)); };
  return (<div className="admin"><table><thead><tr><th>Name</th><th>Email</th><th>Joined</th><th>CV</th></tr></thead><tbody>
    {users.map(u => (<tr key={u.id} className={sel?.id === u.id ? "on" : ""}><td>{u.full_name}</td><td>{u.email}</td><td>{u.created_at.slice(0, 10)}</td>
      <td>{u.has_cv ? <button className="link" onClick={() => open(u)}>View CV</button> : <span className="muted">None yet</span>}</td></tr>))}</tbody></table>
    {sel && <section><div className="bar"><h2>{sel.full_name}'s CV</h2><button onClick={() => api.download(`/admin/users/${sel.id}/cv/pdf`)}>Download PDF</button></div>
      <Editor cv={cv} setCv={setCv} readOnly /></section>}</div>);
}

export default function App() {
  const [user, setUser] = useState<User | null>(session.user); const [cv, setCv] = useState<CV>(() => loadDraft() ?? blank());
  const [hadDraft] = useState(() => !!loadDraft()); const [tab, setTab] = useState<"cv" | "admin">("cv");
  const [authOpen, setAuthOpen] = useState(false); const [msg, setMsg] = useState(""); const [url, setUrl] = useState(""); const wantDownload = useRef(false);
  const fileRef = useRef<HTMLInputElement>(null); const [note, setNote] = useState("");

  function logout() { session.clear(); localStorage.removeItem("draft"); setUser(null); setCv(blank()); setTab("cv"); }
  useEffect(() => { localStorage.setItem("draft", JSON.stringify(cv)); }, [cv]);
  useEffect(() => { if (user && !hadDraft) api.getCv().then(c => c.sections.length && setCv(c)).catch(() => { session.clear(); setUser(null); }); }, []);
  useEffect(() => {  // live (watermarked) preview, refreshed shortly after the last edit
    let live = true;
    const t = setTimeout(async () => {
      try { const b = await api.preview(cv); if (live) { setUrl(u => { if (u) URL.revokeObjectURL(u); return URL.createObjectURL(b); }); setMsg(""); } }
      catch (e) { if (live) setMsg((e as Error).message); }
    }, 900);
    return () => { live = false; clearTimeout(t); };
  }, [cv]);

  const onUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; e.target.value = ""; if (!f) return;
    if ((cv.name || cv.sections.some(s => s.text || s.items.some(i => i.title))) && !window.confirm("Replace what you have with the content of this PDF?")) return;
    setNote("Reading your PDF…");
    try { const p = await api.parse(f); setCv({ ...p, template: cv.template, color: cv.color, font: cv.font }); setNote("Imported. Please check each section: automatic reading is never perfect."); }
    catch (err) { setNote((err as Error).message); }
  };
  const persistAndDownload = async () => {
    try { setMsg("Preparing your PDF…"); await api.saveCv(cv); await api.download("/cv/pdf"); setMsg("Downloaded ✓ (saved to your account)"); }
    catch (e) { const m = (e as Error).message; if (/token|User not found/i.test(m)) { session.clear(); setUser(null); wantDownload.current = true; setAuthOpen(true); } else setMsg(m); }
  };
  const download = () => { wantDownload.current = true; session.token ? persistAndDownload() : setAuthOpen(true); };
  const authed = async (u: User) => {
    setUser(u); setAuthOpen(false);
    if (wantDownload.current) { wantDownload.current = false; persistAndDownload(); }
    else { const c = await api.getCv().catch(() => null); if (c && c.sections.length) setCv(c); }
  };

  return (<div className="app"><header><strong>CV Maker</strong><nav>
    {user?.role === "admin" && <button className="link" onClick={() => setTab(tab === "cv" ? "admin" : "cv")}>{tab === "cv" ? "Admin: all users" : "Back to my CV"}</button>}
    {user ? <><span className="muted">{user.email}</span><button className="link" onClick={logout}>Log out</button></> : <button className="link" onClick={() => setAuthOpen(true)}>Log in</button>}</nav></header>
    {authOpen && <Auth onClose={() => { setAuthOpen(false); wantDownload.current = false; }} onDone={authed} />}
    <main>{tab === "admin" ? <Admin /> : <div className="layout"><div>
      <div className="bar"><h2>Build your CV</h2><div><input ref={fileRef} type="file" accept="application/pdf" hidden onChange={onUpload} /><button className="ghost" onClick={() => fileRef.current?.click()}>Upload PDF CV</button><button className="ghost" onClick={() => setCv(sample as unknown as CV)}>Load sample</button>
        <button className="ghost" onClick={() => window.confirm("Clear everything and start over?") && setCv(blank())}>Start over</button></div></div>
      <p className="muted" role="status">{note || "Already have a CV? Upload it as a PDF and the form fills itself in (the file is not stored)."}</p>
      <Editor cv={cv} setCv={setCv} /></div>
      <aside><div className="bar"><h2>Preview</h2><button onClick={download}>Download PDF</button></div>
        <p className="muted" role="status">{msg || "Free to build. Registration is only needed to download the clean PDF."}</p>
        {url && <iframe title="CV preview" src={url} />}</aside></div>}</main></div>);
}
