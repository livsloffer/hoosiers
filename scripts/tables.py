"""Split positioned PDF text into tables (handles side-by-side tables)."""
import re
from pdftext import read_pdf

TITLES = {'Rushing', 'Passing', 'Receiving', 'Punt Returns', 'Interceptions', 'Kick Returns', 'Fumble Returns',
          'Scoring', 'Total Offense', 'Field Goals', 'FG Sequence', 'Punting', 'Kickoffs', 'All Purpose',
          'Defensive Leaders', 'Team Statistics', 'Score by Quarters', 'Record:', 'Date', 'Conf'}
NUMERIC = re.compile(r'^[-+(]?[\d.,:%/()\s-]+$|^[—–.]$')
SPACED = re.compile(r'^(\S )+\S$')  # "R u s h i n g" -> "Rushing"

class Cell:
    def __init__(self, x0, x1, y, text):
        self.x0, self.x1, self.y, self.text = x0, x1, y, text
    @property
    def xc(self): return (self.x0 + self.x1) / 2
    def __repr__(self): return f'{self.text!r}@{self.x0:.0f}-{self.x1:.0f}'

def lines_of(chunks, ytol=3, gap=1.2):
    chunks = [c for c in chunks if c[3].strip()]
    chunks.sort(key=lambda c: (-c[1], c[0]))
    rows = []
    for c in chunks:
        if rows and abs(rows[-1][0] - c[1]) <= ytol: rows[-1][1].append(c)
        else: rows.append([c[1], [c]])
    out = []
    for y, cs in rows:
        cs.sort(key=lambda c: c[0])
        cells = []
        for x, _, fs, t, w in cs:
            if cells and x - cells[-1].x1 < gap:
                cells[-1].text += t; cells[-1].x1 = max(cells[-1].x1, x + w)
            else:
                cells.append(Cell(x, x + w, y, t))
        for c in cells:
            c.text = ' '.join(c.text.split())
            if SPACED.match(c.text): c.text = c.text.replace(' ', '')
        out.append((y, cells))
    return out

def header_starts(cells):
    """Indices of cells that begin a table header in this line."""
    titles = [i for i, c in enumerate(cells) if c.text.lstrip('#').strip() in TITLES
              and not (c.text == 'Date' and i > 0 and cells[i-1].text == 'Conf')]
    if len(titles) >= 3: return []          # a group-label line such as "Rushing Receiving Passing ..."
    out = []
    for i in titles:
        t = cells[i].text.lstrip('#').strip()
        nxt = cells[i+1].text if i + 1 < len(cells) else ''
        if not nxt or NUMERIC.match(nxt): continue
        if t == 'Date' and i > 0 and cells[i-1].text == 'Conf': continue
        out.append(i - 1 if i > 0 and cells[i-1].text in ('#', '##') else i)
    return out

class Table:
    def __init__(self, title, header, group, y):
        self.title, self.header, self.group = title, header, group
        self.rows = []; self.last_y = y; self.step = None

def align(cells, cols):
    """Monotonic DP: assign each cell to a distinct column, minimising positional distance."""
    n, m = len(cells), len(cols)
    if n > m: return None
    def cost(c, h):
        return min(abs(c.x0 - h.x0), abs(c.x1 - h.x1), abs(c.xc - h.xc))
    INF = float('inf')
    D = [[INF] * (m + 1) for _ in range(n + 1)]; B = {}
    for j in range(m + 1): D[0][j] = 0
    for i in range(1, n + 1):
        for j in range(i, m + 1):
            a = D[i][j-1]; b = D[i-1][j-1] + cost(cells[i-1], cols[j-1])
            if b <= a: D[i][j] = b; B[i, j] = True
            else: D[i][j] = a; B[i, j] = False
    out = [''] * m; i, j = n, m
    while i > 0:
        if B[i, j]: out[j-1] = cells[i-1].text; i -= 1
        j -= 1
    return out

def group_names(header, groups):
    """Partition header columns into contiguous runs, one per group label, matching centres."""
    m, g = len(header), len(groups)
    INF = float('inf')
    # D[k][j]: best cost placing first k groups covering columns s..j-1 (s = start of first group)
    best = (INF, None)
    for s in range(m - g + 1):
        D = [[INF] * (m + 1) for _ in range(g + 1)]; B = {}
        D[0][s] = 0
        for k in range(1, g + 1):
            for j in range(s + k, m + 1):
                for i in range(s + k - 1, j):
                    if D[k-1][i] == INF: continue
                    c = D[k-1][i] + abs(groups[k-1].xc - (header[i].x0 + header[j-1].x1) / 2)
                    if c < D[k][j]: D[k][j] = c; B[k, j] = i
        if D[g][m] < best[0]:
            labels = [''] * m; j = m
            for k in range(g, 0, -1):
                i = B[k, j]
                for q in range(i, j): labels[q] = groups[k-1].text
                j = i
            best = (D[g][m], labels)
    return best[1]

