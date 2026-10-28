"""Minimal stdlib-only PDF text extractor: returns positioned text chunks per page."""
import re, zlib

def load_objects(data):
    objs = {}
    for m in re.finditer(rb'(\d+)\s+0\s+obj(.*?)endobj', data, re.S):
        objs[int(m.group(1))] = m.group(2)
    for num, body in list(objs.items()):
        if b'/ObjStm' in body:
            raw = stream_data(body)
            n = int(re.search(rb'/N\s+(\d+)', body).group(1))
            first = int(re.search(rb'/First\s+(\d+)', body).group(1))
            hdr = list(map(int, raw[:first].split()))
            for i in range(n):
                onum, off = hdr[2*i], hdr[2*i+1]
                end = hdr[2*i+3] if i+1 < n else len(raw)-first
                objs.setdefault(onum, raw[first+off:first+end])
    return objs

def stream_data(body):
    m = re.search(rb'stream\r?\n', body)
    s = body[m.end():]
    s = s[:s.rfind(b'endstream')]
    if b'FlateDecode' in body[:m.start()]:
        return zlib.decompressobj().decompress(s)
    return s

def refs(v):
    return [int(x) for x in re.findall(rb'(\d+)\s+0\s+R', v)]

def deref(objs, v):
    m = re.fullmatch(rb'\s*(\d+)\s+0\s+R\s*', v)
    return objs[int(m.group(1))] if m else v

def dict_entry(body, key):
    """Return raw value for /key (dict, array, ref or name)."""
    m = re.search(rb'/' + key + rb'\s*', body)
    if not m: return None
    s = body[m.end():]
    if s[:2] == b'<<':
        depth = 0; i = 0
        while i < len(s):
            if s[i:i+2] == b'<<': depth += 1; i += 2; continue
            if s[i:i+2] == b'>>':
                depth -= 1; i += 2
                if depth == 0: return s[:i]
                continue
            i += 1
    if s[:1] == b'[':
        depth = 0
        for i, c in enumerate(s):
            if c == 91: depth += 1
            elif c == 93:
                depth -= 1
                if depth == 0: return s[:i+1]
    m2 = re.match(rb'\d+\s+0\s+R|/\w+|[-\d.]+', s)
    return m2.group(0) if m2 else None

def pages(objs):
    root = [b for b in objs.values() if re.search(rb'/Type\s*/Pages\b', b) and b'/Parent' not in b][0]
    out = []
    def walk(body, inherited):
        res = dict_entry(body, b'Resources') or inherited
        for k in refs(dict_entry(body, b'Kids')):
            kb = objs[k]
            if re.search(rb'/Type\s*/Pages\b', kb): walk(kb, res)
            else: out.append((kb, dict_entry(kb, b'Resources') or res))
    walk(root, None)
    return out

HELV = {' ':278,'.':278,',':278,'-':333,'/':278,'(':333,')':333,'#':556,'*':389,'%':889,':':278,"'":191,'I':278,'i':222,'l':222,'j':222,'f':278,'t':278,'r':333,'J':500,'m':833,'w':722,'M':833,'W':944}
def helv_width(ch):
    if ch in HELV: return HELV[ch]
    if ch.isdigit(): return 556
    if ch.isupper(): return 667
    return 500

HELV_W = dict(zip(range(32, 127), map(int, '278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 1015 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 556 333 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 556 556 333 500 278 556 500 722 500 500 500 334 260 334 584'.split())))
HELVB_W = dict(zip(range(32, 127), map(int, '278 333 474 556 556 889 722 238 333 333 389 584 278 333 278 278 556 556 556 556 556 556 556 556 556 556 333 333 584 584 584 611 975 722 722 722 722 667 611 778 722 278 556 722 611 833 722 778 667 778 722 667 611 722 667 944 667 667 611 333 278 333 584 556 333 556 611 556 611 556 333 611 611 278 278 556 278 889 611 611 611 611 389 556 333 611 556 778 556 556 500 389 280 389 584'.split())))

