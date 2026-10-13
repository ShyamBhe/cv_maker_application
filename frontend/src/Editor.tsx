import type { CV, Item, Kind, Section } from "./api";

const COLORS = ["#5b9ac6", "#2e7d6b", "#b5483a", "#6b4fa0", "#c78a1a", "#2b2f33"];
const KINDS: Record<Kind, string> = {
  entries: "Entries with bullet points (jobs, projects, courses)", text: "Text paragraph",
  skills: "Skills with level dots", list: "Simple list (languages, hobbies)" };
export const blankItem = (): Item => ({ title: "", subtitle: "", period: "", bullets: [], level: 4 });

export default function Editor({ cv, setCv, readOnly }: { cv: CV; setCv: (c: CV) => void; readOnly?: boolean }) {
  const set = (p: Partial<CV>) => setCv({ ...cv, ...p });
  const setSec = (i: number, p: Partial<Section>) => set({ sections: cv.sections.map((s, n) => (n === i ? { ...s, ...p } : s)) });
  const setItem = (i: number, j: number, p: Partial<Item>) => setSec(i, { items: cv.sections[i].items.map((x, n) => (n === j ? { ...x, ...p } : x)) });
  const move = (i: number, d: number) => { const a = [...cv.sections], j = i + d; if (j < 0 || j >= a.length) return; [a[i], a[j]] = [a[j], a[i]]; set({ sections: a }); };
  const F = (label: string, value: string, on: (v: string) => void, rows = 0) => (
    <label>{label}{rows ? <textarea rows={rows} disabled={readOnly} value={value} onChange={e => on(e.target.value)} />
      : <input disabled={readOnly} value={value} onChange={e => on(e.target.value)} />}</label>);
  const top = (k: "name" | "title" | "email" | "phone" | "website" | "linkedin", label: string) => F(label, cv[k], v => set({ [k]: v } as Partial<CV>));
  const addSection = (kind: Kind) => set({ sections: [...cv.sections, { title: "New section", kind, text: "", items: kind === "entries" || kind === "skills" ? [blankItem()] : [] }] });

  const convert = (i: number, k: Kind) => {  // switch a section's type without losing its content
    const s = cv.sections[i]; let text = s.text, items = s.items;
    if (s.kind === "list" && k === "skills") items = text.split("\n").filter(x => x.trim()).map(t => ({ ...blankItem(), title: t }));
    if (s.kind === "skills" && k === "list") text = items.map(x => x.title).join("\n");
    if ((k === "entries" || k === "skills") && !items.length) items = [blankItem()];
    setSec(i, { kind: k, text, items });
  };
  return (<div className="form">
    {!readOnly && <fieldset><legend>Design</legend>
      <div className="row"><span>Template</span>{(["sidebar", "classic", "modern"] as const).map(t =>
        <button key={t} className={cv.template === t ? "pick on" : "pick"} onClick={() => set({ template: t })}>{t[0].toUpperCase() + t.slice(1)}</button>)}</div>
      <div className="row"><span>Colour</span>{COLORS.map(c => <button key={c} aria-label={`Colour ${c}`} className={cv.color === c ? "sw on" : "sw"} style={{ background: c }} onClick={() => set({ color: c })} />)}
        <input type="color" className="cp" aria-label="Custom colour" value={cv.color} onChange={e => set({ color: e.target.value })} />
        <select aria-label="Font" value={cv.font} onChange={e => set({ font: e.target.value as CV["font"] })}><option value="sans">Sans-serif font</option><option value="serif">Serif font</option></select></div></fieldset>}
    <div className="grid">{top("name", "Full name")}{top("title", "Job title")}{top("email", "Email")}{top("phone", "Phone")}{top("website", "Website")}{top("linkedin", "LinkedIn")}</div>
    {cv.sections.map((s, i) => (<fieldset key={i}>
      <div className="bar">{F("Section title", s.title, v => setSec(i, { title: v }))}
        {!readOnly && <div className="ctl"><button className="link" aria-label="Move up" onClick={() => move(i, -1)}>↑</button><button className="link" aria-label="Move down" onClick={() => move(i, 1)}>↓</button>
          <button className="link" onClick={() => set({ sections: cv.sections.filter((_, n) => n !== i) })}>Delete section</button></div>}</div>
      {!readOnly && <label>Section type<select value={s.kind} onChange={ev => convert(i, ev.target.value as Kind)}>{(Object.keys(KINDS) as Kind[]).map(k => <option key={k} value={k}>{KINDS[k]}</option>)}</select></label>}
      {s.kind === "text" && F("Text", s.text, v => setSec(i, { text: v }), 5)}
      {s.kind === "list" && F("One item per line", s.text, v => setSec(i, { text: v }), 4)}
      {s.kind === "skills" && s.items.map((it, j) => (<div className="skill" key={j}>{F("Skill", it.title, v => setItem(i, j, { title: v }))}
        <label>Level<select disabled={readOnly} value={it.level} onChange={e => setItem(i, j, { level: +e.target.value })}>{[1, 2, 3, 4, 5].map(n => <option key={n}>{n}</option>)}</select></label>
        {!readOnly && <button className="link" onClick={() => setSec(i, { items: s.items.filter((_, n) => n !== j) })}>Remove</button>}</div>))}
      {s.kind === "entries" && s.items.map((it, j) => (<fieldset key={j} className="sub"><div className="grid">{F("Title", it.title, v => setItem(i, j, { title: v }))}
        {F("Subtitle (employer, school…)", it.subtitle, v => setItem(i, j, { subtitle: v }))}{F("Period", it.period, v => setItem(i, j, { period: v }))}</div>
        {F("Bullet points (one per line, **bold** allowed)", it.bullets.join("\n"), v => setItem(i, j, { bullets: v.split("\n") }), 4)}
        {!readOnly && <button className="link" onClick={() => setSec(i, { items: s.items.filter((_, n) => n !== j) })}>Remove entry</button>}</fieldset>))}
      {!readOnly && (s.kind === "entries" || s.kind === "skills") && <button className="ghost" onClick={() => setSec(i, { items: [...s.items, blankItem()] })}>{s.kind === "skills" ? "Add skill" : "Add entry"}</button>}
    </fieldset>))}
    {!readOnly && <select aria-label="Add a section" value="" onChange={e => e.target.value && addSection(e.target.value as Kind)}>
      <option value="">+ Add a section…</option>{(Object.keys(KINDS) as Kind[]).map(k => <option key={k} value={k}>{KINDS[k]}</option>)}</select>}
  </div>);
}
