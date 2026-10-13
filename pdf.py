import io, re
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, FrameBreak, KeepInFrame, NextPageTemplate,
                                Paragraph, Spacer, Flowable, CondPageBreak, Table, TableStyle, HRFlowable, KeepTogether)

W, H = A4
INK, GREY, RULE = colors.HexColor("#2b2f33"), colors.HexColor("#555b61"), colors.HexColor("#dfe5ea")
FONTS = {"sans": ("Helvetica", "Helvetica-Bold"), "serif": ("Times-Roman", "Times-Bold")}

LINK = re.compile(r"(?<![\w@/.-])((?:https?://|www\.)[^\s<>()]+|[\w-]+(?:\.[\w-]+)*\.([a-z]{2,24})/[^\s<>()]+)", re.I)
def _a(m):  # make URLs clickable (Node.js/Express-style text is left alone)
    u = m.group(1).rstrip(".,;:"); tail = m.group(1)[len(u):]
    if m.group(2) and m.group(2).lower() in ("js", "ts", "py", "cs", "rb", "md"): return m.group(0)
    return f'<a href="{u if re.match("https?://", u, re.I) else "https://" + u}" color="#1a5fa8">{u}</a>{tail}'

def esc(t, link=True):
    t = (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)  # **bold** support
    return LINK.sub(_a, t) if link else t

def clink(x):  # one contact item (email / website / profile) as a clickable link
    x = x.strip()
    if x and " " not in x:
        href = "mailto:" + x if "@" in x else (x if x.lower().startswith("http") else "https://" + x) if re.fullmatch(r"(?:https?://|www\.)\S+|[\w-]+(?:\.[\w-]+)+(?:/\S*)?", x, re.I) else None
        if href: return f'<a href="{href}" color="#1a5fa8">{esc(x, False)}</a>'
    return esc(x, False)

class Theme:
    def __init__(s, d):
        s.tpl, s.accent = d.template, colors.HexColor(d.color)
        s.light = colors.Color(*[1 - (1 - v) * .3 for v in (s.accent.red, s.accent.green, s.accent.blue)])
        s.reg, s.bold = FONTS[d.font]
    def p(s, name, bold=False, c=INK, **k):
        return ParagraphStyle(name, fontName=s.bold if bold else s.reg, textColor=c, **k)

def heading(text, th, small=False, first=False):
    if th.tpl == "classic":
        st, text = th.p("h", True, th.accent, fontSize=10.5, leading=13, spaceBefore=0 if first else 12, keepWithNext=1), text.upper()
    else:
        fs = 14 if small else 16
        st = th.p("h", False, th.accent, fontSize=fs, leading=fs + 4, spaceBefore=0 if first else 14, keepWithNext=1)
    hr = HRFlowable(width="100%", thickness=.6, color=RULE, spaceBefore=1, spaceAfter=7); hr.keepWithNext = 1
    return [Paragraph(esc(text), st), hr]

class Skill(Flowable):
    def __init__(self, name, level, width, th, style):
        super().__init__(); self.p, self.lv, self.w, self.th = Paragraph(esc(name), style), max(0, min(5, level)), width, th
    def wrap(self, aw, ah):
        self.p.wrap(self.w - 58, ah); self.h = self.p.height + 7; return self.w, self.h
    def draw(self):
        self.p.drawOn(self.canv, 0, self.h - 4 - self.p.height)
        for i in range(5):
            self.canv.setFillColor(self.th.accent if i < self.lv else self.th.light)
            self.canv.circle(self.w - 50 + i * 10.5, self.h - 9, 3.3, stroke=0, fill=1)

def dated(title, period, w, th):
    t = Table([[Paragraph(esc(title), th.p("t", True, GREY, fontSize=8.8, leading=11)),
                Paragraph(esc(period), th.p("d", True, th.accent, fontSize=8.5, leading=11, alignment=TA_RIGHT))]], colWidths=[w - 92, 92])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")] + [(a, (0, 0), (-1, -1), 0) for a in ("LEFTPADDING", "RIGHTPADDING", "TOPPADDING")] + [("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    return t

def section(sec, w, th, side=False):
    fs = 8.5 if side else 8.8
    body = th.p("b", fontSize=fs, leading=fs + 3, spaceAfter=3)
    bl = th.p("bl", fontSize=fs, leading=fs + 3.2, leftIndent=14, bulletIndent=4)
    out, lines = heading(sec.title, th, side), [l for l in sec.text.split("\n") if l.strip()]
    if sec.kind == "text": out += [Paragraph(esc(l), body) for l in lines]
    elif sec.kind == "list": out += [Paragraph(esc(l), body) for l in lines] if side else [Paragraph(esc(l), bl, bulletText="•") for l in lines]
    elif sec.kind == "skills": out += [Skill(i.title, i.level, w if side else min(w, 250), th, body) for i in sec.items if i.title.strip()]
    else:
        for i in sec.items:
            if not (i.title.strip() or i.subtitle.strip() or any(b.strip() for b in i.bullets)): continue
            head = [dated(i.title, i.period, w, th)]
            if i.subtitle: head.append(Paragraph(esc(i.subtitle), th.p("e", c=th.accent, fontSize=8.5, leading=11, spaceAfter=3)))
            out.append(KeepTogether(head))
            out += [Paragraph(esc(b), bl, bulletText="•") for b in i.bullets if b.strip()] + [Spacer(1, 9)]
    return ([] if side else [CondPageBreak(90)]) + out if len(out) > 2 else []  # start a new page rather than strand a heading at the bottom

