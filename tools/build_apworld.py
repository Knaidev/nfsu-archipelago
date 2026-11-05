"""Builds build/nfsu.apworld (run with the Python of an Archipelago source checkout).

    python tools/build_apworld.py --archipelago <path to Archipelago source>

Packs worlds/nfsu (without tests and caches) and writes the manifest the same way Archipelago's own
build does (archipelago.json + container "version"/"compatible_version").
"""
import argparse
import json
import pathlib
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORLD = ROOT / "worlds" / "nfsu"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--archipelago", required=True, help="Archipelago source folder (for the manifest format)")
    p.add_argument("--out", default=str(ROOT / "build" / "nfsu.apworld"))
    p.add_argument("--with-tests", action="store_true")
    a = p.parse_args()

    sys.path.insert(0, a.archipelago)
    from worlds.Files import APWorldContainer  # noqa: E402

    manifest = json.loads((WORLD / "archipelago.json").read_text(encoding="utf-8"))
    container = APWorldContainer(a.out)
    container.game = manifest["game"]
    manifest.update({k: v for k, v in container.get_manifest().items() if k in ("version", "compatible_version")})

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    skip_dirs = {"__pycache__"} | (set() if a.with_tests else {"test"})
    with zipfile.ZipFile(out, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(WORLD.rglob("*")):
            rel = path.relative_to(WORLD)
            if path.is_dir() or rel.name == "archipelago.json" or path.suffix == ".pyc":
                continue
            if any(part in skip_dirs for part in rel.parts):
                continue
            zf.write(path, pathlib.Path("nfsu") / rel)
        zf.writestr("nfsu/archipelago.json", json.dumps(manifest, indent=4))
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    print(f"Built {out} ({out.stat().st_size // 1024} KiB, {len(names)} files)")
    print("Manifest:", json.dumps(manifest))


if __name__ == "__main__":
    main()
