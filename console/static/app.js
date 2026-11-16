// Shadeline page. One question is one agent session; follow-ups reuse it.
const $ = (id) => document.getElementById(id);
let sessionId = null;
let busy = false;

// The agent's markdown, sanitized, then split so each ### section is its own block on the sheet.
function renderBrief(markdown) {
  const src = document.createElement("div");
  src.innerHTML = DOMPurify.sanitize(marked.parse(markdown));
  const sheet = document.createElement("div");
  sheet.className = "sheet";
  let section = null;
  for (const node of [...src.childNodes]) {
    if (node.nodeName === "H2") {
      node.classList.add("sheet-title");
      sheet.appendChild(node);
      section = null;
    } else if (node.nodeName === "H3") {
      section = document.createElement("section");
      section.className = "part";
      const title = node.textContent.trim();
      if (/^\d+\./.test(title)) section.classList.add("part-site");
      if (/^set aside/i.test(title)) section.classList.add("part-aside");
      if (/draft/i.test(title)) section.classList.add("part-draft");
      section.appendChild(node);
      sheet.appendChild(section);
    } else if (section) {
      section.appendChild(node);
    } else if (node.nodeType === Node.ELEMENT_NODE || node.textContent.trim()) {
      sheet.appendChild(node);
    }
  }
  sheet.querySelectorAll("blockquote").forEach((q) => q.classList.add("memo"));
  return sheet;
}

function renderSteps(list, steps) {
  list.replaceChildren();
  steps.forEach((s, i) => {
    const li = document.createElement("li");
    const d = document.createElement("details");
    const sum = document.createElement("summary");
    sum.innerHTML = '<span class="step-n"></span><span class="step-label"></span><code class="step-tool"></code>';
    sum.querySelector(".step-n").textContent = i + 1;
    sum.querySelector(".step-label").textContent = s.label;
    sum.querySelector(".step-tool").textContent = s.tool;
    const pre = document.createElement("pre");
    pre.textContent = s.detail;
    d.append(sum, pre);
    li.appendChild(d);
    list.appendChild(li);
  });
  if (!steps.length) list.innerHTML = '<li class="muted">No tool was called for this answer.</li>';
}

function setBusy(on) {
  busy = on;
  ["ask", "followup-send", "new-question"].forEach((id) => ($(id).disabled = on));
  $("working").hidden = !on;
  if (on) {
    const t0 = Date.now();
    $("elapsed").textContent = "0 s";
    setBusy.timer = setInterval(() => ($("elapsed").textContent = `${Math.round((Date.now() - t0) / 1000)} s`), 1000);
    $("working").scrollIntoView({ behavior: "smooth", block: "nearest" });
  } else {
    clearInterval(setBusy.timer);
  }
}

function showError(msg) {
  $("error").textContent = msg;
  $("error").hidden = !msg;
}

async function send(message) {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  let data;
  try { data = await res.json(); } catch { data = { error: `The server answered ${res.status}.` }; }
  if (!res.ok || data.error) throw new Error(data.error || `The server answered ${res.status}.`);
  return data;
}

function reset() {
  sessionId = null;
  $("brief").replaceChildren();
  $("thread").replaceChildren();
  $("steps").replaceChildren();
  $("steps-box").hidden = true;
  $("followup").hidden = true;
  $("empty").hidden = false;
  showError("");
}

async function ask() {
  const text = $("question-input").value.trim();
  if (!text || busy) return;
  reset();  // every question gets a fresh session
  $("empty").hidden = true;
  setBusy(true);
  try {
    const data = await send(text);
    sessionId = data.session_id;
    $("brief").replaceChildren(renderBrief(data.reply));
    renderSteps($("steps"), data.steps);
    $("steps-time").textContent = `${data.seconds} s`;
    $("steps-box").hidden = false;
    $("followup").hidden = false;
  } catch (e) {
    showError(`The assistant could not answer this question. ${e.message}`);
    $("empty").hidden = false;
  } finally {
    setBusy(false);
  }
}

async function followUp() {
  const text = $("followup-input").value.trim();
  if (!text || busy || !sessionId) return;
  showError("");
  const item = document.createElement("article");
  item.className = "turn";
  const q = document.createElement("p");
  q.className = "turn-question";
  q.textContent = text;
  item.appendChild(q);
  $("thread").appendChild(item);
  $("followup-input").value = "";
  setBusy(true);
  try {
    const data = await send(text);
    item.appendChild(renderBrief(data.reply));
    const box = document.createElement("div");
    box.className = "steps-box";
    box.innerHTML = '<h3 class="label">What the assistant ran <span class="muted"></span></h3><ol class="steps"></ol>';
    box.querySelector(".muted").textContent = `${data.seconds} s`;
    renderSteps(box.querySelector("ol"), data.steps);
    item.appendChild(box);
  } catch (e) {
    item.remove();
    $("followup-input").value = text;
    showError(`The follow-up did not go through. ${e.message}`);
  } finally {
    setBusy(false);
  }
}

// A starter fills the question box; the planner can edit it before sending.
document.querySelectorAll(".starter").forEach((b) =>
  b.addEventListener("click", () => {
    $("question-input").value = b.textContent.trim();
    $("question-input").focus();
  }));

$("ask").addEventListener("click", ask);
$("followup-send").addEventListener("click", followUp);
$("followup-input").addEventListener("keydown", (e) => { if (e.key === "Enter") followUp(); });
$("question-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
});
$("new-question").addEventListener("click", () => {
  reset();
  $("question-input").value = "";
  $("question-input").focus();
});
