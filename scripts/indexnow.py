#!/usr/bin/env python3
"""Tell Bing (and every engine in IndexNow: Yandex, Seznam, Naver; Bing also feeds ChatGPT search and DuckDuckGo)
about the site's public pages, read from the live sitemap. No account is needed: ownership is shown by the key
file served at https://deal-intelligence.app/<key>.txt. The key is public by design."""
from __future__ import annotations

import json
import re
import sys
from urllib.request import Request, urlopen

HOST = "deal-intelligence.app"
KEY = "c5628a9c5a15747df9b85d0bb07ab312"


def main() -> int:
    with urlopen(f"https://{HOST}/sitemap.xml", timeout=30) as r:
        urls = re.findall(r"<loc>([^<]+)</loc>", r.read().decode())
    if not urls:
        print("sitemap is empty; nothing to submit")
        return 1
    body = json.dumps({"host": HOST, "key": KEY, "keyLocation": f"https://{HOST}/{KEY}.txt",
                       "urlList": urls[:10000]}).encode()
    req = Request("https://api.indexnow.org/indexnow", data=body, method="POST",
                  headers={"Content-Type": "application/json; charset=utf-8"})
    with urlopen(req, timeout=30) as r:
        print(f"submitted {len(urls)} URLs: HTTP {r.status}")
        return 0 if r.status in (200, 202) else 1


if __name__ == "__main__":
    sys.exit(main())
