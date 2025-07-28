#!/usr/bin/env python3
"""
Steam Popular New Releases Capsules

Opis:
    Pobiera popularne nowe gry ze Steam Search API, zapisuje unikalne rekordy do lokalnego cache'u (JSON),
    oraz (opcjonalnie) pobiera i zapisuje obrazy głównych kapsuł lokalnie.
    Dodatkowo zbiera tagi każdej gry i generuje interaktywną galerię HTML z filtrowaniem po tagach.

Funkcje:
    - Cache unikalnych gier w `cache.json` (z czasem `first_seen`).
    - Opcja `--download` zapisuje obrazy w `capsules/` z nazwami opartymi na tytule gry.
    - Opcja `--gallery` generuje `gallery.html`:
        * Responsywny grid: 3 kolumny (szerokie), 2 kolumny (≤1200px), 1 (≤768px).
        * Karty są linkami do strony Steam gry.
        * Overlay z tytułem i tagami.
        * Filtry tagów pokazują/ukrywają karty po kliknięciu.

Zależności:
    - Python 3
    - requests
    - beautifulsoup4

Instalacja:
    pip install --upgrade pip
    pip install requests beautifulsoup4

Użycie:
    python steam_popular_new_capsules.py [--download] [--gallery]
"""
import os
import sys
import re
import json
import argparse
from datetime import datetime, timezone, timedelta

# Sprawdzenie zależności
try:
    import requests
except ModuleNotFoundError:
    print("Module 'requests' not found. Install with: pip install requests")
    sys.exit(1)
try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:
    print("Module 'beautifulsoup4' not found. Install with: pip install beautifulsoup4")
    sys.exit(1)

# Konfiguracja
BASE_DIR = os.path.dirname(__file__)
CACHE_FILE = os.path.join(BASE_DIR, 'cache.json')
CAPSULE_DIR = os.path.join(BASE_DIR, 'capsules')
CET = timezone(timedelta(hours=2))  # Europe/Warsaw time


def load_cache():
    if not os.path.exists(CACHE_FILE):
        return []
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_cache(cache):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def sanitize_filename(name):
    clean = re.sub(r'[^0-9A-Za-z _-]', '', name)
    return clean.strip().replace(' ', '_')


def fetch_main_capsule_url(appid):
    url = f"https://store.steampowered.com/app/{appid}"
    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')
    meta = soup.select_one('meta[name="twitter:image"]')
    if not meta or not meta.get('content'):
        raise RuntimeError(f"Main capsule not found for appid {appid}")
    return meta['content']


def fetch_tags(appid):
    url = f"https://store.steampowered.com/app/{appid}"
    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')
    anchors = soup.select('a.app_tag')
    seen, tags = set(), []
    for a in anchors:
        t = a.get_text(strip=True)
        if t and t not in seen:
            seen.add(t)
            tags.append(t)
        if len(tags) >= 5:
            break
    return tags


def fetch_popular_new_releases(page=1):
    url = "https://store.steampowered.com/search/results/"
    params = {"filter": "popularnew", "sort_by": "Released_DESC", "json": 1, "page": page}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    rows = []
    if 'results_html' in data:
        rows = BeautifulSoup(data['results_html'], 'html.parser').select('a.search_result_row')
    elif 'items' in data and isinstance(data['items'], list):
        for item in data['items']:
            name, logo = item.get('name'), item.get('logo')
            m = re.search(r'/steam/apps/(\d+)/', logo or '')
            if m:
                fake = f'<a data-ds-appid="{m.group(1)}"><span class="title">{name}</span></a>'
                rows.append(BeautifulSoup(fake, 'html.parser').a)
    else:
        raise RuntimeError(f"Unexpected JSON structure: {data!r}")
    games = []
    for a in rows:
        appid = a.get('data-ds-appid')
        title_el = a.select_one('span.title')
        if appid and title_el:
            games.append({'appid': appid, 'title': title_el.get_text(strip=True)})
    return games


def download_image(url, path):
    resp = requests.get(url)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(resp.content)


def update_cache_with_new(download=False):
    cache = load_cache()
    existing = {g['appid'] for g in cache}
    new_games = []
    for g in fetch_popular_new_releases():
        if g['appid'] not in existing:
            g['main_capsule_url'] = fetch_main_capsule_url(g['appid'])
            g['tags'] = fetch_tags(g['appid'])
            g['first_seen'] = datetime.now(CET).isoformat()
            if download:
                fn = sanitize_filename(g['title']) + '.jpg'
                outp = os.path.join(CAPSULE_DIR, fn)
                download_image(g['main_capsule_url'], outp)
                g['image_path'] = os.path.relpath(outp, BASE_DIR)
            cache.append(g)
            new_games.append(g)
    if new_games:
        save_cache(cache)
    return new_games


