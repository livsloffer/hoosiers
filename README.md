# Hoosiers by the Numbers

Indiana football season stats for 2015, 2020, 2025 and 2026 (through Oct 24, 2026). The repo holds the original stat reports, CSV versions of them, and a page that compares the four seasons.

## Contents

- `2015.pdf`, `2020.pdf`, `2025.pdf`, `2026.pdf`: the original season stat reports.
- `csv/<year>/`: one CSV per table in each report (game results, team statistics, rushing, passing, receiving, defense, kicking, game-by-game and more).
- `hoosiers.html`: a crimson-and-cream comparison page covering records, per-game Indiana vs. opponent stats, every game's margin, scoring by quarter and season leaders.
- `scripts/`: the PDF-to-CSV converter. It uses only the Python standard library.

## Regenerating the CSVs

```sh
python3 scripts/convert.py . csv
```

This reads every `*.pdf` in the folder and writes `csv/<pdf name>/*.csv`. Values are kept as printed in the reports, including `—` or `.` for empty cells.

This is a fan project and is not affiliated with Indiana University.