class Font:
    def __init__(self, objs, body):
        self.cid = b'/Type0' in body
        self.cmap = {}
        self.widths = {}
        self.default = 500
        tu = dict_entry(body, b'ToUnicode')
        if tu and tu.strip().endswith(b'R'):
            self.parse_cmap(stream_data(deref(objs, tu)))
        if self.cid:
            desc = deref(objs, re.search(rb'\[\s*(\d+\s+0\s+R)', dict_entry(body, b'DescendantFonts')).group(1))
            dw = dict_entry(desc, b'DW'); self.default = int(dw) if dw else 1000
            w = dict_entry(desc, b'W')
            if w:
                toks = re.findall(rb'\[|\]|[-\d.]+', deref(objs, w)[1:-1])
                i = 0
                while i < len(toks):
                    c = int(toks[i])
                    if toks[i+1] == b'[':
                        j = i + 2
                        while toks[j] != b']':
                            self.widths[c] = float(toks[j]); c += 1; j += 1
                        i = j + 1
                    else:
                        c2, wv = int(toks[i+1]), float(toks[i+2])
                        for cc in range(c, c2+1): self.widths[cc] = wv
                        i += 3
        else:
            if b'/Helvetica' in body and b'/Widths' not in body:
                self.widths = dict(HELVB_W if b'Bold' in body else HELV_W)
            fc = dict_entry(body, b'FirstChar'); ws = dict_entry(body, b'Widths')
            if fc and ws:
                fc = int(fc)
                for i, wv in enumerate(re.findall(rb'[-\d.]+', deref(objs, ws))):
                    self.widths[fc+i] = float(wv)

    def parse_cmap(self, data):
        for blk in re.findall(rb'beginbfchar(.*?)endbfchar', data, re.S):
            for a, b in re.findall(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', blk):
                self.cmap[int(a, 16)] = bytes.fromhex(b.decode()).decode('utf-16-be')
        for blk in re.findall(rb'beginbfrange(.*?)endbfrange', data, re.S):
            for a, b, c in re.findall(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', blk):
                base = int(c, 16)
                for i, code in enumerate(range(int(a, 16), int(b, 16)+1)):
                    self.cmap[code] = chr(base + i)

    def decode(self, raw):
        """Return (text, width in text-space units /1000)."""
        codes = [raw[i]*256 + raw[i+1] for i in range(0, len(raw)-1, 2)] if self.cid else list(raw)
        out = []; w = 0
        for c in codes:
            ch = self.cmap.get(c) if self.cmap else None
            if ch is None: ch = bytes([c]).decode('cp1252', 'replace') if c < 256 else '?'
            out.append(ch)
            w += self.widths.get(c, helv_width(ch) if not self.widths else self.default)
        return ''.join(out), w / 1000

def unescape(s):
    return re.sub(rb'\\([nrtbf()\\]|[0-7]{1,3})', lambda m: {b'n':b'\n',b'r':b'\r',b't':b'\t',b'b':b'\b',b'f':b'\f',b'(':b'(',b')':b')',b'\\':b'\\'}.get(m.group(1)) or bytes([int(m.group(1),8)&255]), s)

TOK = re.compile(rb'\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>|\[[^\]]*\]|[-+]?\d*\.?\d+|/[^\s/\[\]()<>]+|[A-Za-z\'"*]+')

def strbytes(t):
    if t[:1] == b'(': return unescape(t[1:-1])
    return bytes.fromhex(re.sub(rb'\s', b'', t[1:-1]).decode())

def page_chunks(objs, page, res):
    fontmap = {}
    res = deref(objs, res) if res else b''
    fd = dict_entry(res, b'Font')
    if fd:
        fd = deref(objs, fd)
        for name, ref in re.findall(rb'/([^\s/<>\[\]]+)\s*(\d+\s+0\s+R)', fd):
            fontmap[name] = Font(objs, deref(objs, ref))
    cm = dict_entry(page, b'Contents')
    content = b''.join(stream_data(objs[r]) for r in refs(cm if cm.startswith(b'[') else cm))
    if cm.strip().endswith(b'R') and not cm.startswith(b'['):
        body = deref(objs, cm)
        if body.lstrip().startswith(b'['):
            content = b''.join(stream_data(objs[r]) for r in refs(body))
    chunks = []; vlines = []; pt = None; stack = []; tm = [1, 0, 0, 1, 0, 0]; lm = list(tm); font = None; fs = 0
    def show(text, w):
        sx = tm[0]
        chunks.append((tm[4], tm[5], fs*abs(tm[3] or 1), text, w*fs*sx))
    for t in TOK.findall(content):
        if t in (b'Td', b'TD'):
            dx, dy = float(stack[-2]), float(stack[-1])
            lm = [lm[0], lm[1], lm[2], lm[3], lm[4] + dx*lm[0], lm[5] + dy*lm[3]]; tm = list(lm); stack = []
        elif t == b'Tm':
            lm = [float(v) for v in stack[-6:]]; tm = list(lm); stack = []
        elif t == b'm':
            pt = (float(stack[-2]), float(stack[-1])); stack = []
        elif t == b'l':
            x2, y2 = float(stack[-2]), float(stack[-1])
            if pt and abs(pt[0] - x2) < 0.5 and abs(pt[1] - y2) > 8:
                vlines.append((x2, min(pt[1], y2), max(pt[1], y2)))
            pt = (x2, y2); stack = []
        elif t == b'BT':
            tm = [1, 0, 0, 1, 0, 0]; lm = list(tm); stack = []
        elif t == b'Tf':
            fs = float(stack[-1]); font = fontmap.get(stack[-2][1:]); stack = []
        elif t in (b'Tj', b"'", b'"'):
            txt, w = font.decode(strbytes(stack[-1])) if font else (stack[-1].decode('latin1'), 0)
            show(txt, w); stack = []
        elif t == b'TJ':
            parts = re.findall(rb'\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>|[-+]?\d*\.?\d+', stack[-1][1:-1])
            txt = ''; w = 0
            for p in parts:
                if p[:1] in b'(<':
                    a, b = font.decode(strbytes(p)); txt += a; w += b
                else:
                    w -= float(p) / 1000
                    if float(p) < -200: txt += ' '
            show(txt, w); stack = []
        elif t[:1] in b'(/[<' or re.match(rb'[-+.\d]', t):
            stack.append(t)
        else:
            stack = []
    return chunks, vlines

def read_pdf(path):
    objs = load_objects(open(path, 'rb').read())
    return [page_chunks(objs, p, r) for p, r in pages(objs)]