def generate_gallery(output_file):
    cache = load_cache()
    tag_counts = {}
    for it in cache:
        for t in it.get('tags', []):
            tag_counts[t] = tag_counts.get(t, 0) + 1
    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
    html = [
        '<!DOCTYPE html>',
        '<html lang="pl">',
        '<head>',
        '  <meta charset="UTF-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        '  <title>Steam Popular New Releases Gallery</title>',
        '  <style>',
        '    body{margin:0;padding:20px;font-family:sans-serif;}',
        '    .container{max-width:1920px;margin:0 auto;padding:10px;}',
        '    .filters{margin-bottom:20px;}',
        '    .filter{display:inline-block;margin:0 10px 10px 0;padding:5px 10px;background:#eee;border-radius:5px;cursor:pointer;}',
        '    .filter.active{background:#6cf;color:#000;}',
        '    .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:15px;}',
        '    @media(max-width:1200px){.grid{grid-template-columns:repeat(2,1fr);}}',
        '    @media(max-width:768px){.grid{grid-template-columns:1fr;}}',
        '    .card{position:relative;overflow:hidden;}',
        '    .card img{width:100%;height:auto;display:block;}',
        '    .overlay{position:absolute;top:0;left:0;width:100%;height:100%;',
        '             background:rgba(0,0,0,0.6);color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;',
        '             text-align:center;padding:10px;opacity:0;transition:opacity .3s;}',
        '    .card:hover .overlay{opacity:1;}',
        '    .overlay .title{font-size:1.2em;font-weight:bold;margin-bottom:.5em;}',
        '    .overlay .tags{font-size:.9em;}',
        '  </style>',
        '  <script>',
        '    document.addEventListener("DOMContentLoaded",()=>{',
        '      const filters = document.querySelectorAll(".filter");',
        '      filters.forEach(f=>{f.addEventListener("click",()=>{',
        '        f.classList.toggle("active");',
        '        const active = Array.from(filters).filter(x=>x.classList.contains("active")).map(x=>x.dataset.tag);',
        '        document.querySelectorAll(".card").forEach(card=>{',
        '          const tags = card.dataset.tags ? card.dataset.tags.split(",") : [];',
        '          const show = active.length===0 || active.some(t=>tags.includes(t));',
        '          card.closest("a").style.display = show ? "block" : "none";',
        '        });',
        '      })});',
        '    });',
        '  </script>',
        '</head>',
        '<body>',
        '  <div class="container">',
        '    <h1>Steam Popular New Releases Gallery</h1>',
        '    <div class="filters">'
    ]
    for tag, count in sorted_tags:
        html.append(f'      <span class="filter" data-tag="{tag}">{tag} ({count})</span>')
    html.append('    </div>')
    html.append('    <div class="grid">')
    for it in cache:
        appid = it['appid']
        title = it['title']
        tags = it.get('tags', [])
        tags_attr = ",".join(tags)
        img_src = it.get('image_path') or it.get('main_capsule_url')
        html.append(
            f'      <a href="https://store.steampowered.com/app/{appid}" target="_blank" rel="noopener noreferrer">' +
            f'<div class="card" data-tags="{tags_attr}">' +
            f'<img src="{img_src}" alt="{title}">' +
            '<div class="overlay">' +
            f'<div class="title">{title}</div>' +
            f'<div class="tags">{", ".join(tags)}</div>' +
            '</div></div></a>'
        )
    html.append('    </div>')
    html.append('  </div>')
    html.append('</body>')
    html.append('</html>')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(html))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Steam Popular New Releases Capsules')
    parser.add_argument('--download', action='store_true', help='Pobierz obrazy kapsuł')
    parser.add_argument('--gallery', action='store_true', help='Wygeneruj galerię HTML')
    args = parser.parse_args()

    new_games = update_cache_with_new(download=args.download)
    if new_games:
        print(f"Dodano {len(new_games)} nowych gier:")
        for g in new_games:
            line = f"- {g['appid']} {g['title']} (Tags: {', '.join(g.get('tags', []))})"
            if args.download and 'image_path' in g:
                line += f" -> {g['image_path']}"
            print(line)
    else:
        print("Brak nowych gier.")

    if args.gallery:
        gallery_file = os.path.join(BASE_DIR, 'gallery.html')
        generate_gallery(gallery_file)
        print(f"Wygenerowano galerię: {gallery_file}")
