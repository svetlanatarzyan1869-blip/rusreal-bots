"""
Синхронизация данных из Notion → bots.json + images/
"""

import requests, json, os, re, time
from pathlib import Path
from urllib.parse import unquote

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
DATABASE_ID  = "35b3030e84d880d0a00afbc3053bdabb"
IMAGES_DIR   = Path("images")
IMAGES_DIR.mkdir(exist_ok=True)

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

def query_database():
    """Все страницы базы с пагинацией (без фильтра — фильтруем сами)."""
    pages, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(
            f"https://api.notion.com/v1/databases/{DATABASE_ID}/query",
            headers=HEADERS, json=body, timeout=30,
        )
        if r.status_code != 200:
            print(f"⚠ API error {r.status_code}: {r.text[:300]}")
            break
        data = r.json()
        pages.extend(data.get("results", []))
        print(f"  загружено страниц: {len(pages)}")
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        time.sleep(0.2)
    return pages

def prop_text(prop) -> str:
    if not prop: return ""
    t = prop.get("type", "")
    if t == "title":     return "".join(x["plain_text"] for x in prop.get("title", []))
    if t == "rich_text": return "".join(x["plain_text"] for x in prop.get("rich_text", []))
    if t == "url":       return prop.get("url") or ""
    if t == "select":    s = prop.get("select");  return s["name"] if s else ""
    if t == "status":    s = prop.get("status");  return s["name"] if s else ""
    return ""

def prop_tags(prop) -> list:
    if not prop: return []
    if prop.get("type") == "multi_select":
        return ["#" + s["name"].lstrip("#") for s in prop.get("multi_select", [])]
    raw = prop_text(prop)
    return re.findall(r"#\S+", raw)

def extract_author_name(url: str) -> str:
    if not url: return "Unknown"
    if "janitorai.com/profiles/" in url:
        parts = url.split("_profile-of-")
        if len(parts) > 1:
            return unquote(parts[-1]).replace("-", " ").strip().title()
    if "t.me/" in url:
        return "@" + url.split("t.me/")[-1].rstrip("/")
    return url

def get_cover_url(page):
    props = page.get("properties", {})
    card = props.get("Карточка", {})
    if card.get("type") == "files" and card.get("files"):
        f = card["files"][0]
        return f["file"]["url"] if f["type"] == "file" else f["external"]["url"]
    cover = page.get("cover")
    if cover:
        return cover["file"]["url"] if cover["type"] == "file" else cover["external"]["url"]
    return None

def download_image(url, safe_name):
    if not url: return None
    dest = IMAGES_DIR / safe_name
    if dest.exists(): return f"images/{safe_name}"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            dest.write_bytes(r.content)
            return f"images/{safe_name}"
    except Exception as e:
        print(f"  ⚠ {safe_name}: {e}")
    return None

def safe_fn(name): return re.sub(r"[^\w\-.]", "_", name)[:80] + ".jpg"

def main():
    print("🔄 Запрос к Notion API...")
    pages = query_database()
    print(f"   Всего записей: {len(pages)}")

    bots = []
    for page in pages:
        props = page.get("properties", {})

        # Фильтр по статусу
        status = prop_text(props.get("Статус")).strip().lower()
        if status and status not in ("yes", "да"):
            continue

        name = prop_text(props.get("Имя")).strip()
        if not name: continue

        author_url  = prop_text(props.get("Автор")).strip()
        account_url = prop_text(props.get("Аккаунт автора")).strip()
        author_name = extract_author_name(author_url)
        janitor_url = prop_text(props.get("Ссылка на Janitor")).strip()
        description = prop_text(props.get("Описание")).strip()
        scenario    = prop_text(props.get("Сценарий")).strip()
        tags        = prop_tags(props.get("Тэги"))

        # Пропускаем пустые технические записи
        if not description and not janitor_url and not tags:
            continue

        img_url  = get_cover_url(page)
        img_path = download_image(img_url, safe_fn(name)) if img_url else None
        time.sleep(0.05)

        bots.append({
            "id":          page["id"],
            "name":        name,
            "author":      author_name,
            "authorUrl":   author_url if author_url.startswith("http") else (account_url or ""),
            "image":       img_path,
            "description": description,
            "scenario":    scenario,
            "janitorUrl":  janitor_url,
            "tags":        tags,
        })

    # Сортировка по имени
    bots.sort(key=lambda b: b["name"].lower())
    authors = sorted({b["author"] for b in bots if b["author"] not in ("Unknown", "")})

    out = {"bots": bots, "authors": authors, "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open("bots.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"✅ Готово: {len(bots)} ботов, {len(authors)} авторов")

if __name__ == "__main__":
    main()
