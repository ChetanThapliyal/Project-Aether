"""Shared style for the Project Aether diagrams: palette, font, drawing primitives, the
SVG wrapper, flow helpers (nodes, routes, legend) and an optional SMIL animation layer.

Every builder (build_architecture.py, build_flow_*.py) does `from aether_style import *`,
draws into the shared `out` list, and finishes with `wrap(...)`.
Role-level only: no IP addresses, hostnames or port numbers (the repo is public)."""
from html import escape

BG, PANEL, NODE, LINE, TEXT, DIM = "#1C1917", "#231F1D", "#292524", "#57534E", "#F5F5F4", "#A8A29E"
HOME, OCI, DMZ, MESH, PLAN = "#EA580C", "#D97706", "#E11D48", "#78716C", "#A8A29E"
ACCENT = "#FB923C"
FONT = "Inter, 'Segoe UI', system-ui, -apple-system, Helvetica, Arial, sans-serif"
DATE_STAMP = "as of 18 Nov 2026"
# What-moves colours. Site colours keep their meaning, so these avoid orange, amber and rose.
SKY, VIOLET, TEAL, LIME, SNOW = "#38BDF8", "#A78BFA", "#2DD4BF", "#A3E635", "#F5F5F4"

out = []
top = []   # drawn after the animation layer, so highlights never cross them (stage-time pills)
_markers = {}   # colour -> marker id, for coloured arrows


