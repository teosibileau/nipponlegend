#!/usr/bin/env python3
"""Run a parts hunt for a given hunt slug.

Reads:
  src/content/vehicles/<vehicle>.mdx  (profile + heuristics)
  src/content/sites/<site>.mdx        (adapter config) for each huntOn site
  src/content/hunts/<hunt>.mdx        (items + status + chosen)

Writes back:
  src/content/hunts/<hunt>.mdx        (alternates refreshed, lastRun updated)
  data/catalogs/<site>-<vehicle>.json (cached catalog)
  data/runs/<hunt>.<date>.json        (run snapshot)
"""
import argparse
import importlib
import json
import re
import sys
import unicodedata
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
VEHICLES_DIR = ROOT / "src" / "content" / "vehicles"
SITES_DIR = ROOT / "src" / "content" / "sites"
HUNTS_DIR = ROOT / "src" / "content" / "hunts"
CATALOGS_DIR = ROOT / "data" / "catalogs"
RUNS_DIR = ROOT / "data" / "runs"


# --- MDX I/O ---------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


def read_mdx(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(f"{path} has no YAML frontmatter")
    fm = yaml.safe_load(m.group(1)) or {}
    body = text[m.end():]
    return fm, body


_NUMERIC_LOOKING = re.compile(r"^-?\d+(\.\d+)?$")


def _str_representer(dumper, data):
    # PyYAML emits YAML 1.1; Astro's content loader follows 1.2. The two
    # disagree on numeric-looking strings (esp. leading-zero all-digit
    # strings like SKU '044833508009'), which the loader would parse as a
    # number on read-back and fail the string schema. Force-quote anything
    # that could be ambiguous.
    if data and _NUMERIC_LOOKING.match(data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


class _SafeDumper(yaml.SafeDumper):
    pass


_SafeDumper.add_representer(str, _str_representer)


def write_mdx(path: Path, frontmatter: dict, body: str) -> None:
    fm_text = yaml.dump(
        frontmatter,
        Dumper=_SafeDumper,
        allow_unicode=True,
        sort_keys=False,
        width=140,
        default_flow_style=False,
    )
    path.write_text(f"---\n{fm_text}---\n{body if body.startswith(chr(10)) else chr(10) + body}")


# --- text normalization ----------------------------------------------------

class _StripHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buf: list[str] = []
    def handle_data(self, d: str) -> None:
        self.buf.append(d)


def strip_html(s: str) -> str:
    if not s:
        return ""
    p = _StripHTML()
    p.feed(s)
    return " ".join("".join(p.buf).split())


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("×", "x")
    return re.sub(r"\s+", " ", s.lower()).strip()


# --- year-range extraction -------------------------------------------------

_YEAR_SEP = r"(?:\s*[-/]\s*|\s+al\s+)"


def expand_year(n: int) -> int:
    if n < 100:
        return 1900 + n if n >= 50 else 2000 + n
    return n


def extract_year_ranges(s: str) -> list[tuple[int, int]]:
    pat = rf"\b(19\d{{2}}|20\d{{2}}|\d{{2}}){_YEAR_SEP}(19\d{{2}}|20\d{{2}}|\d{{2}})\b"
    out = []
    for m in re.finditer(pat, s):
        a, b = expand_year(int(m.group(1))), expand_year(int(m.group(2)))
        if a <= b:
            out.append((a, b))
    return out


# --- term matching (plural-insensitive, token-bag) -------------------------

def term_matches(term: str, name_norm: str) -> bool:
    tokens = [t.rstrip("s") for t in norm(term).split() if len(t) > 2]
    if not tokens:
        return False
    return all(re.search(rf"\b{re.escape(t)}s?\b", name_norm) for t in tokens)


# --- scoring (generic, driven by vehicle profile) --------------------------

def score_item(product: dict, vehicle: dict) -> tuple[int, list[str]]:
    name = norm(product["name"])
    desc = norm(strip_html(product.get("description", "")))
    text = f"{name} || {desc}"
    notes: list[str] = []
    s = 0

    ranges = extract_year_ranges(text)
    year = int(vehicle["year"])
    if ranges:
        if any(a <= year <= b for a, b in ranges):
            s += 15
            notes.append(f"+15 año {year} en rango del título")
        else:
            mn = min(a for a, _ in ranges)
            mx = max(b for _, b in ranges)
            s -= 30
            notes.append(f"-30 año {year} fuera de {mn}-{mx}")

    disp = vehicle.get("displacement")
    if disp:
        disp_re = rf"(?<!\d){re.escape(str(disp))}(?!\d)"
        if re.search(disp_re, name):
            s += 25
            notes.append(f"+25 cilindrada {disp} en título")
        elif re.search(disp_re, desc):
            s += 12
            notes.append(f"+12 cilindrada {disp} en descripción")

    engine = (vehicle.get("engineCode") or "").lower()
    if engine and re.search(rf"\b{re.escape(engine)}\b", text):
        s += 20
        notes.append(f"+20 motor {engine}")

    chassis = (vehicle.get("chassis") or "").lower()
    if chassis:
        if chassis in name:
            s += 35
            notes.append(f"+35 chasis {chassis} en título")
        elif chassis in desc:
            s += 15
            notes.append(f"+15 chasis {chassis} en descripción")

    drive = (vehicle.get("drive") or "").lower()
    if drive and re.search(rf"\b{re.escape(drive)}\b", text):
        s += 10
        notes.append(f"+10 {drive}")

    for q in (str(q).lower() for q in vehicle.get("qualifiers", [])):
        if not q or q in (engine, chassis, drive, str(disp).lower() if disp else ""):
            continue
        if re.search(rf"\b{re.escape(q)}\b", text):
            s += 5
            notes.append(f"+5 calificador '{q}'")

    for d in (str(d).lower() for d in vehicle.get("disqualifiers", [])):
        if not d:
            continue
        if re.search(rf"\b{re.escape(d)}\b", name):
            s -= 25
            notes.append(f"-25 descalificador '{d}' en título")

    return s, notes


# --- orchestration ---------------------------------------------------------

def load_adapter(name: str, config: dict):
    mod = importlib.import_module(f"adapters.{name}")
    return mod.Adapter(config)


def load_site(slug: str) -> dict:
    fm, _ = read_mdx(SITES_DIR / f"{slug}.mdx")
    fm["slug"] = slug
    return fm


def load_vehicle(slug: str) -> dict:
    fm, _ = read_mdx(VEHICLES_DIR / f"{slug}.mdx")
    fm["slug"] = slug
    return fm


def fetch_or_load_catalog(adapter, site_slug: str, vehicle: dict, refresh: bool) -> list:
    cache = CATALOGS_DIR / f"{site_slug}-{vehicle['slug']}.json"
    if cache.exists() and not refresh:
        items = json.loads(cache.read_text())
        if items and "site" in items[0]:
            print(f"  loaded {len(items)} cached items from {cache.name}", file=sys.stderr)
            return items
        print(f"  cache {cache.name} is in legacy format — refreshing", file=sys.stderr)
    query = (vehicle.get("model") or vehicle.get("make") or "").split()[-1].lower()
    items = adapter.fetch_catalog(query)
    cache.write_text(json.dumps(items, ensure_ascii=False))
    print(f"  cached {len(items)} items to {cache.name}", file=sys.stderr)
    return items


def find_candidates(item: dict, catalog: list, vehicle: dict, top: int = 10) -> list[dict]:
    out: list[dict] = []
    search_terms = item.get("searchTerms") or []
    exclude_prefixes = [norm(p) for p in (item.get("excludeTitlePrefixes") or [])]
    for p in catalog:
        nm = norm(p["name"])
        matched = [t for t in search_terms if term_matches(t, nm)]
        if not matched:
            continue
        s, notes = score_item(p, vehicle)
        out.append({
            "site": p["site"],
            "url": p["url"],
            "title": p["name"],
            "sku": p.get("sku"),
            "score": s,
            "notes": notes,
        })
    # Carry-forward: merge existing alternates by URL. A URL still in the live
    # catalog gets a fresh score (out wins on dedupe); a URL no longer present
    # keeps its last-known score and survives if it still beats the cull.
    by_url: dict[str, dict] = {c["url"]: c for c in out}
    for e in (item.get("alternates") or []):
        by_url.setdefault(e["url"], e)
    merged = list(by_url.values())
    if exclude_prefixes:
        merged = [
            c for c in merged
            if not any(norm(c["title"]).startswith(pre) for pre in exclude_prefixes)
        ]
    merged.sort(key=lambda c: -c["score"])
    return merged[:top]


def run_hunt(hunt_slug: str, refresh: bool = False) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    hunt_path = HUNTS_DIR / f"{hunt_slug}.mdx"
    fm, body = read_mdx(hunt_path)
    vehicle = load_vehicle(fm["vehicle"])

    catalogs: dict[str, list] = {}
    for site_slug in vehicle.get("huntOn", []):
        site = load_site(site_slug)
        config = {"baseUrl": site["baseUrl"], **(site.get("config") or {})}
        adapter = load_adapter(site["adapter"], config)
        catalogs[site_slug] = fetch_or_load_catalog(adapter, site_slug, vehicle, refresh)

    combined = [p for items in catalogs.values() for p in items]
    print(f"  scoring against {len(combined)} catalog items across {len(catalogs)} site(s)", file=sys.stderr)

    snapshot = {"date": date.today().isoformat(), "vehicle": vehicle["slug"], "items": {}}

    for item in fm.get("items") or []:
        alternates = find_candidates(item, combined, vehicle)
        item["alternates"] = alternates
        snapshot["items"][item["id"]] = alternates

    fm["lastRun"] = date.today()
    write_mdx(hunt_path, fm, body)

    snapshot_file = RUNS_DIR / f"{hunt_slug}.{date.today().isoformat()}.json"
    snapshot_file.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
    print(f"Wrote {hunt_path.relative_to(ROOT)} and {snapshot_file.relative_to(ROOT)}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hunt_slug")
    ap.add_argument("--refresh", action="store_true", help="Re-fetch catalogs from all sites")
    args = ap.parse_args()
    run_hunt(args.hunt_slug, refresh=args.refresh)


if __name__ == "__main__":
    main()
