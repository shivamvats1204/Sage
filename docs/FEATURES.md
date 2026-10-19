# Sage feature migration

The original `Backend/` implementation is the feature reference. The shared `sage/` core extends it for the new desktop and browser interfaces without starting the original modules' import-time browser and image loops.

| Original capability | Shared desktop and web | Details |
|---|---|---|
| Groq conversation | Available | Existing keys and configurable model; bounded tool rounds and history |
| User name from `.env` | Available | `Username` fallback; per-session override; explicit name memory; personalization control |
| Realtime web search | Available | DDGS titles, links, dated snippets; persisted source evidence; search permission |
| Content creation and Notepad output | Available as drafts | Formatted reviewable drafts and Markdown export |
| Image generation | Integrated; requires image token | Modern Hugging Face Inference Providers API, bounded timeout, PNG preview/download, session-scoped storage |
| Google and YouTube actions | Available as links | Explicit clickable actions; no automatic browser/app control |
| Voice output | Browser plus original launcher | Browser speech synthesis; language setting; legacy desktop TTS retained |
| Speech recognition | Browser support varies; original launcher retained | Optional user-triggered dictation; requires microphone permission |
| Open/close local apps and volume | Original desktop launcher | Kept out of the browser server; not migrated to new desktop |

## Response presentation added

- Sanitized Markdown headings, emphasis, lists, blockquotes, fenced code, and comparison tables; user text remains literal.
- Browser table scrolling, copy-code/answer actions, per-answer Markdown export, and read-aloud.
- Bar, line, and pie charts drawn from validated numeric values, with underlying data and source IDs. Browser: SVG/CSV export. Desktop: PNG export and data tables.
- Generated-image previews and downloads. Images and chart definitions persist in local SQLite independently of chat memory.
- Inspectable document/web citations, per-answer source cards, tool summaries, technical details, and unmatched-reference warnings.
- Earlier conversations gain formatted presentation automatically. Document citations can be recovered when the referenced source still exists; historical web/tool evidence that was never stored cannot be reconstructed.

## General and advanced use

Everyday, Research, Study, Developer, and Business presets keep the first-run experience simple. Profile & settings exposes name, personalization, model, creativity, output limit, tool-round budget, document passage count, web/image/draft permissions, image model, voice language, memory, and custom instructions.

Example requests:

- “Compare the options in a table, with one row per option.”
- “Chart these fictional budgets: Research 2500 USD and Design 1500 USD.”
- “Search official Python documentation for beginner tutorials and cite your sources.”
- “Call me Sam and remember that name.”
- “Generate an image of a calm reading room with warm daylight.” (requires image token)
- “Give me a YouTube link for a Python tutorial.”

## Remaining improvements, in priority order

1. Full-page research retrieval and source quality checks. Search snippets alone are insufficient for detailed factual claims; official material and anecdotal reports should stay distinguishable.
2. Streaming responses, cancellation, provider/model discovery, and visible per-turn usage. Current calls are bounded but presented after completion. Basic rate-limit recovery is implemented: one provider-directed retry of at most 45 seconds, at most two web searches, and a final synthesis round.
3. Better document retrieval: semantic/hybrid search, hierarchical document maps and bounded recursive exploration, followed by retrieval/citation evaluations on representative documents. Do not label the existing lexical search as RLM.
4. Formula/math typesetting and reviewed diagram rendering. Current numeric charts are implemented; arbitrary model HTML/JavaScript is not executed.
5. A dedicated permission-based desktop automation layer before moving app-control functions into the new desktop shell.
6. Asset deletion/management and storage quotas by byte size; current asset limit is 100 per session and 10 MB per image. Clearing conversation removes messages, not saved drafts, documents, or assets.
7. Authentication, tenant administration, TLS, deployment limits, and encrypted secret storage before any public deployment.

## Verification limits

Automated tests use isolated temporary databases and mocked search/image adapters. Live checks should use public search topics and clearly marked fictional chart data. A missing image token is a setup requirement, not a successful generation. Never commit `.env`, local databases, uploaded documents, or generated user images.
