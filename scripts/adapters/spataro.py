"""WordPress + WooCommerce Store API adapter for spatarorepuestos.com (Neuquén).

Structurally identical to the nipponpartsweb adapter, with one enrichment:
Spataro exposes per-product attributes (`Año`, `Motor`, `OEM`, `Tipo`, etc.)
that nipponpartsweb does not. We synthesise those attribute terms into the
normalised `description` field so the matcher's existing text-based scoring
(year-range / displacement / engine / drive / qualifiers) picks them up
without requiring any change to hunt.py.
"""
import json
import sys
import time
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17 Safari/605.1.15"


class Adapter:
    site_id = "spataro"

    def __init__(self, config: dict):
        self.api = f"{config['baseUrl']}{config['apiPath']}"
        self.per_page = int(config.get("perPage", 100))
        self.rate_limit = float(config.get("rateLimitSeconds", 0.4))

    def _get(self, url: str):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
            headers = dict(r.headers)
        return data, headers

    def fetch_catalog(self, query: str) -> list:
        out, page = [], 1
        while True:
            q = urllib.parse.quote(query)
            url = f"{self.api}?per_page={self.per_page}&page={page}&search={q}"
            items, headers = self._get(url)
            if not items:
                break
            for p in items:
                out.append(self._normalize(p))
            total_pages = int(headers.get("X-WP-TotalPages", 1))
            total = int(headers.get("X-WP-Total", len(out)))
            print(f"  [{self.site_id}] search={query!r}: page {page}/{total_pages} ({len(out)}/{total})", file=sys.stderr)
            if page >= total_pages:
                break
            page += 1
            time.sleep(self.rate_limit)
        return out

    def _normalize(self, p: dict) -> dict:
        attr_lines: list[str] = []
        years: list[int] = []
        for a in p.get("attributes", []) or []:
            name = (a.get("name") or "").strip()
            terms = [t.get("name", "") for t in (a.get("terms") or [])]
            terms = [t for t in terms if t]
            if not terms:
                continue
            attr_lines.append(f"{name}: {' '.join(terms)}")
            if name.lower() in ("año", "ano"):
                for t in terms:
                    try:
                        years.append(int(t))
                    except ValueError:
                        pass

        # Spataro lists Año as discrete year terms (e.g. ["2001","2002","2003","2004"]).
        # extract_year_ranges() in hunt.py only matches YYYY-YYYY patterns, so emit a
        # synthetic min-max range for it to find.
        if years:
            attr_lines.append(f"Año range: {min(years)}-{max(years)}")

        original_desc = p.get("description", "") or ""
        parts: list[str] = []
        if original_desc.strip():
            parts.append(original_desc)
        if attr_lines:
            parts.append(" | ".join(attr_lines))
        enriched_desc = " || ".join(parts)

        return {
            "site": self.site_id,
            "id": str(p.get("id", "")),
            "name": p.get("name", ""),
            "description": enriched_desc,
            "sku": p.get("sku") or None,
            "url": p.get("permalink", ""),
            "in_stock": bool(p.get("is_in_stock", True)),
        }
