# probe_episode.py

import requests
from bs4 import BeautifulSoup
import re
import json

EPISODE_URL = "https://siji.typlog.io/episodes/yami"

headers = {
    "User-Agent": "Mozilla/5.0"
}

resp = requests.get(EPISODE_URL, headers=headers, timeout=30)
resp.raise_for_status()

html = resp.text

soup = BeautifulSoup(html, "html.parser")

result = {}

# -----------------------------
# title
# -----------------------------

title = None

h1 = soup.find("h1")

if h1:
    title = h1.get_text(strip=True)

if not title:
    meta_title = soup.find("meta", property="og:title")

    if meta_title:
        title = meta_title.get("content")

result["title"] = title

# -----------------------------
# cover
# -----------------------------

cover = None

meta_cover = soup.find("meta", property="og:image")

if meta_cover:
    cover = meta_cover.get("content")

result["cover"] = cover

# -----------------------------
# date
# -----------------------------

date = None

meta_date = soup.find("meta", property="article:published_time")

if meta_date:
    date = meta_date.get("content")

result["date"] = date

# -----------------------------
# description
# -----------------------------

desc = None

meta_desc = soup.find("meta", property="og:description")

if meta_desc:
    desc = meta_desc.get("content")

result["description"] = desc

# -----------------------------
# mp3 extraction
# -----------------------------

mp3 = None

# try audio tag
audio = soup.find("audio")

if audio and audio.get("src"):
    mp3 = audio.get("src")

# try source tag
if not mp3:
    source = soup.find("source")

    if source and source.get("src"):
        mp3 = source.get("src")

# regex fallback
if not mp3:
    matches = re.findall(r'https://[^"]+\.mp3[^"]*', html)

    if matches:
        mp3 = matches[0]

result["mp3"] = mp3

# -----------------------------
# output
# -----------------------------

print(json.dumps(result, ensure_ascii=False, indent=2))

with open("episode_probe.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("[INFO] saved -> episode_probe.json")

headers = []

for h in soup.find_all(["h1", "h2", "h3"]):
    text = h.get_text(strip=True)

    if text:
        headers.append(text)

episode_title = headers[2]
print(episode_title)