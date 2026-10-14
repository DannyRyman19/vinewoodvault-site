#!/usr/bin/env python3
"""Build the crawlable GTA 5 guide pages from pois.json.

Writes, relative to the site root:
  gta-5/index.html            hub: every category, Story Mode and Online
  gta-5/<category>.html       one page per category, every item listed
  images/maps/<category>.jpg  overview map with numbered pins (only with --tiles)
  sitemap.xml, robots.txt

pois.json stays the single source of truth: publish it as usual, then rerun
this. The maps need the app's tile pyramid, so they are only redrawn when
--tiles points at it; without it the existing map images are kept.

  python3 tools/build_guides.py
  uv run --with pillow python tools/build_guides.py --tiles ~/VinewoodVault/Resources/DevTiles
"""

import argparse
import datetime
import html
import json
import math
import os
import re
import sys

SITE = "https://vinewoodvault.djr.li"
APP_ID = "6806873745"
APP_URL = f"https://apps.apple.com/app/id{APP_ID}"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Mirrors Milestones.swift hundredPlusSection; a category's own "section" wins.
ONLINE = {
    "playing-cards", "signal-jammers", "action-figures", "store-robberies", "online-awards",
    "movie-props", "ld-organics", "online-peyote-plants",
    "bunker-research", "treasure-hunts", "snowmen",
}

# Search phrasing per category: what people actually type. Anything missing
# falls back to "<label> locations" / "<label> checklist".
SEARCH_NAME = {
    "missions": "Story Missions & Gold Medals",
    "stranger-missions": "Strangers and Freaks Missions",
    "achievements": "Trophies & Achievements",
    "online-awards": "Awards",
    "hobbies": "Hobbies and Pastimes",
    "online-peyote-plants": "Peyote Plants",
    "ld-organics": "LD Organics",
    "bunker-research": "Bunker Research Projects",
    "misc": "Miscellaneous 100% Tasks",
}

# Where "All N ..." reads wrong (missions counts branches and the finale
# choices, so 77 entries for 69 missions).
TITLE_OVERRIDE = {
    "missions": ("GTA 5 Missions List & Gold Medal Guide (All Objectives)",
                 "GTA 5 missions and gold medals"),
}


def esc(s):
    return html.escape(str(s), quote=True)


def is_online(cat):
    if cat.get("section") == "online" or cat.get("mode") == "online":
        return True
    if cat.get("section") == "singlePlayer":
        return False
    return cat["id"] in ONLINE


def game(cat):
    return "GTA Online" if is_online(cat) else "GTA 5"


# ---------------------------------------------------------------- text

LINK = re.compile(r"\[([^\]]+)\]\((poi|category):([^)]+)\)")


def rich(text, poi_cat):
    """Escape, then turn the app's [label](poi:id) links into page links."""
    out, last = [], 0
    for m in LINK.finditer(text):
        out.append(esc(text[last:m.start()]))
        label, kind, target = m.groups()
        if kind == "poi" and target in poi_cat:
            out.append(f'<a href="/gta-5/{poi_cat[target]}#{esc(target)}">{esc(label)}</a>')
        elif kind == "category":
            out.append(f'<a href="/gta-5/{esc(target)}">{esc(label)}</a>')
        else:
            out.append(esc(label))
        last = m.end()
    out.append(esc(text[last:]))
    return "".join(out)


def plain(text):
    return LINK.sub(lambda m: m.group(1), text)


def clip(text, n):
    text = " ".join(text.split())
    if len(text) <= n:
        return text
    cut = text[: n - 1].rsplit(" ", 1)[0].rstrip(",.;:")
    return cut + "…"


# ---------------------------------------------------------------- map

WORLD = 11.0  # MapConfig.worldSpan, degrees, centred on 0,0
WATER = (21, 65, 111)
Z = 9


