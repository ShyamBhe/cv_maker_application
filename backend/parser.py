"""Best-effort CV parser: PDF -> CVData-shaped dict. Rule based, runs locally, stores nothing."""
import re
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextLine, LTChar

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<!\d)\+?\d[\d ()./-]{6,}\d(?!\d)")
MON = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
DT = rf"(?:\d{{1,2}}/\d{{4}}|{MON}\s+\d{{4}}|(?:19|20)\d{{2}})"
RANGE = re.compile(rf"{DT}\s*(?:-|–|—|to)\s*(?:{DT}|Present|Current|Now|Ongoing|Today)", re.I)
SINGLE = re.compile(rf"\b(?:{MON}\s+)?(?:19|20)\d{{2}}\b", re.I)
URL = re.compile(r"(?:https?://)?(?:www\.)?[\w-]+(?:\.[\w-]+)+(?:/\S*)?")
BUL = "•▪●◦·‣*-–—"

HEAD = {}
for kind, names in {
    "text": "profile|summary|professional summary|profile summary|about me|about|objective|career objective|personal statement|references|reference",
    "entries": "experience|work experience|professional experience|employment|employment history|work history|career history|education|education and training|academic background|projects|personal projects|academic projects|volunteering|volunteer experience|publications|internships|research experience",
    "list": "skills|technical skills|key skills|core skills|core competencies|competencies|languages|certifications|certificates|awards|achievements|interests|hobbies|tools|technologies",
    "contact": "personal details|contact|contact details|personal information|personal info|details"}.items():
    HEAD.update({n: kind for n in names.split("|")})
RANKS = [("profile|summary|about|objective|statement", 0), ("experience|employment|history|internship", 1), ("education|academic", 2),
         ("project|volunteer|publication", 3), ("skill|competenc|tool|technolog", 4), ("language", 5), ("certif|award|achiev", 6), ("interest|hobb", 7), ("refer", 9)]

def heading(t):
    if len(t) > 40: return None
    k = HEAD.get(re.sub(r"\s+", " ", re.sub(r"[^a-z& ]", "", t.lower()).replace("&", "and")).strip())
    return (t.strip(": ").title() if t.isupper() else t.strip(": "), k) if k else None

def read_pages(fp):
    pages = []
    for pg in extract_pages(fp, maxpages=5):
        L = []
        def walk(o):
            if isinstance(o, LTTextLine):
                t = re.sub(r"\(cid:\d+\)", "•", " ".join(o.get_text().split()))
                if t: L.append(dict(t=t, x0=o.x0, x1=o.x1, y=o.y1, size=max((c.size for c in o if isinstance(c, LTChar)), default=0)))
            elif hasattr(o, "__iter__"):
                for c in o: walk(c)
        walk(pg); pages.append((pg.width, L))
    return pages

def rows(c):
    out, cur, ry = [], [], None
    for l in sorted(c, key=lambda l: -l["y"]):
        if ry is not None and abs(ry - l["y"]) < 3.5: cur.append(l)
        else: out += sorted(cur, key=lambda l: l["x0"]); cur, ry = [l], l["y"]
    return out + sorted(cur, key=lambda l: l["x0"])

def order(width, L, hint=None):  # detect a two-column layout (e.g. sidebar) via a vertical gutter no line crosses
    best = None
    if hint:  # later pages with few lines reuse the gutter found on an earlier page
        cross = sum(1 for l in L if l["x0"] < hint - 2 and l["x1"] > hint + 2)
        if cross <= max(1, .06 * len(L)) and any(l["x1"] <= hint + 2 for l in L) and any(l["x0"] >= hint - 2 for l in L): best = (cross, hint)
    for g in range(int(width * .22), int(width * .46), 4):
        cross = sum(1 for l in L if l["x0"] < g - 2 and l["x1"] > g + 2)
        left, right = sum(1 for l in L if l["x1"] <= g + 2), sum(1 for l in L if l["x0"] >= g - 2)
        if not hint and left >= 8 and right >= 8 and cross <= max(1, .06 * len(L)) and (best is None or cross < best[0]): best = (cross, g)
    if not best: return [("R", l) for l in rows(L)], None
    g = best[1]
    return ([("L", l) for l in rows([l for l in L if (l["x0"] + l["x1"]) / 2 < g])] + [("R", l) for l in rows([l for l in L if (l["x0"] + l["x1"]) / 2 >= g])]), g

def find_name(L):
    for l in sorted(L, key=lambda l: -l["size"]):
        if 1 <= len(l["t"].split()) <= 5 and len(l["t"]) < 50 and not re.search(r"\d|@", l["t"]) and not heading(l["t"]): return l

def find_title(L, n):
    best, cx = None, (n["x0"] + n["x1"]) / 2
    for l in L:
        d = n["y"] - l["y"]
        if l is n or not 0 < d < 45 or len(l["t"]) > 70 or EMAIL.search(l["t"]) or PHONE.search(l["t"]) or heading(l["t"]): continue
        if (abs(l["x0"] - n["x0"]) < 12 or abs((l["x0"] + l["x1"]) / 2 - cx) < 15) and (best is None or d < n["y"] - best["y"]): best = l
    return best

def contact(cv, t):  # a header line may hold several items: "email | phone | website"
    for p in re.split(r"\s*[|•·]\s*", t):
        if p.strip(): _contact(cv, p.strip())

