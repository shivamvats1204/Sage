"""One safe Markdown renderer for web, desktop, drafts, and exports."""
import html
import re

import bleach
from markdown_it import MarkdownIt

TAGS = {"p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "strong", "em", "s", "blockquote",
        "ul", "ol", "li", "pre", "code", "table", "thead", "tbody", "tr", "th", "td", "a"}


def render_markdown(text):
    parser = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
    # Markdown image links are not automatically loaded. Generated images use authenticated asset routes.
    parser.renderer.rules["image"] = lambda tokens, idx, options, env: html.escape(tokens[idx].content)
    rendered = parser.render(text)
    clean = bleach.clean(rendered, tags=TAGS, attributes={"a": ["href", "title"], "code": ["class"], "ol": ["start"]},
                         protocols={"http", "https", "mailto"}, strip=True)
    linker = bleach.linkifier.Linker(callbacks=[bleach.callbacks.nofollow, bleach.callbacks.target_blank], skip_tags={"pre", "code"})
    return linker.linkify(clean)


def old_sources(store, session, text):
    """Recover inspectable document references for conversations saved before metadata existed."""
    docs = {d["id"]: d for d in store.documents(session)}
    found = []
    for doc_id, section_text in dict.fromkeys(re.findall(r"\[([a-f0-9]{12}):(\d{1,3})\]", text)):
        section = int(section_text)
        doc = docs.get(doc_id)
        start = (section - 1) * 1000
        if doc and 1 <= section <= 300 and start < len(doc["text"]):
            found.append({"source": f"{doc_id}:{section}", "document_id": doc_id, "name": doc["name"], "text": doc["text"][start:start + 1200]})
    return found