# ── primitives (unchanged: the architecture diagram must stay byte-identical) ──
def rect(x, y, w, h, r=8, fill="none", stroke=LINE, sw=1.5, dash=None, opacity=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    o = f' fill-opacity="{opacity}"' if opacity else ""
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"{o} stroke="{stroke}" stroke-width="{sw}"{d}/>')


def text(x, y, s, size=15, fill=TEXT, weight=400, anchor="start", spacing=None):
    sp = f' letter-spacing="{spacing}"' if spacing else ""
    out.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{sp}>{escape(s)}</text>')


def chip_w(label):
    return round(len(label) * 8.0 + 22)


def chips(x, y, max_x, items, gap=10, h=34):
    """Lays chips out left to right, wrapping at max_x. An item is a label or (label, True) for planned."""
    cx = x
    for it in items:
        label, planned = (it, False) if isinstance(it, str) else it
        w = chip_w(label)
        if cx + w > max_x and cx > x:
            cx, y = x, y + h + gap
        rect(cx, y, w, h, 7, "none" if planned else NODE, PLAN if planned else LINE, 1.5, "6 5" if planned else None)
        text(cx + w / 2, y + 22, label, 15, DIM if planned else TEXT, 400 if planned else 600, "middle")
        cx += w + gap
    return y + h


def label(x, y, s):
    text(x, y, s, 12.5, DIM, 700, spacing="0.08em")


def zone(x, y, w, h, color, tag, sub):
    rect(x, y, w, h, 14, color, color, 3, opacity="0.08")
    tw = round(len(tag) * 11.5 + 26)
    out.append(f'<rect x="{x + 16}" y="{y - 15}" width="{tw}" height="30" rx="8" fill="{color}"/>')
    text(x + 16 + tw / 2, y + 6, tag, 17, BG, 800, "middle")
    sw = round(len(sub) * 7.6 + 20)   # a strip of background so the border doesn't run through the text
    out.append(f'<rect x="{x + 16 + tw + 4}" y="{y - 12}" width="{sw}" height="24" fill="{BG}"/>')
    text(x + 16 + tw + 14, y + 6, sub, 15, TEXT, 600)


def actor(x, y, w, name, sub):
    rect(x, y, w, 64, 9, NODE, LINE)
    text(x + w / 2, y + 27, name, 16, TEXT, 700, "middle")
    text(x + w / 2, y + 48, sub, 13, DIM, 400, "middle")


def arrow(x1, y1, x2, y2, color=DIM, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2"{d} marker-end="url(#arr)"/>')


# ── the SVG wrapper ───────────────────────────────────────────────────────────
def wrap(W, H, aria, extra="", style=""):
    """Returns the finished SVG. `extra` is appended after the shapes (the animation layer);
    `style` becomes a <style> block. With neither, the output matches the original architecture writer."""
    mk = "".join(f'<marker id="{i}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="{c}"/></marker>'
                 for c, i in _markers.items())
    st = f"<style>{style}</style>" if style else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{FONT}" role="img" '
            f'aria-label="{aria}">'
            f'<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="{DIM}"/></marker>{mk}</defs>'
            f'{st}<rect width="{W}" height="{H}" fill="{BG}"/>' + "".join(out) + extra + "".join(top) + "</svg>\n")


# ── flow helpers ──────────────────────────────────────────────────────────────
def blend(c1, c2, t):
    """Mix two #RRGGBB colours; t=0 gives c1, t=1 gives c2."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


def marker_id(color):
    if color == DIM:
        return "arr"
    return _markers.setdefault(color, "arr-" + color.lstrip("#").lower())


def path_d(pts):
    return "M" + " L".join(f"{x},{y}" for x, y in pts)


def route(pts, color=DIM, dash=None, sw=2, head=True):
    """A polyline arrow along `pts`. Returns its path data so the animation layer can reuse it."""
    d = path_d(pts)
    da = f' stroke-dasharray="{dash}"' if dash else ""
    mk = f' marker-end="url(#{marker_id(color)})"' if head else ""
    out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linejoin="round"{da}{mk}/>')
    return d


def node(x, y, w, h, title, subs=(), stroke=LINE, dash=None, planned=False):
    """A flow node: title plus up to three dim lines, centred. Returns its box."""
    rect(x, y, w, h, 9, "none" if planned else NODE, PLAN if planned else stroke, 1.5, "6 5" if planned else dash)
    text(x + w / 2, y + 28, title, 16, DIM if planned else TEXT, 700, "middle")
    for i, s in enumerate(subs):
        text(x + w / 2, y + 49 + i * 18, s, 13, DIM, 400, "middle")
    return (x, y, w, h)


def pill(cx, y, s, color):
    """A small tag straddling a node's top border, used for the time of a stage."""
    w = round(len(s) * 7.6 + 20)
    top.append(f'<rect x="{cx - w / 2}" y="{y - 11}" width="{w}" height="22" rx="7" fill="{color}"/>')
    top.append(f'<text x="{cx}" y="{y + 4.5}" font-size="12.5" font-weight="800" fill="{BG}" text-anchor="middle">{escape(s)}</text>')


def title_row(name, subtitle):
    text(40, 46, "Project Aether", 30, TEXT, 800)
    text(262, 46, name, 22, ACCENT, 700)
    text(1576, 46, DATE_STAMP, 14, DIM, 400, "end")
    text(40, 74, subtitle, 15, DIM)


def legend(items, x_end, y, head="WHAT MOVES"):
    """Right-aligned colour key. Returns one box per item, so the animation can dim the idle ones."""
    ws = [round(len(n) * 7.4 + 26) for n, _ in items]
    hw = round(len(head) * 9.8)
    x = x_end - hw - 14 - sum(ws) - 8 * len(items)
    label(x, y + 4, head)
    x += hw + 14
    boxes = []
    for (name, c), w in zip(items, ws):
        out.append(f'<circle cx="{x + 6}" cy="{y}" r="6" fill="{c}"/>')
        text(x + 18, y + 5, name, 13.5, TEXT, 600)
        boxes.append((x - 4, y - 14, w + 6, 28))
        x += w + 8
    return boxes


# ── animation: dots racing along the routes, nodes lighting up ────────────────
class Anim:
    """Optional SMIL layer. One story at a time: a dot hops along each route in turn, the node it
    reaches lights up, and the lit nodes and routes stay on until the story ends. The base drawing is
    complete without it, so the still frame (PNG, README) reads on its own. No scripts."""
    HOP, STEP, HOLD, GAP, LEAD, FADE = 0.5, 0.58, 1.0, 0.1, 0.2, 0.15

    def __init__(self):
        self.stories = []

    def story(self, color, first, steps, legend_box=None):
        """first: box or list of boxes lit at the start. steps: list of steps; a step is a list of
        (path_d, target_box) that move together. A bare tuple is a one-route step."""
        first = [first] if isinstance(first, tuple) else list(first)
        steps = [[s] if isinstance(s, tuple) else list(s) for s in steps]
        self.stories.append(dict(color=color, first=first, steps=steps, legend=legend_box))

    def _times(self):
        t, sched = self.LEAD, []
        for s in self.stories:
            n = len(s["steps"])
            starts = [t + 0.1 + k * self.STEP for k in range(n)]
            end = starts[-1] + self.HOP + self.HOLD
            sched.append((t, starts, end))
            t = end + self.GAP
        return sched, round(t + 0.3, 2)

    @staticmethod
    def _anim(attr, T, start, end, peak, base, fade):
        ts = [0, max(start - fade, 0), start, end, min(end + fade, T), T]
        vs = [base, base, peak, peak, base, base]
        kt = ";".join(f"{v / T:.4f}" for v in ts)
        return (f'<animate attributeName="{attr}" dur="{T}s" repeatCount="indefinite" keyTimes="{kt}" '
                f'values="{";".join(str(v) for v in vs)}"/>')

    def render(self):
        sched, T = self._times()
        g = []
        for s, (t0, starts, end) in zip(self.stories, sched):
            c = s["color"]
            lit = {}   # box -> time it lights
            for b in s["first"]:
                lit.setdefault(b, t0)
            for k, step in enumerate(s["steps"]):
                for d, box in step:
                    lit.setdefault(box, starts[k] + self.HOP)
                    on = starts[k] + self.HOP
                    g.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="3" stroke-linejoin="round" '
                             f'marker-end="url(#{marker_id(c)})" opacity="0">{self._anim("opacity", T, starts[k], end, 1, 0, self.FADE)}</path>')
                    kt = f"0;{starts[k] / T:.4f};{(starts[k] + self.HOP) / T:.4f};1"
                    g.append(f'<g opacity="0"><animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" calcMode="discrete" '
                             f'keyTimes="{kt}" values="0;1;0;0"/>'
                             f'<animateMotion dur="{T}s" repeatCount="indefinite" path="{d}" calcMode="linear" keyPoints="0;0;1;1" keyTimes="{kt}"/>'
                             f'<circle r="12" fill="{c}" fill-opacity="0.28"/><circle r="6" fill="{c}" stroke="{TEXT}" stroke-width="2"/></g>')
            for (x, y, w, h), t_on in lit.items():
                g.append(f'<rect x="{x - 2}" y="{y - 2}" width="{w + 4}" height="{h + 4}" rx="10" fill="none" '
                         f'stroke="{c}" stroke-width="2.5" opacity="0">{self._anim("opacity", T, t_on, end, 1, 0, self.FADE)}</rect>')
            if s["legend"]:
                x, y, w, h = s["legend"]   # dims the legend entry whenever its story is not playing
                g.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{BG}" opacity="0">{self._anim("opacity", T, t0, end, 0, 0.7, self.FADE)}</rect>')
        style = "@media (prefers-reduced-motion: reduce){.anim{display:none}}"
        return f'<g class="anim" pointer-events="none">{"".join(g)}</g>', style
