"""
Синхронизация данных из Notion → bots.json + images/
Запускается GitHub Action'ом автоматически.
"""

import requests
import json
import os
import re
import time
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


# ─── Notion API ──────────────────────────────────────────────────────────────

def query_database():
    """Получаем все активные боты (Статус = Yes) с пагинацией."""
    pages, cursor = [], None
    while True:
        body = {
            "filter": {
                "or": [
                    {"property": "Статус", "select":   {"equals": "Yes"}},
                    {"property": "Статус", "status":   {"equals": "Yes"}},
                    {"property": "Статус", "checkbox": {"equals": True}},
                ]
            },
            "page_size": 100,
        }
        if cursor:
            body["start_cursor"] = cursor

        r = requests.post(
            f"https://api.notion.com/v1/databases/{DATABASE_ID}/query",
            headers=HEADERS, json=body, timeout=30,
        )
        if r.status_code != 200:
            print(f"⚠ API error {r.status_code}: {r.text[:300]}")
            # Пробуем без фильтра если первый запрос упал
            if cursor is None:
                r2 = requests.post(
                    f"https://api.notion.com/v1/databases/{DATABASE_ID}/query",
                    headers=HEADERS, json={"page_size": 100}, timeout=30,
                )
                data = r2.json()
            else:
                break
        else:
            data = r.json()

        pages.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        time.sleep(0.15)

    return pages


# ─── Парсинг свойств ─────────────────────────────────────────────────────────

def prop_text(prop) -> str:
    if not prop:
        return ""
    t = prop.get("type", "")
    if t == "title":
        return "".join(x["plain_text"] for x in prop.get("title", []))
    if t == "rich_text":
        return "".join(x["plain_text"] for x in prop.get("rich_text", []))
    if t == "url":
        return prop.get("url") or ""
    if t == "select":
        s = prop.get("select")
        return s["name"] if s else ""
    if t == "status":
        s = prop.get("status")
        return s["name"] if s else ""
    return ""


def prop_tags(prop) -> list:
    if not prop:
        return []
    t = prop.get("type", "")
    if t == "multi_select":
        return ["#" + s["name"].lstrip("#") for s in prop.get("multi_select", [])]
    # Если теги хранятся как plain text
    raw = prop_text(prop)
    return re.findall(r"#\S+", raw)


def extract_author_name(url: str) -> str:
    if not url:
        return "Unknown"
    if "janitorai.com/profiles/" in url:
        parts = url.split("_profile-of-")
        if len(parts) > 1:
            name = unquote(parts[-1]).replace("-", " ").strip()
            return name.title()
    if "t.me/" in url:
        return "@" + url.split("t.me/")[-1].rstrip("/")
    return url


def get_cover_url(page: dict) -> str | None:
    """Обложка страницы или файл в свойстве Карточка."""
    props = page.get("properties", {})

    # 1. Свойство "Карточка" (Files & Media)
    card = props.get("Карточка", {})
    if card.get("type") == "files" and card.get("files"):
        f = card["files"][0]
        if f["type"] == "file":
            return f["file"]["url"]
        if f["type"] == "external":
            return f["external"]["url"]

    # 2. Обложка страницы
    cover = page.get("cover")
    if cover:
        if cover["type"] == "file":
            return cover["file"]["url"]
        if cover["type"] == "external":
            return cover["external"]["url"]

    return None


def download_image(url: str, safe_name: str) -> str | None:
    """Скачивает изображение, возвращает путь или None."""
    if not url:
        return None
    dest = IMAGES_DIR / safe_name
    # Не перекачиваем если уже есть
    if dest.exists():
        return f"images/{safe_name}"
    try:
        r = requests.get(url, timeout=30, stream=True)
        if r.status_code == 200:
            dest.write_bytes(r.content)
            return f"images/{safe_name}"
    except Exception as e:
        print(f"  ⚠ Не удалось скачать {safe_name}: {e}")
    return None


def safe_filename(name: str) -> str:
    return re.sub(r"[^\w\-.]", "_", name)[:80] + ".jpg"


# ─── Основной цикл ───────────────────────────────────────────────────────────

def main():
    print("🔄 Запрос к Notion API...")
    pages = query_database()
    print(f"   Получено записей: {len(pages)}")

    bots = []
    for page in pages:
        props = page.get("properties", {})

        name = prop_text(props.get("Имя"))
        if not name:
            continue

        # Статус — пробуем отфильтровать вручную если API-фильтр не сработал
        status = prop_text(props.get("Статус"))
        if status and status.lower() not in ("yes", "да", ""):
            continue

        author_url   = prop_text(props.get("Автор"))
        author_name  = extract_author_name(author_url)
        account_url  = prop_text(props.get("Аккаунт автора"))
        janitor_url  = prop_text(props.get("Ссылка на Janitor"))
        description  = prop_text(props.get("Описание"))
        scenario     = prop_text(props.get("Сценарий"))
        tags         = prop_tags(props.get("Тэги"))

        # Изображение
        img_url  = get_cover_url(page)
        img_path = download_image(img_url, safe_filename(name)) if img_url else None
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

    authors = sorted({b["author"] for b in bots if b["author"] not in ("Unknown", "")})

    out = {"bots": bots, "authors": authors, "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open("bots.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"✅ Готово: {len(bots)} ботов, {len(authors)} авторов → bots.json")


if __name__ == "__main__":
    main()
