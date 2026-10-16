# Sage — desktop and web AI workspace

Sage provides a simple assistant interface with specialist workspace presets and optional advanced controls. The desktop application is implemented first; the web application uses the same Python agent, storage, document retrieval, and validated tools.

## Start the desktop application

Python 3.12 is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r Requirements.txt
Copy-Item .env.example .env
python Main.py
```

Set `SAGE_API_KEY` in `.env` to enable model conversation, synthesis, and multi-step tools. The default provider is Groq; the model ID is configurable in Advanced settings. Existing `GroqAPIKey` and `GROQ_API_KEY` environment names are also accepted. No key is required for local document search.

## Start the web version

```powershell
python -m pip install -r requirements-core.txt
python web_app.py --port 8765
```

Open http://127.0.0.1:8765. The browser application is served by the Python backend; opening `web/index.html` directly will not work. No Node build step is required.

## What you can do

- Choose Everyday, Research, Study, Developer, or Business. These presets specialize the assistant's instructions; they do not grant extra permissions.
- Import PDF, TXT, Markdown, CSV, JSON, and Python text documents. PDFs must contain extractable text; scanned PDFs need OCR first.
- Ask questions with inspectable source passages and stable document/section citations.
- Compare documents through list/read/search tools, calculate arithmetic, and save generated drafts for review and export.
- Inspect tool activity, export conversations and drafts, remove documents, and clear conversation history.
- Adjust model, creativity, response length, model-round limit, source count, conversation memory, draft permission, and custom instructions.

Try uploading `examples/project-brief.md`, then ask: “Calculate the total budget and save a cited project brief.” Without a model key, Sage returns matching source passages and clearly labels local-search mode; it does not simulate AI answers.

## Configuration and storage

`SAGE_BASE_URL` selects a server-admin-configured chat-completions-compatible endpoint. To use a local model server, set its `/v1` URL and `SAGE_LOCAL_MODEL=1`, then select an installed model ID in Advanced settings. Tool support depends on that model/server. Credentials never enter browser JavaScript.

Local data lives in `.sage/sage.db`; `SAGE_DATA_DIR` overrides the location. Desktop uses a persistent local session. Browsers have separate cookie-scoped sessions and do not automatically share desktop documents or history. Disabling memory stops use and storage of subsequent chat turns; use Clear conversation to delete previously saved turns. Documents and drafts remain until separately removed or the local data directory is deleted. Storage is local plaintext; protect the machine and backups accordingly.

Document retrieval uses Unicode lexical scoring with overlapping chunks; it is not embedding-based semantic search. Uploaded document names and relevant passages are sent to the configured model when answering. Tool permissions are enforced in Python. Tools cannot run shell commands, control applications, send messages, or publish drafts. Source panels show retrieved evidence; generated citations still need inspection.

The web server binds only to loopback, checks Host/Origin and CSRF tokens, limits request size, serializes session mutations, and renders user/model text without HTML interpretation. It is a local application, not a public multi-user deployment: authentication, TLS, deployment limits, and tenant administration are future work.

## Original desktop features

The original voice, app-control, web-search, and image-generation assistant remains available separately:

```powershell
python -m pip install -r requirements-legacy.txt
python legacy_main.py
```

It retains its original provider and browser requirements: configure `Username`, `AssistantName`, `CohereAPIKey`, `GroqAPIKey`, `HuggingFaceAPIKey`, `AssistantVoice`, and `InputLanguage` in `.env` for the legacy integrations. Those legacy integrations have not been migrated into the new agent or web shell. The `Backend/` and original `Frontend/GUI.py` modules remain intact.

## Verify

```powershell
python -m unittest discover -s tests -v
python -m compileall -q sage Main.py web_app.py
```

The suite checks multi-step execution with a scripted provider, source retrieval, session isolation, permission enforcement, history preservation, memory opt-out, Qt worker completion, and real local HTTP upload/search/security flows. It does not call a paid model service. Qt tests skip when its dependency is absent. CI runs on Windows with Python 3.12.
