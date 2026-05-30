import html
import os
import re
import time
from pathlib import Path

import requests


HTML_FILE = Path("index.html")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")


def normalize(text: str) -> str:
    """Normalize paper titles for fuzzy matching."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def overlap_score(query_title: str, result_title: str) -> int:
    """Simple token-overlap score for choosing the best Scholar result."""
    q = set(normalize(query_title).split())
    r = set(normalize(result_title).split())
    return len(q & r)


def get_citation_count(title: str) -> int | None:
    """
    Query Google Scholar via SerpApi and return the citation count
    from the best matching result.
    """
    if not SERPAPI_KEY:
        raise RuntimeError("Missing SERPAPI_KEY. Add it as a GitHub Actions secret.")

    params = {
        "engine": "google_scholar",
        "q": title,
        "api_key": SERPAPI_KEY,
        "hl": "en",
        "num": 5,
    }

    response = requests.get(
        "https://serpapi.com/search",
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    results = data.get("organic_results", [])
    if not results:
        print(f"[WARN] No Google Scholar results found for: {title}")
        return None

    best = max(
        results,
        key=lambda item: overlap_score(title, item.get("title", "")),
    )

    best_title = best.get("title", "")
    score = overlap_score(title, best_title)

    if score < 4:
        print(f"[WARN] Weak match for: {title}")
        print(f"       Best match: {best_title}")

    cited_by = best.get("inline_links", {}).get("cited_by", {})
    total = cited_by.get("total")

    if total is None:
        return 0

    return int(total)


def update_badge_count(html_text: str, title: str, count: int) -> str:
    """
    Find a scholar badge by data-title and update:
    <span class="scholar-count">NUMBER</span>
    """
    title_escaped = re.escape(html.escape(title, quote=True))

    pattern = (
        r'(<a\s+class="scholar-badge"[^>]*'
        r'data-title="' + title_escaped + r'"[^>]*>.*?'
        r'<span\s+class="scholar-count">)'
        r'(\d+)'
        r'(</span>.*?</a>)'
    )

    updated, n = re.subn(
        pattern,
        lambda m: f"{m.group(1)}{count}{m.group(3)}",
        html_text,
        flags=re.DOTALL,
    )

    if n == 0:
        print(f"[WARN] Could not update badge for: {title}")

    return updated


def main() -> None:
    if not HTML_FILE.exists():
        raise FileNotFoundError(f"Cannot find {HTML_FILE}")

    html_text = HTML_FILE.read_text(encoding="utf-8")

    titles = re.findall(
        r'<a\s+class="scholar-badge"[^>]*data-title="([^"]+)"',
        html_text,
        flags=re.DOTALL,
    )

    if not titles:
        raise RuntimeError(
            "No scholar badges found. Make sure each badge has class='scholar-badge' and data-title='...'."
        )

    print(f"Found {len(titles)} scholar badges.")

    updated_html = html_text

    for raw_title in titles:
        title = html.unescape(raw_title)
        print(f"Querying: {title}")

        count = get_citation_count(title)

        if count is None:
            print(f"[WARN] Skipping: {title}")
            continue

        print(f"  citations: {count}")
        updated_html = update_badge_count(updated_html, title, count)

        # Be gentle with the API.
        time.sleep(2)

    HTML_FILE.write_text(updated_html, encoding="utf-8")


if __name__ == "__main__":
    main()