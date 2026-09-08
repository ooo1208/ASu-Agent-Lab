"""Serve synthetic supplier quotations without external services or model calls.

    python src/mcp_server/quote_server.py
    python src/mcp_server/quote_server.py --write-mapping

QUOTE_BASE_URL controls URLs written into the Skill mapping; QUOTE_HOST/QUOTE_PORT
control the listener. A sandbox's localhost is not the Windows/Linux host.
"""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mcp_server.server_config import QUOTE_BASE_URL, QUOTE_HOST, QUOTE_PORT

PAGES = Path(__file__).resolve().parent / "html_quote"
MAPPING = SRC_DIR / "skills/procurement/supplier-price-urls/data/url_mapping.yaml"


def mapping_document(base_url: str) -> dict:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("QUOTE_BASE_URL must be an absolute http(s) URL reachable by the page consumer")
    catalog = json.loads((PAGES / "quotes.json").read_text(encoding="utf-8"))
    return {"data_kind": "synthetic", "as_of": catalog["as_of"], "quote_base_url": base_url.rstrip("/"),
            "mappings": [{"part_id": row["part_id"], "part_name": row["part_name"], "supplier_id": row["supplier_id"],
                          "supplier": row["supplier"], "url": base_url.rstrip("/") + "/" + row["page"]}
                         for row in catalog["quotes"]]}


def write_mapping(base_url: str) -> None:
    # JSON is a valid YAML document and avoids implicit date/number conversions.
    MAPPING.parent.mkdir(parents=True, exist_ok=True)
    MAPPING.write_text(json.dumps(mapping_document(base_url), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class QuoteHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] == "/mapping.json":
            body = json.dumps(mapping_document(self.server.quote_base_url), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def main():
    parser = argparse.ArgumentParser(description="Serve only the project's synthetic quotation pages")
    parser.add_argument("--host", default=QUOTE_HOST)
    parser.add_argument("--port", type=int, default=QUOTE_PORT)
    parser.add_argument("--base-url", default=QUOTE_BASE_URL)
    parser.add_argument("--write-mapping", action="store_true", help="Update the Skill URL mapping before serving; then sync Skills into the sandbox")
    parser.add_argument("--mapping-only", action="store_true", help="Only write the Skill URL mapping")
    args = parser.parse_args()
    mapping_document(args.base_url)
    if args.write_mapping or args.mapping_only:
        write_mapping(args.base_url)
    if args.mapping_only:
        return
    server = ThreadingHTTPServer((args.host, args.port), partial(QuoteHandler, directory=str(PAGES)))
    server.quote_base_url = args.base_url
    print(f"Synthetic quote service: http://{args.host}:{args.port}; published base URL: {args.base_url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
