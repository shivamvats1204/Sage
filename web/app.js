"use strict";
const $ = id => document.getElementById(id);
const defaults = {
  workspace: "everyday", model: "qwen/qwen3.8-27b", temperature: 0.3,
  max_tokens: 1800, max_steps: 4, retrieval_k: 4, remember: true,
  allow_drafts: true, instructions: "", display_name: "", personalize: true,
  allow_web: true, allow_images: true, image_model: "black-forest-labs/FLUX.1-schnell",
  voice_language: "en-IN"
};
let state = null, busy = false, turns = [], activeSpeech = null;

function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
function error(message) {
  $("error").textContent = message;
  $("error").hidden = !message;
}
function safeURL(value) {
  try { const url = new URL(value); return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password; }
  catch { return false; }
}
async function api(path, body) {
  const options = body === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json", "X-Sage-CSRF": state.csrf},
    body: JSON.stringify(body)
  };
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}
function populate(settings) {
  for (const [key, value] of Object.entries({...defaults, ...settings})) {
    const el = $(key);
    if (!el) continue;
    if (el.type === "checkbox") el.checked = value;
    else el.value = value;
  }
}
function settings() {
  const result = {};
  for (const [key, fallback] of Object.entries(defaults)) {
    const el = $(key);
    result[key] = typeof fallback === "boolean" ? el.checked : typeof fallback === "number" ? Number(el.value) : el.value;
  }
  return result;
}
function download(name, text, type = "text/plain;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([text], {type}));
  const a = element("a"); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function button(text, callback, className = "quiet") {
  const result = element("button", className, text);
  result.type = "button"; result.onclick = callback; return result;
}
function renderBody(html, plainText) {
  const body = element("div", "markdown-body");
  // This HTML is generated and allow-list sanitized by sage/presentation.py on our own server.
  if (typeof html === "string" && html) body.innerHTML = html;
  else body.textContent = plainText;
  for (const pre of body.querySelectorAll("pre")) {
    const wrapper = element("div", "code-block");
    pre.replaceWith(wrapper); wrapper.append(pre);
    wrapper.append(button("Copy code", async () => {
      try { await navigator.clipboard.writeText(pre.innerText); } catch { error("Could not access the clipboard."); }
    }));
  }
  for (const table of body.querySelectorAll("table")) {
    const wrapper = element("div", "table-scroll");
    wrapper.tabIndex = 0; wrapper.setAttribute("aria-label", "Scrollable response table");
    table.replaceWith(wrapper); wrapper.append(table);
  }
  return body;
}
function sourceDetails(meta) {
  const details = element("details", "message-evidence");
  const sources = meta.sources || [], steps = meta.steps || [];
  details.append(element("summary", "", `${sources.length} source${sources.length === 1 ? "" : "s"}${steps.length ? ` · ${steps.length} tool actions` : ""}`));
  const cards = new Map();
  for (const [index, source] of sources.entries()) {
    const card = element("div", "source-card");
    card.append(element("strong", "", `${index + 1}. ${source.name || source.title || source.source}`));
    if (safeURL(source.url)) {
      const link = element("a", "source-link", new URL(source.url).hostname);
      link.href = source.url; link.target = "_blank"; link.rel = "noopener noreferrer";
      card.append(link);
    }
    card.append(element("p", "", source.text || ""));
    card.append(element("small", "muted", source.kind === "web" ? `Search snippet · retrieved ${source.retrieved_at || "this session"}` : `Document passage · ${source.source}`));
    details.append(card); cards.set(source.source, {card, index});
  }
  if (steps.length) {
    const labels = {search_documents: "Searched your documents", read_document: "Read a document section", list_documents: "Listed available documents", calculate: "Calculated a value", save_draft: "Saved a draft", search_web: "Searched the web", create_chart: "Created a chart", generate_image: "Requested an image", remember_name: "Updated your name", create_link: "Prepared a link"};
    const list = element("ul", "tool-list");
    for (const step of steps) {
      const failure = step.result && step.result.error;
      list.append(element("li", failure ? "tool-failed" : "", `${labels[step.tool] || step.tool}${failure ? `: ${failure}` : ""}`));
    }
    details.append(list);
    const technical = element("details", "technical-details");
    technical.append(element("summary", "", "Technical details"), element("pre", "", JSON.stringify(steps, null, 2)));
    details.append(technical);
  }
  for (const warning of meta.warnings || []) details.append(element("p", "warning-note", warning));
  return {details, cards};
}
function decorateReferences(body, evidence) {
  const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) {
    if (!walker.currentNode.parentElement.closest("a,code,pre,button")) nodes.push(walker.currentNode);
  }
  for (const node of nodes) {
    const regex = /\[((?:web:)[a-f0-9]{12}|[a-f0-9]{10,24}:\d{1,3})\]/g;
    const matches = [...node.textContent.matchAll(regex)];
    if (!matches.length) continue;
    const fragment = document.createDocumentFragment(); let offset = 0;
    for (const match of matches) {
      fragment.append(document.createTextNode(node.textContent.slice(offset, match.index)));
      const source = evidence.cards.get(match[1]);
      if (source) {
        const cite = button(`[${source.index + 1}]`, () => {
          evidence.details.open = true;
          source.card.scrollIntoView({block: "nearest", behavior: "smooth"});
        }, "citation");
        cite.title = `Inspect source ${match[1]}`;
        cite.setAttribute("aria-label", `Inspect source ${source.index + 1}`);
        fragment.append(cite);
      } else {
        const cite = element("span", "citation unverified", match[0]);
        cite.title = "This reference could not be matched to an available source.";
        fragment.append(cite);
      }
      offset = match.index + match[0].length;
    }
    fragment.append(document.createTextNode(node.textContent.slice(offset)));
    node.replaceWith(fragment);
  }
}
const SVG = "http://www.w3.org/2000/svg";
function svgElement(name, attributes = {}, text) {
  const el = document.createElementNS(SVG, name);
  for (const [key, value] of Object.entries(attributes)) el.setAttribute(key, String(value));
  if (text !== undefined) el.textContent = text;
  return el;
}
function chartCard(asset) {
  const spec = asset.spec;
  const card = element("section", "asset-card chart-card");
  if (!spec || !Array.isArray(spec.values) || !Array.isArray(spec.labels) || !spec.values.length || spec.values.length !== spec.labels.length || spec.values.length > 24 || spec.values.some(v => typeof v !== "number" || !Number.isFinite(v))) return card;
  card.append(element("h3", "", asset.title));
  const colors = ["#416f55", "#9eaa50", "#5f8f99", "#be8351", "#8c6c9d", "#d4b45b"];
  const height = spec.type === "bar" ? Math.max(180, spec.values.length * 34 + 40) : Math.max(320, spec.labels.length * 23 + 40);
  const svg = svgElement("svg", {viewBox: `0 0 720 ${height}`, role: "img", "aria-label": asset.title, xmlns: SVG});
  svg.append(svgElement("title", {}, asset.title));
  const number = v => v.toLocaleString(undefined, {maximumFractionDigits: 3});
  if (spec.type === "pie") {
    const total = spec.values.reduce((a, b) => a + b, 0); let offset = 0;
    if (total > 0 && spec.values.every(v => v >= 0)) {
      const circumference = 2 * Math.PI * 85;
      spec.values.forEach((value, i) => {
        const length = value / total * circumference;
        svg.append(svgElement("circle", {cx: 175, cy: 155, r: 85, fill: "none", stroke: colors[i % colors.length], "stroke-width": 58, "stroke-dasharray": `${length} ${circumference}`, "stroke-dashoffset": -offset, transform: "rotate(-90 175 155)"}));
        offset += length;
        svg.append(svgElement("rect", {x: 340, y: 38 + i * 23, width: 12, height: 12, fill: colors[i % colors.length]}));
        svg.append(svgElement("text", {x: 363, y: 49 + i * 23, fill: "#193b32", "font-size": 12}, `${spec.labels[i]}: ${number(value)} (${(value / total * 100).toFixed(1)}%)`));
      });
      svg.append(svgElement("text", {x: 175, y: 160, "text-anchor": "middle", fill: "#193b32", "font-size": 20}, number(total)));
    }
  } else {
    const low = Math.min(0, ...spec.values), high = Math.max(0, ...spec.values), range = high - low || 1;
    if (spec.type === "bar") {
      const x = v => 180 + (v - low) / range * 430;
      svg.append(svgElement("line", {x1: x(0), y1: 12, x2: x(0), y2: height - 15, stroke: "#b7c6af"}));
      spec.values.forEach((value, i) => {
        const y = 24 + i * 34;
        svg.append(svgElement("text", {x: 165, y: y + 15, "text-anchor": "end", fill: "#193b32", "font-size": 12}, String(spec.labels[i]).slice(0, 26)));
        const bar = svgElement("rect", {x: Math.min(x(0), x(value)), y, width: Math.max(1, Math.abs(x(value) - x(0))), height: 23, rx: 3, fill: colors[i % colors.length]});
        bar.append(svgElement("title", {}, `${spec.labels[i]}: ${number(value)} ${spec.unit || ""}`));
        svg.append(bar, svgElement("text", {x: 630, y: y + 15, fill: "#193b32", "font-size": 12}, number(value)));
      });
    } else {
      const x = i => 65 + i / Math.max(1, spec.values.length - 1) * 600;
      const y = v => 255 - (v - low) / range * 210;
      for (let i = 0; i <= 4; i++) {
        const value = low + range * i / 4;
        svg.append(svgElement("line", {x1: 65, y1: y(value), x2: 665, y2: y(value), stroke: "#d9ded3"}), svgElement("text", {x: 58, y: y(value) + 4, "text-anchor": "end", fill: "#6a756d", "font-size": 10}, number(value)));
      }
      svg.append(svgElement("polyline", {points: spec.values.map((v, i) => `${x(i)},${y(v)}`).join(" "), fill: "none", stroke: colors[0], "stroke-width": 3}));
      spec.values.forEach((v, i) => {
        const dot = svgElement("circle", {cx: x(i), cy: y(v), r: 5, fill: colors[0]});
        dot.append(svgElement("title", {}, `${spec.labels[i]}: ${number(v)}`)); svg.append(dot);
        if (spec.labels.length <= 12 || i % Math.ceil(spec.labels.length / 8) === 0) svg.append(svgElement("text", {x: x(i), y: 279, "text-anchor": "middle", fill: "#6a756d", "font-size": 10}, String(spec.labels[i]).slice(0, 12)));
      });
    }
  }
  card.append(svg);
  card.append(element("p", "muted small", `Unit: ${spec.unit || "not specified"}. ${spec.source_ids?.length ? "Sources: " + spec.source_ids.join(", ") : "Values supplied in this conversation; inspect the data below."}`));
  const table = element("table"), tableHead = element("tr");
  tableHead.append(element("th", "", "Label"), element("th", "", spec.unit || "Value")); table.append(tableHead);
  spec.values.forEach((value, i) => {const row = element("tr"); row.append(element("td", "", spec.labels[i]), element("td", "", number(value))); table.append(row);});
  const data = element("details", "chart-data"); data.append(element("summary", "", "View chart data"), table); card.append(data);
  const controls = element("div", "asset-controls");
  controls.append(button("Download SVG", () => download("sage-chart.svg", new XMLSerializer().serializeToString(svg), "image/svg+xml")));
  controls.append(button("Download CSV", () => {
    const quote = value => '"' + String(value).replace(/^[=+@\-\t\r]/, "'$&").replaceAll('"', '""') + '"';
    download("sage-chart.csv", "Label,Value\n" + spec.labels.map((label, i) => `${quote(label)},${spec.values[i]}`).join("\n"), "text/csv;charset=utf-8");
  }));
  card.append(controls); return card;
}
function assetCard(asset) {
  if (asset.kind === "chart") return chartCard(asset);
  const card = element("section", "asset-card");
  if (asset.kind !== "image" || !/^[a-f0-9]{32}$/.test(asset.id)) return card;
  card.append(element("h3", "", asset.title));
  const img = element("img", "generated-image"); img.src = "/api/assets/" + asset.id; img.alt = asset.prompt || asset.title; img.loading = "lazy";
  const link = element("a", "asset-download", "Download image ↗"); link.href = img.src; link.download = "sage-image.png";
  card.append(img, element("p", "muted small", `AI-generated · ${asset.model || "configured image provider"}`), link); return card;
}
function speak(text, control) {
  if (!("speechSynthesis" in window)) return;
  if (activeSpeech) { speechSynthesis.cancel(); activeSpeech.textContent = "Read aloud"; }
  if (activeSpeech === control) { activeSpeech = null; return; }
  activeSpeech = control; control.textContent = "Stop reading";
  const utterance = new SpeechSynthesisUtterance(text.slice(0, 8000));
  utterance.lang = $("voice_language").value;
  utterance.onend = utterance.onerror = () => {control.textContent = "Read aloud"; if (activeSpeech === control) activeSpeech = null;};
  speechSynthesis.speak(utterance);
}
function message(role, text, html = "", metadata = {}) {
  const turn = {role, content: text, html, metadata}; turns.push(turn);
  const article = element("article", "message " + role);
  const heading = element("div", "message-heading");
  heading.append(element("strong", "", role === "user" ? "YOU" : "SAGE")); article.append(heading);
  const body = role === "assistant" ? renderBody(html, text) : element("div", "user-text", text);
  article.append(body);
  if (role === "assistant") {
    const controls = element("div", "message-controls");
    controls.append(button("Copy", async () => {try {await navigator.clipboard.writeText(text);} catch {error("Clipboard access is unavailable.");}}));
    controls.append(button("Export Markdown", () => download("sage-response.md", text)));
    if ("speechSynthesis" in window) {const read = button("Read aloud", () => speak(body.innerText, read)); controls.append(read);}
    article.append(controls);
    for (const asset of metadata.assets || []) article.append(assetCard(asset));
    for (const action of metadata.actions || []) if (safeURL(action.url)) {
      const link = element("a", "action-link", action.title + " ↗"); link.href = action.url; link.target = "_blank"; link.rel = "noopener noreferrer"; article.append(link);
    }
    const evidence = sourceDetails(metadata);
    if ((metadata.sources || []).length || (metadata.steps || []).length || (metadata.warnings || []).length) article.append(evidence.details);
    decorateReferences(body, evidence);
  }
  $("messages").append(article); $("welcome").hidden = true; return article;
}
function renderDocuments() {
  $("documents").replaceChildren(); $("doc-count").textContent = state.documents.length;
  for (const doc of state.documents) {
    const row = element("div", "document"), name = element("span", "", doc.name);
    const remove = button("×", () => guard(async () => {await api("/api/documents/remove", {id: doc.id}); await refresh(false);}));
    remove.setAttribute("aria-label", "Remove " + doc.name); row.append(name, remove); $("documents").append(row);
  }
}
function renderDrafts() {
  $("draft-content").replaceChildren(); $("drafts").hidden = !state.drafts.length;
  for (const draft of state.drafts) {
    const details = element("details"), summary = element("summary", "", draft.title);
    details.append(summary, renderBody(draft.html, draft.content), button("Export draft ↗", () => download("sage-draft.md", draft.content)));
    $("draft-content").append(details);
  }
}
function renderProfile() {
  const name = state.profile?.display_name || "";
  $("profile-label").textContent = name ? ` / ${name}` : "";
  $("greeting").textContent = name ? `A LITTLE CONTEXT. A NEW POSSIBILITY, ${name.toUpperCase()}.` : "A LITTLE CONTEXT. A NEW POSSIBILITY.";
  $("capability-strip").replaceChildren();
  for (const label of ["Documents + citations", "Tables + charts", state.capabilities.web_search && $("allow_web").checked ? "Web search ready" : "Web search off", state.capabilities.image_generation && $("allow_images").checked ? "Images ready" : "Images · setup needed"]) $("capability-strip").append(element("span", "capability-chip", label));
  $("image-setup").textContent = state.capabilities.image_generation ? "Image provider configured. Generated images remain in this local workspace." : state.capabilities.image_setup;
}
function renderSavedAssets() {
  const visible = new Set(turns.flatMap(turn => (turn.metadata?.assets || []).map(asset => asset.id)));
  const saved = (state.assets || []).filter(asset => !visible.has(asset.id));
  $("saved-assets").hidden = !saved.length;
  $("saved-assets-label").textContent = `Saved visuals (${saved.length})`;
  $("saved-assets-content").replaceChildren(...saved.map(assetCard));
}
async function refresh(full = true) {
  state = await api("/api/state");
  $("status").textContent = state.model_available ? "Connected model · ready" : "Local search · add an API key for AI";
  if (full) {
    $("workspace").replaceChildren();
    for (const w of state.workspaces) {const option = element("option", "", w); option.value = w; $("workspace").append(option);}
    populate(state.settings); turns = []; $("messages").replaceChildren();
    $("welcome").hidden = !!state.history.length;
    for (const item of state.history) message(item.role, item.content, item.html, item.metadata || {});
  } else {
    // A remember_name tool may have changed the profile while the model was working.
    $("display_name").value = state.settings.display_name;
  }
  renderDocuments(); renderDrafts(); renderProfile(); renderSavedAssets();
}
async function guard(action) {
  if (busy) return;
  busy = true; error(""); $("send").disabled = true;
  try {await action();} catch (e) {error(e.message);} finally {busy = false; $("send").disabled = false;}
}
$("settings-toggle").onclick = () => {
  const open = $("settings").hidden; $("settings").hidden = !open;
  $("settings-toggle").setAttribute("aria-expanded", String(open));
};
$("reset-settings").onclick = () => populate(defaults);
$("save-settings").onclick = () => guard(async () => {const result = await api("/api/settings", settings()); populate(result.settings); await refresh(false); $("status").textContent = "Settings saved";});
$("clear").onclick = () => guard(async () => {await api("/api/history/clear", {}); turns = []; $("messages").replaceChildren(); $("welcome").hidden = false; $("sources").hidden = true; await refresh(false);});
$("export").onclick = () => download("sage-conversation.md", turns.map(item => `## ${item.role === "user" ? "You" : "Sage"}\n\n${item.content}`).join("\n\n"));
document.querySelectorAll("[data-prompt]").forEach(control => control.onclick = () => {$("message").value = control.dataset.prompt; $("message").focus();});
for (const [id, text] of [["web-prompt", "Search the web for "], ["image-prompt", "Generate an image of "], ["chart-prompt", "Create a chart comparing "]]) $(id).onclick = () => {$("message").value = text; $("message").focus();};
$("upload").onchange = () => guard(async () => {
  try {
    const file = $("upload").files[0]; if (!file) return;
    if (file.size > 5000000) throw new Error("Files must be smaller than 5 MB");
    const content = await new Promise((resolve, reject) => {const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(",")[1]); reader.onerror = () => reject(new Error("Could not read file")); reader.readAsDataURL(file);});
    await api("/api/documents", {name: file.name, content}); await refresh(false);
  } finally {$("upload").value = "";}
});
$("chat-form").onsubmit = event => {
  event.preventDefault(); guard(async () => {
    const text = $("message").value.trim(); if (!text) return;
    const options = settings(); message("user", text); $("message").value = "";
    $("status").textContent = "Working through your request…";
    const pending = element("div", "pending-message", "Sage is working…"); pending.setAttribute("role", "status"); $("messages").append(pending);
    try {
      const response = await api("/api/chat", {message: text, settings: options});
      const article = message("assistant", response.answer, response.html, response);
      await refresh(false);
      $("status").textContent = response.mode === "error" ? "Model request failed · see response" : response.mode === "local-search" ? "Local search · no model configured" : "Ready";
      article.scrollIntoView({block: "start", behavior: "smooth"});
    } catch (e) {$("message").value = text; $("status").textContent = "Request failed · retry when ready"; throw e;}
    finally {pending.remove();}
  });
};
$("message").addEventListener("keydown", event => {if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {event.preventDefault(); if (!busy) $("chat-form").requestSubmit();}});
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
if (Recognition) {
  $("microphone").onclick = () => {
    if (recognition) {recognition.stop(); return;}
    recognition = new Recognition(); recognition.lang = $("voice_language").value; recognition.interimResults = false;
    recognition.onresult = event => {$("message").value += ($("message").value ? " " : "") + event.results[0][0].transcript;};
    recognition.onerror = event => error(event.error === "not-allowed" ? "Microphone access was not granted. You can continue typing." : "Dictation could not complete. Try again or type your message.");
    recognition.onend = () => {recognition = null; $("microphone").textContent = "♩ Dictate";};
    try {recognition.start(); $("microphone").textContent = "Stop dictation";} catch {recognition = null; error("Dictation is unavailable in this browser.");}
  };
} else {$("microphone").disabled = true; $("microphone").title = "Dictation requires a browser with speech recognition support.";}
$("send").disabled = true;
refresh().then(() => {$("send").disabled = false;}).catch(e => error(e.message));