def render_pdf(d, watermark=False) -> io.BytesIO:
    th, buf = Theme(d), io.BytesIO()
    contact = [x for x in (d.email, d.phone, d.website, d.linkedin) if x]
    fr = dict(leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    def mark(c, _):
        if watermark:
            c.saveState(); c.setFillColor(colors.Color(.5, .5, .5, alpha=.16)); c.setFont("Helvetica-Bold", 90)
            c.translate(W / 2, H / 2); c.rotate(50); c.drawCentredString(0, 0, "PREVIEW"); c.restoreState()
    def tpl(name, frames, deco=None): return PageTemplate(name, frames, onPage=deco or (lambda c, _: None), onPageEnd=mark)
    doc = BaseDocTemplate(buf, pagesize=A4, title=f"CV {d.name}", author=d.name)
    name_st = lambda **k: th.p("n", True, th.accent, **k)
    secs = d.sections

    if d.template == "sidebar":
        SW, MX = 186, 232; sw, mw = SW - 28, W - 232 - 30
        side = heading("Personal details", th, True, True) + [Paragraph(clink(p) if k else esc(p), th.p("c", fontSize=8.5, leading=11, spaceAfter=5)) for k, p in [(0, d.name)] * bool(d.name) + [(1, p) for x in contact for p in x.split("|") if p.strip()]]
        for s in secs:
            if s.kind in ("skills", "list"): side += section(s, sw, th, True)
        main = [Paragraph(esc(d.name) or "Your Name", name_st(fontSize=28, leading=32))]
        if d.title: main.append(Paragraph(esc(d.title.upper()), th.p("ti", fontSize=9.5, leading=14, spaceBefore=4)))
        for s in secs:
            if s.kind in ("text", "entries"): main += section(s, mw, th)
        def deco(c, _):
            c.saveState(); c.setFillColor(colors.HexColor("#f3f5f7")); c.rect(26, 0, SW, H, stroke=0, fill=1)
            c.setFillColor(th.accent); c.rect(0, 0, 26, H, stroke=0, fill=1); c.restoreState()
        right = Frame(MX, 30, mw, H - 56, id="r", **fr)
        doc.addPageTemplates([tpl("first", [Frame(40, 30, sw, H - 58, id="l", **fr), right], deco), tpl("later", [right], deco)])
        story = [KeepInFrame(sw, H - 58, side, mode="shrink"), FrameBreak(), NextPageTemplate("later")] + main
    elif d.template == "classic":
        mw = W - 80
        story = [Paragraph(esc(d.name) or "Your Name", th.p("n", True, INK, fontSize=26, leading=30, alignment=TA_CENTER))]
        if d.title: story.append(Paragraph(esc(d.title), th.p("ti", c=th.accent, fontSize=11, leading=15, alignment=TA_CENTER)))
        story.append(Paragraph("  |  ".join(clink(p) for x in contact for p in x.split("|") if p.strip()), th.p("c", c=GREY, fontSize=8.8, leading=12, alignment=TA_CENTER, spaceAfter=6)))
        for s in secs: story += section(s, mw, th)
        doc.addPageTemplates([tpl("p", [Frame(40, 36, mw, H - 72, **fr)])])
    else:  # modern: coloured header band
        mw, band = W - 80, 108
        def deco(c, _):
            c.saveState(); c.setFillColor(th.accent); c.rect(0, H - band, W, band, stroke=0, fill=1); c.setFillColor(colors.white)
            c.setFont(th.bold, 27); c.drawString(40, H - 55, d.name or "Your Name")
            c.setFont(th.reg, 11); c.drawString(40, H - 74, d.title)
            c.setFont(th.reg, 8.8); c.drawString(40, H - 94, "   |   ".join(contact)); c.restoreState()
        doc.addPageTemplates([tpl("first", [Frame(40, 36, mw, H - band - 54, **fr)], deco), tpl("later", [Frame(40, 36, mw, H - 72, **fr)])])
        story = [NextPageTemplate("later")]
        for s in secs: story += section(s, mw, th)
    doc.build(story or [Spacer(1, 1)]); buf.seek(0); return buf
