"""Fetch wikitext of all NFSU Underground Mode event pages from the NFS Wiki (MediaWiki API)."""
import json, re, sys, urllib.parse, urllib.request, pathlib

research = pathlib.Path(sys.argv[1])
src = (research / "underground_mode.wiki").read_text(encoding="utf-8-sig")

events = []
for m in re.finditer(r"\{\{NFSUG1_InfoIcon\|(\w+)\}\}<nowiki>#</nowiki>(\d+): \"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]\"", src):
    events.append({"num": int(m.group(2)), "icon": m.group(1), "page": m.group(3)})
# set membership
set_of = {}
cur = None
for line in src.splitlines():
    s = re.search(r"<h4>Set (\d+)</h4>", line)
    if s:
        cur = int(s.group(1))
    e = re.search(r"<nowiki>#</nowiki>(\d+):", line)
    if e and cur is not None:
        set_of[int(e.group(1))] = cur
for e in events:
    e["set"] = set_of.get(e["num"])

UA = {"User-Agent": "NFSU-AP-research/0.1"}
pages = {}
titles = [e["page"] for e in events]
for i in range(0, len(titles), 40):
    chunk = titles[i:i + 40]
    q = urllib.parse.urlencode({"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                                "titles": "|".join(chunk), "redirects": 1, "format": "json", "formatversion": 2})
    with urllib.request.urlopen(urllib.request.Request("https://nfs.fandom.com/api.php?" + q, headers=UA)) as r:
        data = json.load(r)
    redirects = {x["from"]: x["to"] for x in data["query"].get("redirects", [])}
    normalized = {x["from"]: x["to"] for x in data["query"].get("normalized", [])}
    bytitle = {p["title"]: p for p in data["query"]["pages"]}
    for t in chunk:
        tt = normalized.get(t, t)
        tt = redirects.get(tt, tt)
        p = bytitle.get(tt, {})
        revs = p.get("revisions")
        pages[t] = revs[0]["slots"]["main"]["content"] if revs else None

for e in events:
    e["wikitext"] = pages.get(e["page"])
(research / "events_raw.json").write_text(json.dumps(events, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(events), "events;", sum(1 for e in events if e["wikitext"]), "with wikitext")
