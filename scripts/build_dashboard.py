"""Build dashboard/index.html from dashboard/app.html + dashboard/demo-data.json.

app.html is the single source of the dashboard. The same file is published as a
Claude artifact (where it uses the artifact's own database), served locally by
`careeros serve`, and hosted on GitHub Pages with the demo data inlined.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "dashboard"
app = (root / "app.html").read_text(encoding="utf-8")
demo = (root / "demo-data.json").read_text(encoding="utf-8").replace("</", "<\\/")
head, body = app.split("</style>", 1)
html = (
    "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">\n"
    "<meta name=\"description\" content=\"CareerOS: an evidence-first job application agent dashboard.\">\n"
    "<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}img{max-width:100%}</style>\n"
    + head + "</style>\n</head>\n<body>\n"
    + "<script type=\"application/json\" id=\"demo-data\">" + demo + "</script>\n"
    + body.strip() + "\n</body>\n</html>\n"
)
(root / "index.html").write_text(html, encoding="utf-8")
print(f"wrote {root / 'index.html'} ({len(html):,} bytes)")

# The same dashboard for CareerOS Cloud, without demo data: it finds the cloud API at boot.
cloud = (
    "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">\n"
    "<meta name=\"description\" content=\"CareerOS: fresh roles from company career pages, checked against your filters.\">\n"
    "<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}img{max-width:100%}</style>\n"
    + head.replace("<title>VishStack CareerOS</title>", "<title>CareerOS</title>") + "</style>\n</head>\n<body>\n"
    + body.strip() + "\n</body>\n</html>\n"
)
target = root.parent / "careeros" / "cloud" / "static" / "dashboard.html"
target.write_text(cloud, encoding="utf-8")
print(f"wrote {target} ({len(cloud):,} bytes)")