def merc(lat, lon, z):
    n = 256 * (1 << z)
    x = (lon + 180) / 360 * n
    r = math.radians(lat)
    y = (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n
    return x, y


def world_px(nx, ny, z=Z):
    return merc(WORLD / 2 - ny * WORLD, -WORLD / 2 + nx * WORLD, z)


def build_base(tiles):
    from PIL import Image

    x0, y0 = merc(WORLD / 2, -WORLD / 2, Z)
    x1, y1 = merc(-WORLD / 2, WORLD / 2, Z)
    tx0, ty0, tx1, ty1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
    img = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256), WATER)
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            p = os.path.join(tiles, str(Z), str(tx), f"{ty}.jpg")
            if os.path.exists(p):
                img.paste(Image.open(p).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
    return img, tx0 * 256, ty0 * 256


def font(size):
    from PIL import ImageFont

    for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def draw_map(base, ox, oy, pins, hex_color, out_path):
    """pins: [(number, nx, ny)]. Crops to the pins with some context."""
    from PIL import Image, ImageDraw

    pts = [(n, *world_px(nx, ny)) for n, nx, ny in pins]
    xs = [x - ox for _, x, _ in pts]
    ys = [y - oy for _, _, y in pts]
    pad = 260
    left, right = max(min(xs) - pad, 0), min(max(xs) + pad, base.width)
    top, bottom = max(min(ys) - pad, 0), min(max(ys) + pad, base.height)
    # Keep a sane aspect so one-pin pages still show a neighbourhood.
    min_w = 900
    if right - left < min_w:
        c = (left + right) / 2
        left, right = max(c - min_w / 2, 0), min(c + min_w / 2, base.width)
    if bottom - top < min_w * 0.75:
        c = (top + bottom) / 2
        top, bottom = max(c - min_w * 0.375, 0), min(c + min_w * 0.375, base.height)
    crop = base.crop((int(left), int(top), int(right), int(bottom)))
    scale = min(1.0, 1100 / crop.width)
    crop = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.LANCZOS)

    d = ImageDraw.Draw(crop)
    color = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    r = 13 if len(pins) <= 60 else 10
    f = font(13 if r == 13 else 10)
    for n, x, y in sorted(pts, key=lambda p: p[2]):
        cx, cy = (x - ox - left) * scale, (y - oy - top) * scale
        d.ellipse((cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2), fill=(0, 0, 0))
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color, outline=(255, 255, 255), width=2)
        label = str(n)
        w = d.textlength(label, font=f)
        d.text((cx - w / 2, cy - f.size / 2 - 1), label, font=f, fill=(255, 255, 255),
               stroke_width=2, stroke_fill=(0, 0, 0))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    crop.save(out_path, "JPEG", quality=70, optimize=True, progressive=True)
    return crop.size


# ---------------------------------------------------------------- html

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<meta name="apple-itunes-app" content="app-id={app_id}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Vinewood Vault">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
{og_image}<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/logo.svg" type="image/svg+xml">
<link rel="stylesheet" href="/style.css">
<script type="application/ld+json">{ld}</script>
</head>
<body>
<header class="site">
  <div class="inner">
    <a class="wordmark" href="/"><img class="mark" src="/logo.svg" alt="">VINEWOOD VAULT</a>
    <nav>
      <a href="/gta-5/">Guides</a>
      <a href="/support">Support</a>
    </nav>
  </div>
</header>
"""

FOOT = """
<footer>
  Unofficial and not affiliated with Rockstar Games or Take-Two Interactive.
  Grand Theft Auto and GTA are trademarks of Take-Two Interactive Software.
  Game screenshots and map art belong to their respective owners.<br>
  &copy; {year} Vinewood Vault &middot;
  <a href="/privacy">Privacy</a> &middot; <a href="/terms">Terms</a> &middot;
  <a href="mailto:support@vinewoodvault.djr.li">support@vinewoodvault.djr.li</a>
</footer>
</body>
</html>
"""

CTA = """<aside class="cta">
  <p><strong>Tick them off as you go.</strong> Vinewood Vault tracks {what} on an
    offline map, alongside everything else you need for 100% in {game}.
    Free on iPhone and iPad.</p>
  <a class="appstore" href="{app_url}">
    <img src="/appstore-badge.svg" alt="Download Vinewood Vault on the App Store" width="180" height="60">
  </a>
