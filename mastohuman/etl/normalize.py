import re

from bs4 import BeautifulSoup


def normalize_content(html: str) -> str:
    """
    Convert HTML content to normalized text.
    Preserves links, mentions, hashtags as text.
    Collapses whitespace.
    """
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Handle line breaks: replace <br> and <p> with newlines
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for p in soup.find_all("p"):
        p.replace_with("\n" + p.get_text() + "\n")

    text = soup.get_text()

    # Collapse multiple whitespace/newlines
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = text.strip()

    return text


def create_person_document_text(account_info: dict, statuses: list[dict]) -> str:
    """
    Creates the canonical text representation for LLM ingestion.
    Input: Filtered list of original status dictionaries (db objects or dicts).
    """
    lines = []

    # Header
    display = account_info.get("display_name") or account_info.get("acct")
    acct = account_info.get("acct")
    lines.append(f"Account: {display} ({acct})")
    lines.append("-" * 20)
    lines.append("Recent Original Posts (Newest First):")
    lines.append("")

    for s in statuses:
        # Assume s is a dictionary-like object from our DB model
        ts = s["created_at"].strftime("%Y-%m-%d %H:%M")
        content = s["content_text"]
        # Truncate extremely long posts to save context window (optional, but good practice)
        if len(content) > 1000:
            content = content[:1000] + "[...]"

        lines.append(f"[{ts}] {content}")
        # Attach media description if present (future improvement)
        lines.append("")

    return "\n".join(lines)
