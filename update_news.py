"""Fetch public RSS/Atom feeds. Python 3.11+, standard library only."""
import argparse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

UTC = timezone.utc
AI_WORDS = re.compile(r"人工智能|大模型|机器学习|深度学习|神经网络|生成式|智能体|chatgpt|openai|anthropic|deepseek|openclaw|\btokens?\b|\bAI\b|\bLLM\b|\bGPT[- ]?\d", re.I)
TECH_WORDS = re.compile(r"科技|软件|硬件|芯片|半导体|浏览器|漏洞|内核|程序|机器人|航天|火星|量子|电池|linux|windows|android|apple|google|microsoft|keepass|CA 业务|美光", re.I)


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.blocked = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.blocked += 1
        if tag in ("p", "br", "div"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.blocked:
            self.blocked -= 1
        self.parts.append(" ")

    def handle_data(self, data):
        if not self.blocked:
            self.parts.append(data)


def plain(value):
    parser = PlainText()
    parser.feed(value or "")
    return re.sub(r"\s+", " ", unescape("".join(parser.parts))).strip()


def short_summary(value, language):
    text = plain(value)
    if language.startswith("zh"):
        return text[:80].rstrip() + ("…" if len(text) > 80 else "")
    words = text.split()
    return " ".join(words[:26]) + ("…" if len(words) > 26 else "")


def canonical_url(value):
    try:
        p = urlsplit(value.strip())
        if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
            return ""
        query = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")]
        return urlunsplit((p.scheme, p.netloc.lower(), p.path, urlencode(sorted(query)), ""))
    except (ValueError, AttributeError):
        return ""


def parse_date(value):
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        try:
            dt = parsedate_to_datetime(value)
        except (ValueError, TypeError, AttributeError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def child_text(entry, names):
    for name in names:
        for node in entry:
            if local_name(node.tag) == name and node.text:
                return "".join(node.itertext())
    return ""


def parse_feed(raw, source, now):
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("DTD/entity definitions are not supported")
    root = ET.fromstring(raw)
    items = []
    for entry in root.iter():
        if local_name(entry.tag) not in ("item", "entry"):
            continue
        title = plain(child_text(entry, ("title",)))
        link = child_text(entry, ("link",))
        if not link:
            link = next((n.get("href", "") for n in entry if local_name(n.tag) == "link" and n.get("rel", "alternate") == "alternate"), "")
        url = canonical_url(link)
        published = parse_date(child_text(entry, ("pubDate", "published", "date", "updated")))
        if not title or not url or not published:
            continue
        if published > now + timedelta(days=1) or published < now - timedelta(days=45):
            continue
        description = child_text(entry, ("description", "summary", "encoded", "content"))
        # Nature's encoded content starts with bibliographic boilerplate.
        description = re.sub(r"^\s*<p>Nature Chemistry,.*?</p>", "", description, flags=re.S)
        category = source["category"]
        if source["id"] == "solidot" and AI_WORDS.search(title):
            category = "AI"
        elif source["id"] == "solidot" and not TECH_WORDS.search(title):
            continue
        items.append({
            "category": category, "title": title[:250],
            "summary": short_summary(description, source["language"]) or "来源未提供简介，请访问原文阅读。",
            "source": source["name"], "sourceId": source["id"], "url": url,
            "publishedAt": published.isoformat().replace("+00:00", "Z"),
            "language": source["language"], "summaryType": "source-excerpt",
        })
    return items


def select_items(items, limit):
    result, urls, titles = [], set(), set()
    for item in sorted(items, key=lambda x: x["publishedAt"], reverse=True):
        url = canonical_url(item["url"])
        title = re.sub(r"\W+", "", item["title"]).casefold()
        if not url or url in urls or title in titles:
            continue
        urls.add(url)
        titles.add(title)
        result.append(item)
        if len(result) == limit:
            break
    return result


def download(url):
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "FrontierDaily/1.0 (+https://gaoyv1932-bit.github.io/daily-tech-news/)", "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
            with urlopen(request, timeout=25) as response:
                data = response.read(3_000_001)
                if len(data) > 3_000_000:
                    raise ValueError("Feed exceeds 3 MB")
                return data
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def collect(sources, previous, now, fetch=download):
    result, statuses = [], []
    success = 0
    for source in sources:
        try:
            candidates = parse_feed(fetch(source["url"]), source, now)
            items = select_items(candidates, source["limit"])
            if source["id"] == "solidot":
                ai = select_items([x for x in candidates if x["category"] == "AI"], 3)
                tech = select_items([x for x in candidates if x["category"] == "科技"], 3)
                items = select_items(ai + tech, source["limit"])
            if not items:
                raise ValueError("No recent dated articles found")
            success += 1
            status = {"id": source["id"], "name": source["name"], "status": "ok", "count": len(items)}
        except Exception as error:
            # Only reuse dated items from this source, up to 60 days old.
            items = [item for item in previous if item.get("sourceId") == source["id"] and (dt := parse_date(item.get("publishedAt", ""))) and now - timedelta(days=60) <= dt <= now + timedelta(days=1)]
            items = select_items(items, source["limit"])
            status = {"id": source["id"], "name": source["name"], "status": "stale" if items else "unavailable", "count": len(items)}
            print(f"::warning::{source['name']}: {error}", file=sys.stderr)
        result.extend(items)
        statuses.append(status)
    if not success:
        raise RuntimeError("All feeds failed; existing news files were preserved")
    result = select_items(result, 24)
    updated = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    return result, {"updatedAt": updated, "schedule": "每天北京时间 08:17 左右", "sources": statuses, "count": len(result)}


def atomic_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default=".")
    args = parser.parse_args()
    directory = Path(args.directory)
    sources = json.loads((directory / "feeds.json").read_text(encoding="utf-8"))
    news_path = directory / "news.json"
    previous = json.loads(news_path.read_text(encoding="utf-8")) if news_path.exists() else []
    items, metadata = collect(sources, previous, datetime.now(UTC))
    atomic_json(news_path, items)
    atomic_json(directory / "news-meta.json", metadata)
    print(json.dumps({"count": len(items), "sources": metadata["sources"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
