"""Parse events_raw.json (NFS Wiki wikitext) into structured event data."""
import json, re, sys, pathlib

research = pathlib.Path(sys.argv[1])
events = json.loads((research / "events_raw.json").read_text(encoding="utf-8"))

TYPE_BY_ICON = {
    "gmci": "Circuit", "gmsp": "Sprint", "gmdf": "Drift", "gmdg": "Drag", "gmlk": "Knockout", "gmtt": "Time Trial",
    "gmcit": "Tournament (Circuit)", "gmdgt": "Tournament (Drag)", "gmdft": "Tournament (Drift)",
    "gmspt": "Tournament (Sprint)",
}


def clean(s: str) -> str:
    s = re.sub(r"\{\{NFSUG1_InfoIcon\|[^}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\{\{NFSUG1_Bank\|(\d+)\}\}", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    return s.strip()


def infobox_val(w, key):
    m = re.search(r"\|\s*" + key + r"\s*=\s*([^\n|]*)", w)
    return m.group(1).strip() if m else None


def section(w, start_pat, stop_pat=r"\n==[^=]|\n===[^=]|\{\{NFSUUndergroundModeNav"):
    m = re.search(start_pat, w)
    if not m:
        return None
    rest = w[m.end():]
    e = re.search(stop_pat, rest)
    return rest[: e.start()] if e else rest


out = []
for e in events:
    w = e["wikitext"] or ""
    ev = {"num": e["num"], "name": None, "page": e["page"], "set": e["set"],
          "type": TYPE_BY_ICON.get(e["icon"], e["icon"]), "infobox_type": infobox_val(w, "type")}
    ev["name"] = infobox_val(w, "name") or e["page"]
    def toint(x):
        try:
            return int(x.replace(",", ""))
        except Exception:
            return None
    ev["bank_infobox"] = [toint(infobox_val(w, k) or "") for k in ("easy", "med", "hard")]
    rew = section(w, r"====Rewards====", r"====Rankings====|\n===[^=]") or ""
    banks = {}
    for lvl, val in re.findall(r"(Easy|Medium|Hard):\s*\{\{NFSUG1_Bank\|([\d,]+)\}\}", rew):
        banks[lvl] = int(val.replace(",", ""))
    ev["bank_rewards_section"] = [banks.get("Easy"), banks.get("Medium"), banks.get("Hard")]
    ev["bank_mismatch"] = (ev["bank_rewards_section"] != ev["bank_infobox"]
                           and None not in ev["bank_rewards_section"])
    mags = re.search(r"<h5>Magazine Covers</h5>(.*?)</div>", rew, re.S)
    ev["magazine_covers"] = [clean(x) for x in re.findall(r"^\*(.*)$", mags.group(1), re.M)] if mags else []
    ev["magazine_covers"] = [x for x in ev["magazine_covers"] if x and x != "None"]

    unl = section(w, r"===Unlocks===", r"\{\{NFSUUndergroundModeNav|\n==[^=]|\n===[^=]") or ""
    unlocks = {}
    for head, body in re.findall(r"<h4>([^<]+)</h4>(.*?)(?=<h4>|\Z)", unl, re.S):
        items = [clean(x) for x in re.findall(r"^\*(.*)$", body, re.M)]
        items = [x for x in items if x and x != "None"]
        if items:
            unlocks[head.strip()] = items
    ev["unlocks"] = unlocks
    tt = re.findall(r"(Easy|Medium|Hard):\s*(\d+:\d+[.:]\d+)", w)
    if ev["type"] == "Time Trial":
        ev["target_times"] = dict(tt[:3])
    low = w.lower()
    ev["mentions"] = sorted({k for k in ("reputation", "star", "decline", "style points", "required") if k in low})
    ev["source"] = "https://nfs.fandom.com/wiki/" + e["page"].replace(" ", "_")
    out.append(ev)

(research / "events.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("events:", len(out))
print("bank mismatches:", [x["num"] for x in out if x["bank_mismatch"]])
print("missing bank:", [x["num"] for x in out if None in x["bank_infobox"]])
for x in out:
    if x["unlocks"]:
        print(f'#{x["num"]:>3} {x["name"]}: {x["unlocks"]}')
