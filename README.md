# CareerOS feed

Open tech roles in India and remote, regenerated every 3 hours by `.github/workflows/scan.yml` on the main branch.

- `feed/india.jsonl.gz`: one role per line
- `feed/summary.json`: counts and errors
- `feed/boards.json`: which job board each company uses
- `feed/unmapped.csv`: companies whose career site has no public feed
- `feed/careeros.pyz`: the filter tool in one file (`python3 careeros.pyz filter-feed ...`)

See docs/feed.md on main.