def _contact(cv, t):
    if (m := EMAIL.search(t)) and not cv["email"]: cv["email"] = m.group()
    elif re.search(r"linkedin\.com", t, re.I): cv["linkedin"] = cv["linkedin"] or t
    elif (p := PHONE.search(t)) and 8 <= len(re.sub(r"\D", "", p.group())) <= 15 and not RANGE.search(t): cv["phone"] = cv["phone"] or p.group().strip()
    elif URL.fullmatch(t) and not cv["website"]: cv["website"] = t

def bullets(lines):
    out, ended = [], True
    for t in lines:
        marked = len(t) > 1 and t[0] in BUL
        t = t.lstrip(BUL + " ") if marked else t
        if not t: continue
        if out and not marked and not ended: out[-1] += t if out[-1].endswith("-") else " " + t
        else: out.append(t)
        ended = bool(re.search(r"[.!?;)]$", t))
    return out

def split_top(s):
    parts, depth, cur = [], 0, ""
    for ch in s:
        depth += (ch in "([") - (ch in ")]")
        if ch in ",;|•·" and depth <= 0: parts.append(cur); cur = ""
        else: cur += ch
    return parts + [cur]

def list_items(lines):
    merged = []
    for t in (x.lstrip(BUL + " ") for x in lines):
        if not t: continue
        if merged and (merged[-1].count("(") > merged[-1].count(")") or t[0] == "(" or t[0].islower()): merged[-1] += " " + t
        else: merged.append(t)
    return [p.strip() for m in merged for p in ([m] if ":" in m else split_top(m)) if p.strip()]

def wraps(title, nxt):  # is `nxt` the wrapped second line of a title?
    return (title.count("(") > title.count(")") or bool(re.search(r"\b(in|of|and|for|the|at|to)$|&$", title, re.I))
            or (title.isupper() and nxt.isupper() and "," not in nxt and len(nxt.split()) <= 4 and len(title) >= 28))

def entries(L):
    idx = [i for i, t in enumerate(L) if RANGE.search(t)] or [i for i, t in enumerate(L) if len(t) <= 90 and t[0] not in BUL and SINGLE.search(t)]
    if not idx: return [dict(title=L[0], subtitle="", period="", bullets=bullets(L[1:]), level=3)] if L else []
    A = []
    for a in idx:
        t = L[a]; m = RANGE.search(t) or SINGLE.search(t); rest = (t[:m.start()] + " " + t[m.end():]).strip(" -–—|,·()")
        if len(rest) > 2: A.append([a, rest, m.group().strip(), a + 1]); continue
        title, b = (L[a - 1] if a else ""), a + 1
        while b < len(L) and b not in idx and title and wraps(title, L[b]): title += " " + L[b]; b += 1
        A.append([max(a - 1, 0), title, m.group().strip(), b])
    out = []
    for k, (ti, title, period, bs) in enumerate(A):
        body = L[bs: A[k + 1][0] if k + 1 < len(A) else len(L)]; sub = ""
        if body and body[0][0] not in BUL and len(body[0]) <= 90 and not body[0].endswith(".") and not RANGE.search(body[0]): sub, body = body[0], body[1:]
        out.append(dict(title=title, subtitle=sub, period=period, bullets=bullets(body), level=3))
    return out

def parse_pdf(fp):
    pages = read_pages(fp)
    if not any(L for _, L in pages): raise ValueError("no text")
    name_l = find_name(pages[0][1]); title_l = find_title(pages[0][1], name_l) if name_l else None
    skip = {id(name_l), id(title_l)}
    cv = dict(name=(name_l["t"].title() if name_l and name_l["t"].isupper() else name_l["t"] if name_l else ""),
              title=title_l["t"] if title_l else "", email="", phone="", website="", linkedin="")
    secs, state, gutter = [], {}, None  # reading state is tracked per column, so a sidebar never swallows main-column text
    for w, L in pages:
        ordered, g = order(w, L, gutter); gutter = gutter or g
        for key, l in ordered:
            if id(l) in skip: continue
            zone, cur = state.get(key, ("header", None)); t, h = l["t"], heading(l["t"])
            if h:
                zone = "contact" if h[1] == "contact" else "section"
                cur = None if h[1] == "contact" else dict(title=h[0], kind=h[1], lines=[])
                if cur: secs.append(cur)
            elif zone != "section" or cur is None: contact(cv, t)
            else: cur["lines"].append(t)
            state[key] = (zone, cur)
    out = []
    for s in secs:
        L = s["lines"]
        if not L: continue
        if s["kind"] == "text": sec = dict(text="\n".join(bullets(L)), items=[])
        elif s["kind"] == "list": sec = dict(text="\n".join(list_items(L)), items=[])
        else: sec = dict(text="", items=entries(L))
        out.append(dict(title=s["title"], kind=s["kind"], **sec))
    out.sort(key=lambda s: next((r for p, r in RANKS if re.search(p, s["title"].lower())), 8))
    cut = lambda v: v[:3900] if isinstance(v, str) else v
    for s in out:
        s["title"], s["text"], s["items"] = cut(s["title"]), cut(s["text"]), s["items"][:60]
        for i in s["items"]: i.update({k: cut(i[k]) for k in ("title", "subtitle", "period")}, bullets=[cut(b) for b in i["bullets"][:40]])
    return {**{k: cut(v) for k, v in cv.items()}, "sections": out[:30]}