</aside>"""


def head(title, desc, path, ld, image=None):
    og = ""
    if image:
        og = f'<meta property="og:image" content="{SITE}{image}">\n'
    return HEAD.format(title=esc(title), desc=esc(desc), url=f"{SITE}{path}", app_id=APP_ID,
                       og_image=og, ld=json.dumps(ld, ensure_ascii=False).replace("</", "<\\/"))


def crumbs(items):
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": f"{SITE}{p}"}
            for i, (n, p) in enumerate(items)
        ],
    }


def titles(cat, count, has_map):
    if cat["id"] in TITLE_OVERRIDE:
        return TITLE_OVERRIDE[cat["id"]]
    label = SEARCH_NAME.get(cat["id"], cat["label"])
    g = game(cat)
    if has_map:
        return (f"All {count} {g} {label} Locations (Map & Checklist)",
                f"{g} {label}: all {count} locations")
    return (f"All {count} {g} {label}: Full Checklist",
            f"{g} {label}: all {count}")


def item_html(i, p, cat, poi_cat, numbered):
    bits = [f'<li class="item" id="{esc(p["id"])}">']
    num = f'<span class="n">{i}</span>' if numbered else ""
    bits.append(f'<h3>{num}{esc(p["title"])}</h3>')
    meta = []
    if p.get("region") and p["region"] != p["title"]:
        meta.append(esc(p["region"]))
    for key, lab in (("givenBy", "Given by"), ("availableAfter", "After"), ("cost", "Cost"),
                     ("reward", "Reward"), ("weapon", "Weapons"), ("source", "Where"),
                     ("completeBefore", "Do before")):
        if p.get(key):
            meta.append(f"{lab}: {esc(p[key])}")
    if p.get("missable"):
        meta.append('<span class="flag">Missable</span>')
    if meta:
        bits.append(f'<p class="meta">{" &middot; ".join(meta)}</p>')
    img = p.get("imageURL") or p.get("iconURL")
    if img:
        cls = "shot" if p.get("imageURL") else "icon"
        bits.append(f'<img class="{cls}" src="{esc(img)}" alt="{esc(game(cat) + " " + p["title"])}" loading="lazy" decoding="async">')
    if p.get("note"):
        bits.append(f"<p>{rich(p['note'], poi_cat)}</p>")
    if p.get("guide"):
        bits.append(f'<p class="guide">{rich(p["guide"], poi_cat)}</p>')
    if p.get("branchNote"):
        bits.append(f'<p class="meta">{esc(p["branchNote"])}</p>')
    groups = list(p.get("objectiveGroups") or [])
    if p.get("objectives"):
        groups.insert(0, {"label": "Gold medal objectives" if cat["id"] == "missions" else "Objectives",
                          "objectives": p["objectives"]})
    for g in groups:
        bits.append(f'<p class="sub">{esc(g["label"])}</p><ul>'
                    + "".join(f"<li>{esc(o)}</li>" for o in g["objectives"]) + "</ul>")
    if p.get("stats"):
        bits.append('<p class="meta">' + " &middot; ".join(
            f"{esc(s['label'])}: {esc(s['value'])}" for s in p["stats"]) + "</p>")
    if p.get("table"):
        t = p["table"]
        bits.append('<div class="tablewrap"><table><thead><tr>'
                    + "".join(f"<th>{esc(h)}</th>" for h in t["headers"]) + "</tr></thead><tbody>"
                    + "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>" for row in t["rows"])
                    + "</tbody></table></div>")
    if p.get("videoURL"):
        bits.append(f'<p class="video"><a href="{esc(p["videoURL"])}" rel="nofollow noopener" target="_blank">Watch the video</a></p>')
    bits.append("</li>")
    return "\n".join(bits)


def category_page(cat, pois, poi_cat, cats, map_size, today):
    count = len(pois)
    pinned = [p for p in pois if "nx" in p]
    has_map = map_size is not None
    title, h1 = titles(cat, count, has_map and len(pinned) == count)
    intro = cat.get("intro") or ""
    lead = plain(intro) if intro else f"Every {cat['label'].lower()} in {game(cat)}, in one list."
    desc = clip(f"{h1}. {lead}", 158)
    path = f"/gta-5/{cat['id']}"
    image = f"/images/maps/{cat['id']}.jpg" if has_map else None

    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Article", "headline": h1, "description": desc, "dateModified": today,
             "image": f"{SITE}{image}" if image else None,
             "author": {"@type": "Organization", "name": "Vinewood Vault", "url": SITE},
             "about": {"@type": "VideoGame", "name": "Grand Theft Auto V"}},
            crumbs([("Vinewood Vault", "/"), ("GTA 5 guides", "/gta-5/"), (h1, path)]),
            {"@type": "ItemList", "numberOfItems": count, "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": p["title"], "url": f"{SITE}{path}#{p['id']}"}
                for i, p in enumerate(pois)]},
        ],
    }
    if not image:
        del ld["@graph"][0]["image"]

    out = [head(title, desc, path, ld, image), "<main class=\"guide\">"]
    out.append(f'<nav class="crumbs"><a href="/gta-5/">GTA 5 guides</a> &rsaquo; {esc(game(cat))}</nav>')
    out.append(f'<div class="titleblock"><p class="eyebrow">{esc(game(cat))} guide</p><h1>{esc(h1)}</h1>'
               f'<p class="updated">{count} {"entries" if count != 1 else "entry"} &middot; updated {esc(today)}</p></div>')
    if intro:
        out.append(f'<p class="lede">{rich(intro, poi_cat)}</p>')
    if has_map:
        w, h = map_size
        out.append(f'<figure class="map"><img src="{image}" width="{w}" height="{h}" '
                   f'alt="Map of all {count} {esc(game(cat))} {esc(cat["label"])} locations" loading="lazy" decoding="async">'
                   f'<figcaption>Numbers match the list below.</figcaption></figure>')
    out.append(CTA.format(what=f"all {count} {esc(cat['label'])}", game=esc(game(cat)), app_url=APP_URL))

    numbered = has_map
    groups, order = {}, []
    for p in pois:
        g = p.get("subgroup") or ""
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(p)
    n = 0
    for g in order:
        if g and len(order) > 1:
            out.append(f"<h2>{esc(g)}</h2>")
        out.append('<ol class="items">')
        for p in groups[g]:
            n += 1
            out.append(item_html(n, p, cat, poi_cat, numbered))
        out.append("</ol>")

    sibs = [c for c in cats if is_online(c) == is_online(cat) and c["id"] != cat["id"]]
    out.append(f"<h2>More {esc(game(cat))} guides</h2><ul class=\"related\">"
               + "".join(f'<li><a href="/gta-5/{esc(c["id"])}">{esc(c["label"])}</a></li>' for c in sibs)
               + "</ul>")
    out.append("</main>")
    out.append(FOOT.format(year=today[:4]))
    return "\n".join(out)


def hub_page(cats, counts, today):
    title = "GTA 5 100% Guide: Every Collectible, Mission & Trophy"
    desc = ("Complete GTA 5 and GTA Online checklists with maps: spaceship parts, letter scraps, "
            "stunt jumps, action figures, signal jammers, playing cards, gold medals and more.")
    ld = {"@context": "https://schema.org", "@graph": [
        crumbs([("Vinewood Vault", "/"), ("GTA 5 guides", "/gta-5/")]),
        {"@type": "CollectionPage", "name": title, "description": desc, "dateModified": today},
    ]}
    out = [head(title, desc, "/gta-5/", ld, "/images/maps/hub.jpg"), "<main class=\"guide\">"]
    out.append('<div class="titleblock"><p class="eyebrow">Guides</p><h1>GTA 5 100% guide</h1>'
               f'<p class="updated">{sum(counts.values())} entries across {len(cats)} checklists &middot; updated {esc(today)}</p></div>')
    out.append('<p class="lede">Every collectible, mission, hobby and trophy you need for 100% in '
               'Grand Theft Auto V, plus the GTA Online collectibles. Each list has a map and a short '
               'note on how to reach every item.</p>')
    for online, heading in ((False, "Story Mode"), (True, "GTA Online")):
        out.append(f"<h2>{heading}</h2><ul class=\"hub\">")
        for c in cats:
            if is_online(c) == online:
                out.append(f'<li><a href="/gta-5/{esc(c["id"])}">{esc(c["label"])}</a>'
                           f'<span>{counts[c["id"]]}</span></li>')
        out.append("</ul>")
    out.append(CTA.format(what="every checklist here", game="GTA 5 and GTA Online", app_url=APP_URL))
    out.append("</main>")
    out.append(FOOT.format(year=today[:4]))
    return "\n".join(out)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles", help="the app's Resources/DevTiles; redraws the maps")
    args = ap.parse_args()

    today = datetime.date.today().isoformat()
    data = json.load(open(os.path.join(ROOT, "pois.json"), encoding="utf-8"))
    cats = data["categories"]
    by = {c["id"]: [] for c in cats}
    for p in data["pois"]:
        by.setdefault(p["category"], []).append(p)
    poi_cat = {p["id"]: p["category"] for p in data["pois"]}
    counts = {c["id"]: len(by[c["id"]]) for c in cats}

    maps_dir = os.path.join(ROOT, "images", "maps")
    sizes = {}
    if args.tiles:
        base, ox, oy = build_base(os.path.expanduser(args.tiles))
        for c in cats:
            pins = [(i + 1, p["nx"], p["ny"]) for i, p in enumerate(by[c["id"]]) if "nx" in p]
            if len(pins) >= 2:
                draw_map(base, ox, oy, pins, c.get("colorHex", "FFB627"),
                         os.path.join(maps_dir, f"{c['id']}.jpg"))
        # Social card for the hub: the whole island, no pins.
        from PIL import Image
        x0, y0 = world_px(0.0, 0.0)
        x1, y1 = world_px(1.0, 1.0)
        hub = base.crop((int(x0 - ox), int(y0 - oy), int(x1 - ox), int(y1 - oy)))
        hub = hub.resize((1200, round(1200 * hub.height / hub.width)), Image.LANCZOS)
        top = max((hub.height - 630) // 2, 0)
        hub.crop((0, top, 1200, top + 630)).save(os.path.join(maps_dir, "hub.jpg"), "JPEG", quality=82)

    def map_size(cid):
        p = os.path.join(maps_dir, f"{cid}.jpg")
        if not os.path.exists(p):
            return None
        with open(p, "rb") as f:
            b = f.read()
        # Read width/height from the JPEG SOF marker, no Pillow needed.
        i = 2
        while i < len(b):
            marker, size = b[i + 1], int.from_bytes(b[i + 2:i + 4], "big")
            if marker in (0xC0, 0xC1, 0xC2):
                return int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big")
            i += 2 + size
        return None

    out_dir = os.path.join(ROOT, "gta-5")
    os.makedirs(out_dir, exist_ok=True)
    for c in cats:
        if not by[c["id"]]:
            continue
        page = category_page(c, by[c["id"]], poi_cat, cats, map_size(c["id"]), today)
        with open(os.path.join(out_dir, f"{c['id']}.html"), "w", encoding="utf-8") as f:
            f.write(page)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(hub_page([c for c in cats if by[c["id"]]], counts, today))

    urls = ["/", "/gta-5/"] + [f"/gta-5/{c['id']}" for c in cats if by[c["id"]]] + ["/support", "/privacy", "/terms"]
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for u in urls:
            f.write(f"  <url><loc>{SITE}{u}</loc><lastmod>{today}</lastmod></url>\n")
        f.write("</urlset>\n")
    with open(os.path.join(ROOT, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n")
    print(f"{len(urls)} urls, {len([c for c in cats if by[c['id']]])} category pages", file=sys.stderr)


if __name__ == "__main__":
    main()
