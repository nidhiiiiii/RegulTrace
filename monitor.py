import html
import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import analyze
import graph

IST = timezone(timedelta(hours=5, minutes=30))
FEEDS = {
    "RBI notification": "https://www.rbi.org.in/notifications_rss.xml",
    "RBI press release": "https://www.rbi.org.in/pressreleases_rss.xml",
}
IN_SCOPE = re.compile(
    r"\b(upi|payment system|payment aggregator|digital lending|loans?|borrowers?|kyc|know your customer|"
    r"personal data|data protection|grievance|complaints?|ombudsman|fraud|cyber|nbfcs?|key fact statement|"
    r"annual percentage rate|consent|outsourcing)\b", re.I)


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 RegulTrace"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def clean(markup):
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", markup, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</tr>|</li>", "\n", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", text)).strip()


def feed_items():
    for source, url in FEEDS.items():
        for item in ET.fromstring(fetch(url)).iter("item"):
            link = (item.findtext("link") or "").strip()
            number = re.search(r"(?:Id|prid)=(\d+)", link)
            prefix = "RBI-N" if "notification" in source else "RBI-PR"
            yield {
                "id": f"{prefix}-{number[1] if number else abs(hash(link))}",
                "source": source,
                "title": " ".join((item.findtext("title") or "").split()),
                "url": link,
                "date": parsedate_to_datetime(item.findtext("pubDate")).date().isoformat(),
                "text": clean(item.findtext("description") or ""),
            }


def keyword_triage(item):
    hits = sorted({m.lower() for m in IN_SCOPE.findall(f'{item["title"]} {item["text"]}')})
    if hits:
        return True, "Mentions " + ", ".join(hits[:4]) + ", which PayNova's policies cover."
    return False, "About an area PayNova does not operate in."


def triage(items):
    if not items:
        return {}, "keywords", None
    if not analyze.has_key():
        return {item["id"]: keyword_triage(item) for item in items}, "keywords", "no AI key is set, so relevance was judged by keywords"
    try:
        verdicts = analyze.triage(items)
        analyze.clear_error()
        return verdicts, "gpt", None
    except (analyze.OpenAIError, ValueError, KeyError) as exc:
        note = f"{analyze.reason(exc)}, so relevance was judged by keywords for now"
        print(f"triage fell back to keywords: {note}")
        return {item["id"]: keyword_triage(item) for item in items}, "keywords", note


def check():
    g = graph.connect()
    items = list(feed_items())
    new = {item["id"] for item in items if graph.add_circular(g, item)}
    stale = {c["id"] for c in graph.circulars(g) if c.get("triaged_by") == "keywords"} if analyze.has_key() else set()
    pending = [item for item in items if item["id"] in new | stale]
    verdicts, by, note = triage(pending)
    for cid, (relevant, reason) in verdicts.items():
        graph.set_triage(g, cid, relevant, reason, by)
    checked_at = datetime.now(IST).strftime("%d %b %Y, %H:%M IST")
    graph.set_meta(g, "last_checked", checked_at)
    if pending:
        graph.set_meta(g, "triage_note", note or "")
    return {"checked": len(items), "new": len(new), "checked_at": checked_at, "note": note if pending else None}


def watch(interval=1800):
    def loop():
        while True:
            try:
                check()
            except Exception as exc:
                print(f"monitor: {exc}")
            time.sleep(interval)
    threading.Thread(target=loop, daemon=True).start()
