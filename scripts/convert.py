"""Convert the Indiana football stat PDFs into one CSV per table."""
import csv, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tables import extract, to_rows

FIRST_COL = {'Team Statistics': 'Statistic', 'Score by Quarters': 'Team', 'FG Sequence': 'Opponent',
             'Record:': 'Split', 'Date': 'Date', 'Conf': 'Conf'}
GBG_PARTS = ['offense', 'defense', 'kicking']

def slug(s):
    return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')

def convert(pdf, outdir):
    os.makedirs(outdir, exist_ok=True)
    written = []; gbg_count = {}
    for t in extract(pdf):
        if 'Combined' in t.page_title and t.title != 'Record:':
            continue  # summary page that repeats tables from the other pages
        names, rows, bad = to_rows(t)
        if bad:
            print(f'  WARNING {t.title} p{t.page + 1}: {len(bad)} unaligned rows', file=sys.stderr)
        if not rows: continue
        names = ['#' if n == '##' else n for n in names]
        lab = 1 if names[0] == '#' else 0
        if t.title not in ('Date', 'Conf'): names[lab] = FIRST_COL.get(t.title, 'Player')
        if t.title == 'Scoring':
            names = [f'PAT {n}' if n.lower() in ('kick', 'rush', 'rcv', 'pass') else n for n in names]
        if 'Game-by-Game' in t.page_title:
            side = 'opponent' if 'Opponent' in t.page_title else 'team'
            k = gbg_count[side] = gbg_count.get(side, -1) + 1
            fname = f'{side}_game_by_game_{GBG_PARTS[k]}'
            names = [{'off saf': 'saf', 'off pts': 'pts', 'off t/o': 'points off t/o', 'tot off': 'total offense'}.get(n, n) for n in names]
            names[1] = 'Opponent'
        elif t.title in ('Date', 'Conf'):
            fname = 'game_results'
            if 'W/L' in names:  # "Wo"/"Lo" marks an overtime game
                i = names.index('W/L')
                names.insert(i + 1, 'OT')
                rows = [r[:i] + [r[i][:1], 'OT' if r[i].endswith('o') else ''] + r[i+1:] for r in rows]
        elif t.title == 'Defensive Leaders':
            fname = 'defense'
        elif t.title == 'Record:':
            fname = 'record_splits'
        else:
            fname = slug(t.title)
        path = os.path.join(outdir, fname + '.csv')
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f); w.writerow(names); w.writerows(rows)
        written.append((fname, len(rows), len(names)))
    return written

if __name__ == '__main__':
    src, out = sys.argv[1], sys.argv[2]
    for name in sorted(os.listdir(src)):
        if name.lower().endswith('.pdf'):
            year = name[:-4]
            res = convert(os.path.join(src, name), os.path.join(out, year))
            print(f'{name}: {len(res)} CSVs')
            for fname, nr, nc in res: print(f'   {fname}.csv  ({nr} rows x {nc} cols)')
