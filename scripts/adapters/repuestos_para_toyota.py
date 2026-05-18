"""WordPress + WooCommerce Store API adapter for repuestosparatoyota.com.ar.

Structurally identical to the nipponpartsweb adapter — same WC Store API
shape, same pagination headers. Products carry an empty `attributes[]`,
so there's no per-product enrichment to do (unlike the spataro adapter).
"""
import json
import sys
import time
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17 Safari/605.1.15"


class Adapter:
    site_id = "repuestos-para-toyota"

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
        return {
            "site": self.site_id,
            "id": str(p.get("id", "")),
            "name": p.get("name", ""),
            "description": p.get("description", ""),
            "sku": p.get("sku") or None,
            "url": p.get("permalink", ""),
            "in_stock": bool(p.get("is_in_stock", True)),
        }
