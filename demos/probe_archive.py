# probe_archive.py

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json

ARCHIVE_URL = "https://siji.typlog.io/archive/2022/"

headers = {
    "User-Agent": "Mozilla/5.0"
}

resp = requests.get(ARCHIVE_URL, headers=headers, timeout=30)
resp.raise_for_status()

html = resp.text

soup = BeautifulSoup(html, "html.parser")

episode_links = []

for a in soup.find_all("a", href=True):
    href = a["href"]

    if href.startswith("/episodes/") and href != "/episodes/":
        full = urljoin(ARCHIVE_URL, href)

        episode_links.append(full)

# 去重保持顺序
episode_links = list(dict.fromkeys(episode_links))

print(f"[INFO] found {len(episode_links)} episode links")

for idx, ep in enumerate(episode_links, 1):
    print(f"{idx:03d} {ep}")

# optional json dump
with open("episodes_2022.json", "w", encoding="utf-8") as f:
    json.dump(episode_links, f, ensure_ascii=False, indent=2)

print("[INFO] saved -> episodes_2022.json")