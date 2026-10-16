"use strict";
const $ = id => document.getElementById(id);
let state = null;
let busy = false;
const defaults = {workspace:"everyday",model:"llama-3.3-70b-versatile",temperature:0.3,max_tokens:1800,max_steps:4,retrieval_k:4,remember:true,allow_drafts:true,instructions:""};
function error(message){ $("error").textContent=message; $("error").hidden=!message; }
async function api(path, body){
  const options = body === undefined ? {} : {method:"POST",headers:{"Content-Type":"application/json","X-Sage-CSRF":state.csrf},body:JSON.stringify(body)};
  const response=await fetch(path,options);const data=await response.json();
  if(!response.ok)throw new Error(data.error||"Request failed");return data;
}
function populate(settings){for(const [key,value] of Object.entries(settings)){const el=$(key);if(el.type==="checkbox")el.checked=value;else el.value=value;}}
function settings(){const value={};for(const [key,fallback] of Object.entries(defaults)){const el=$(key);value[key]=typeof fallback==="boolean"?el.checked:typeof fallback==="number"?Number(el.value):el.value;}return value;}
function message(role,text){const el=document.createElement("article");el.className="message "+role;const name=document.createElement("strong");name.textContent=role==="user"?"YOU":"SAGE";el.append(name,document.createTextNode(text));$("messages").append(el);$("welcome").hidden=true;}
function download(name,text){const url=URL.createObjectURL(new Blob([text],{type:"text/plain;charset=utf-8"}));const a=document.createElement("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function renderDocuments(){
  $("documents").replaceChildren();$("doc-count").textContent=state.documents.length;
  for(const doc of state.documents){const row=document.createElement("div");row.className="document";const name=document.createElement("span");name.textContent=doc.name;const remove=document.createElement("button");remove.textContent="×";remove.setAttribute("aria-label","Remove "+doc.name);remove.onclick=()=>guard(async()=>{await api("/api/documents/remove",{id:doc.id});await refresh(false);});row.append(name,remove);$("documents").append(row);}
}
function renderDrafts(){
  $("draft-content").replaceChildren();$("drafts").hidden=!state.drafts.length;
  for(const draft of state.drafts){const detail=document.createElement("details");const summary=document.createElement("summary");summary.textContent=draft.title;const text=document.createElement("pre");text.textContent=draft.content;const button=document.createElement("button");button.textContent="Export draft ↗";button.onclick=()=>download("sage-draft.md",draft.content);detail.append(summary,text,button);$("draft-content").append(detail);}
}
function renderEvidence(response){
  $("sources").hidden=!response.sources.length&&!response.steps.length;$("source-content").replaceChildren();
  for(const source of response.sources){const p=document.createElement("p");const heading=document.createElement("strong");heading.textContent=`[${source.source}] ${source.name}`;p.append(heading,document.createTextNode("\n"+source.text));$("source-content").append(p);}
  $("steps").textContent=response.steps.length?JSON.stringify(response.steps,null,2):"";
}
async function refresh(full=true){state=await api("/api/state");$("status").textContent=state.model_available?"Connected model · ready":"Local search · add an API key for AI";if(full){$("workspace").replaceChildren();for(const w of state.workspaces){const option=document.createElement("option");option.value=w;option.textContent=w;$("workspace").append(option);}populate(state.settings);$("messages").replaceChildren();$("welcome").hidden=!!state.history.length;for(const m of state.history)message(m.role,m.content);}renderDocuments();renderDrafts();}
async function guard(action){if(busy)return;busy=true;error("");$("send").disabled=true;try{await action();}catch(e){error(e.message);}finally{busy=false;$("send").disabled=false;}}
$("settings-toggle").onclick=()=>{const open=$("settings").hidden;$("settings").hidden=!open;$("settings-toggle").setAttribute("aria-expanded",String(open));};
$("reset-settings").onclick=()=>populate(defaults);
$("save-settings").onclick=()=>guard(async()=>{const result=await api("/api/settings",settings());populate(result.settings);$("status").textContent="Settings saved";});
$("clear").onclick=()=>guard(async()=>{await api("/api/history/clear",{});$("messages").replaceChildren();$("welcome").hidden=false;$("sources").hidden=true;await refresh(false);});
$("export").onclick=()=>download("sage-conversation.md",Array.from($("messages").children).map(el=>el.textContent).join("\n\n"));
document.querySelectorAll("[data-prompt]").forEach(button=>button.onclick=()=>{$("message").value=button.dataset.prompt;$("message").focus();});
$("upload").onchange=()=>guard(async()=>{const file=$("upload").files[0];if(!file)return;if(file.size>5000000)throw new Error("Files must be smaller than 5 MB");const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(",")[1]);reader.onerror=()=>reject(new Error("Could not read file"));reader.readAsDataURL(file);});await api("/api/documents",{name:file.name,content});$("upload").value="";await refresh(false);});
$("chat-form").onsubmit=event=>{event.preventDefault();guard(async()=>{const text=$("message").value.trim();if(!text)return;const options=settings();message("user",text);$("message").value="";$("status").textContent="Working through your request…";const response=await api("/api/chat",{message:text,settings:options});message("assistant",response.answer);renderEvidence(response);await refresh(false);$("status").textContent=response.mode==="error"?"Model request failed · see response":response.mode==="local-search"?"Local search · no model configured":"Ready";$("message").focus();});};
$("message").addEventListener("keydown",event=>{if(event.key==="Enter"&&!event.shiftKey){event.preventDefault();if(!busy)$("chat-form").requestSubmit();}});
refresh().catch(e=>error(e.message));
