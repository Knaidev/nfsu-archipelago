"""Fetch NFSU visual customisation leaf pages and aggregate cost + reputation per category/level."""
import json, re, sys, pathlib, urllib.parse, urllib.request
from collections import defaultdict

research = pathlib.Path(sys.argv[1])
UA = {"User-Agent": "NFSU-AP-research/0.1"}
BASE = "Need for Speed: Underground/Customisation/Visual/"


def wikitext(title):
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "wikitext", "redirects": 1, "format": "json"})
    with urllib.request.urlopen(urllib.request.Request("https://nfs.fandom.com/api.php?" + q, headers=UA)) as r:
        j = json.load(r)
    return None if "error" in j else j["parse"]["wikitext"]["*"]


leaf = []
for parent in ("Body", "Accessories"):
    w = (research / ("v_body.wiki" if parent == "Body" else "v_acc.wiki")).read_text(encoding="utf-8-sig")
    for sub in re.findall(r"\{\{main\|/([^|}]+)", w):
        leaf.append(BASE + parent + "/" + sub.strip())
leaf += [BASE + x for x in ("Rims", "Decals")]
for parent in ("Paint", "Vinyl"):
    pw = wikitext(BASE + parent) or ""
    for sub in re.findall(r"\{\{[Mm]ain\|/([^|}]+)", pw):
        leaf.append(BASE + parent + "/" + sub.strip())

agg = {}
raw = {}
for t in leaf:
    w = wikitext(t)
    cat = "/".join(t.split("/")[3:])
    raw[cat] = w
    rows = defaultdict(lambda: {"count": 0, "costs": set(), "reps": set()})
    lvl_text = []
    if w:
        # split into sections by === heading ===, track current level heading
        cur = "?"
        for line in w.splitlines():
            h = re.match(r"^={2,4}\s*(.*?)\s*={2,4}\s*$", line)
            if h:
                hl = h.group(1).lower()
                m = re.match(r"level (\d)", hl)
                cur = "l" + m.group(1) if m else ("u" if "unique" in hl else cur)
                continue
            if re.match(r"^\s*(Level \d|Unique)[^\n]*(available|unlocked)", line):
                lvl_text.append(line.strip())
            for args in re.findall(r"\{\{NFSUG1_PartUnlock\|([^}]*)\}\}", line):
                parts = [p.strip() for p in args.split("|")]
                cost = parts[0] if parts else ""
                rep = parts[1] if len(parts) > 1 else ""
                lvl = parts[2].lower() if len(parts) > 2 and parts[2] else ("u" if cost.lower() == "u" else cur)
                r = rows[lvl]
                r["count"] += 1
                r["costs"].add(cost)
                r["reps"].add(rep)
    agg[cat] = {"source": "https://nfs.fandom.com/wiki/" + t.replace(" ", "_"), "found": w is not None,
                "levels": {k: {"count": v["count"], "costs": sorted(v["costs"]), "reps": sorted(v["reps"])}
                           for k, v in sorted(rows.items())},
                "level_text": lvl_text}
(research / "visual.json").write_text(json.dumps(agg, indent=1, ensure_ascii=False), encoding="utf-8")
(research / "visual_raw.json").write_text(json.dumps(raw, indent=1, ensure_ascii=False), encoding="utf-8")
for cat, a in agg.items():
    print(f"== {cat} (found={a['found']})")
    for k, v in a["levels"].items():
        print(f"   {k}: n={v['count']} cost={v['costs']} rep={v['reps']}")
    for lt in a["level_text"]:
        print("   ", re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", lt)[:160])