def extract(path):
    result = []
    for pno, (chunks, vlines) in enumerate(read_pdf(path)):
        lines = [(y, cs) for y, cs in lines_of(chunks) if y < 725]
        title = ' '.join(c.text for c in sorted((c for c in chunks if c[1] >= 725 and c[3].strip()), key=lambda c: (-c[1], c[0])) for c in [Cell(c[0], c[0], c[1], c[3])])
        # column regions: x positions where table headers start on this page
        starts = sorted({round(cells[i].x0) for _, cells in lines for i in header_starts(cells)})
        regions = []
        for s in starts:
            if not regions or s - regions[-1] > 40: regions.append(s)
        def region_of(x):
            r = 0
            for k, s in enumerate(regions):
                if x >= s - 12: r = k
            return r
        active = {}; tables = []; prev = None
        for y, cells in lines:
            hs = header_starts(cells)
            used = set()
            for h in hs:
                r = region_of(cells[h].x0)
                hdr = [c for k, c in enumerate(cells) if k >= h and region_of(c.xc) == r and k not in used]
                # header stops at the first data-like cell (another table's row on the same line)
                cut = []
                for c in hdr:
                    if cut and (',' in c.text or re.fullmatch(r'\d+', c.text)): break
                    cut.append(c)
                used.update(k for k, c in enumerate(cells) if c in cut)
                grp = []
                if prev and prev[0] - y < 22:
                    grp = [c for c in prev[1] if region_of(c.xc) == r and c.x1 > cut[0].x0 - 4]
                    grp = [c for c in grp if not NUMERIC.match(c.text)]
                # the group-label line above this header was appended to the previous table; drop it
                if grp and r in active and active[r].rows and all(c in grp for c in active[r].rows[-1]):
                    active[r].rows.pop()
                name = next(c.text for c in cut if c.text not in ('#', '##'))
                t = Table(name, cut, grp, y); t.page = pno; t.page_title = title
                t.rules = sorted({round(x, 1) for x, lo, hi in vlines if lo - 4 <= y <= hi + 4 and cut[0].x0 < x < cut[-1].x1})
                active[r] = t; tables.append(t)
            buckets = {}
            for k, c in enumerate(cells):
                if k in used: continue
                r = region_of(c.x0)
                if r in active: buckets.setdefault(r, []).append(c)
            for r, cs in buckets.items():
                t = active[r]
                gap = t.last_y - y
                if t.step and gap > 2.6 * t.step and gap > 25:
                    del active[r]; continue
                if t.step is None: t.step = gap
                t.rows.append(cs); t.last_y = y
            prev = (y, cells)
        result += tables
    return result

def to_rows(t):
    hdr = list(t.header)
    is_results = t.title == 'Date' and any(c.text == 'Score' for c in hdr) and not any(c.text == 'WL' for c in hdr)
    if is_results:  # 2015/2020 game results: the W/L and conference-game columns have no header
        sc = next(c for c in hdr if c.text == 'Score')
        hdr.insert(hdr.index(sc), Cell(sc.x0 - 28, sc.x0 - 14, sc.y, 'W/L'))
        star = next((c for cs in t.rows for c in cs if c.text == '*'), None)
        if star: hdr.insert(0, Cell(star.x0, star.x1, sc.y, 'Conf'))
    names = [c.text for c in hdr]
    if len(t.group) >= 2 and t.rules:
        bounds = [-1e9] + t.rules + [1e9]
        for k, c in enumerate(hdr):
            lo, hi = next((a, b) for a, b in zip(bounds, bounds[1:]) if a <= c.xc < b)
            g = [gl.text for gl in t.group if lo <= gl.xc < hi]
            if len(g) == 1: names[k] = f'{g[0]} {names[k]}'
    elif len(t.group) >= 3:
        labels = group_names(hdr, t.group)
        if labels:
            names = [f'{l} {n}'.strip() if l else n for l, n in zip(labels, names)]
    rows = []; bad = []
    for cs in t.rows:
        if len(cs) == 1 and (cs[0].text.startswith(('Numbers in', '* =', 'Games:'))): continue
        r = align(cs, hdr)
        if r is None: bad.append(cs)
        else: rows.append(r)
    # merge wrapped rows (a label-only row followed by rows without a label)
    lab = 1 if names[0] in ('#', '##') else 0
    merged = []
    for r in rows:
        if merged and not r[lab] and not (lab and r[0]) and sum(bool(v) for v in merged[-1]) <= 2:
            merged[-1] = [a + b for a, b in zip(merged[-1], r)]
        else:
            merged.append(r)
    return names, merged, bad
