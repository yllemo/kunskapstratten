(function () {
  const dataEl = document.getElementById("chat-data");
  if (!dataEl) return;

  const CHAT_DATA = JSON.parse(dataEl.textContent);
  const docsByPath = {};
  CHAT_DATA.docs.forEach((d) => { docsByPath[d.rel_path] = d; });
  const skillsBySlug = {};
  CHAT_DATA.skills.forEach((s) => { skillsBySlug[s.slug] = s; });

  const selected = new Set(window.INITIAL_SELECTION || []);
  const temporaryDocuments = [];
  const history = [];
  let streaming = false;
  let abortCtrl = null;

  const chatScroll = document.getElementById("chatScroll");
  const chatEmpty = document.getElementById("chatEmpty");
  const ctxList = document.getElementById("ctxList");
  const ctxCount = document.getElementById("ctxCount");
  const ctxTokens = document.getElementById("ctxTokens");
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const chatSendBtn = document.getElementById("chatSendBtn");
  const skillSelect = document.getElementById("chatSkillSelect");
  const skillDescription = document.getElementById("chatSkillDescription");
  const contextWindow = Number(CHAT_DATA.context_window) || 32768;

  function tokenEstimate(text) {
    return Math.ceil((text || "").length / 4);
  }

  function renderContextMeter() {
    const documentTokens = Array.from(selected).reduce((sum, path) => sum + tokenEstimate(docsByPath[path]?.body), 0)
      + temporaryDocuments.reduce((sum, doc) => sum + tokenEstimate(doc.body), 0);
    const historyTokens = history.reduce((sum, message) => sum + tokenEstimate(message.content) + 4, 0);
    const skill = skillsBySlug[skillSelect?.value];
    const skillTokens = skill ? tokenEstimate(skill.description + "\n" + skill.instructions) : 0;
    const used = documentTokens + historyTokens + skillTokens + 200;
    const percent = Math.min(100, Math.round((used / contextWindow) * 100));
    const progress = document.getElementById("contextProgress");
    const fill = document.getElementById("contextMeterFill");
    document.getElementById("contextPercent").textContent = `${percent} %`;
    document.getElementById("contextUsed").textContent = used.toLocaleString("sv-SE");
    document.getElementById("contextLimit").textContent = contextWindow.toLocaleString("sv-SE");
    document.getElementById("contextDocs").textContent = documentTokens.toLocaleString("sv-SE");
    document.getElementById("contextHistory").textContent = historyTokens.toLocaleString("sv-SE");
    document.getElementById("contextSkill").textContent = skillTokens.toLocaleString("sv-SE");
    progress.setAttribute("aria-valuenow", String(percent));
    fill.style.width = `${percent}%`;
    progress.classList.toggle("is-warning", percent >= 75 && percent < 90);
    progress.classList.toggle("is-danger", percent >= 90);
  }

  function checkboxFor(path) {
    return document.querySelector('.doc-checkbox[value="' + CSS.escape(path) + '"]');
  }

  function renderCtx() {
    ctxList.innerHTML = "";
    let chars = 0;
    selected.forEach((path) => {
      const doc = docsByPath[path];
      chars += doc ? doc.body.length : 0;
      const li = document.createElement("li");
      const nameSpan = document.createElement("span");
      nameSpan.className = "ctx-name";
      nameSpan.textContent = doc ? doc.title : path;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ctx-remove";
      btn.textContent = "\u00d7";
      btn.setAttribute("aria-label", "Ta bort " + (doc ? doc.title : path));
      btn.addEventListener("click", () => {
        selected.delete(path);
        const cb = checkboxFor(path);
        if (cb) cb.checked = false;
        renderCtx();
      });
      li.appendChild(nameSpan);
      li.appendChild(btn);
      ctxList.appendChild(li);
    });
    ctxCount.textContent = selected.size;
    ctxTokens.textContent = Math.ceil(chars / 4).toLocaleString("sv-SE");
    renderContextMeter();
  }

  function renderTemporaryDocuments() {
    const list = document.getElementById("tempCtxList");
    list.innerHTML = "";
    temporaryDocuments.forEach((doc, index) => {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.className = "ctx-name";
      name.textContent = doc.name;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "ctx-remove";
      remove.textContent = "×";
      remove.setAttribute("aria-label", `Ta bort ${doc.name}`);
      remove.addEventListener("click", () => { temporaryDocuments.splice(index, 1); renderTemporaryDocuments(); });
      li.append(name, remove);
      list.appendChild(li);
    });
    renderContextMeter();
  }

  document.querySelectorAll(".doc-checkbox").forEach((cb) => {
    if (selected.has(cb.value)) cb.checked = true;
    cb.addEventListener("change", () => {
      if (cb.checked) selected.add(cb.value);
      else selected.delete(cb.value);
      renderCtx();
    });
  });

  if (skillSelect) skillSelect.addEventListener("change", () => {
    const skill = skillsBySlug[skillSelect.value];
    skillDescription.textContent = skill ? skill.description : "Välj en skill för att använda dess instruktioner i chatten.";
    renderContextMeter();
  });

  const tempFileInput = document.getElementById("tempFileInput");
  if (tempFileInput) tempFileInput.addEventListener("change", async () => {
    const file = tempFileInput.files[0];
    if (!file) return;
    const status = document.getElementById("tempFileStatus");
    status.textContent = `Läser ${file.name}…`;
    const form = new FormData();
    form.append("file", file);
    try {
      const response = await fetch("/api/chat/temp-file", { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Filen kunde inte läsas");
      temporaryDocuments.push(data);
      status.textContent = `${file.name} tillagd enbart i denna chatt.`;
      renderTemporaryDocuments();
    } catch (error) {
      status.textContent = `Fel: ${error.message}`;
    } finally {
      tempFileInput.value = "";
    }
  });

  const clearBtn = document.getElementById("clearCtxBtn");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      selected.clear();
      temporaryDocuments.splice(0);
      document.querySelectorAll(".doc-checkbox").forEach((cb) => { cb.checked = false; });
      renderCtx();
      renderTemporaryDocuments();
    });
  }

  const filterInput = document.getElementById("docFilter");
  if (filterInput) {
    filterInput.addEventListener("input", () => {
      const q = filterInput.value.trim().toLowerCase();
      document.querySelectorAll("#docAddList li").forEach((li) => {
        const label = li.textContent.toLowerCase();
        li.style.display = !q || label.includes(q) ? "" : "none";
      });
    });
  }

  function addBubble(role, text) {
    chatEmpty.style.display = "none";
    const wrap = document.createElement("div");
    wrap.className = "chat-msg " + role;
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    bubble.textContent = text;
    wrap.appendChild(bubble);
    chatScroll.appendChild(wrap);
    chatScroll.scrollTop = chatScroll.scrollHeight;
    return bubble;
  }

  function setSending(on) {
    chatSendBtn.textContent = on ? "\u25a0" : "\u27a4";
    chatSendBtn.classList.toggle("stop", on);
  }

  async function send(question) {
    addBubble("user", question);
    history.push({ role: "user", content: question });
    renderContextMeter();

    const bubble = addBubble("assistant", "");
    let acc = "";
    streaming = true;
    setSending(true);
    abortCtrl = new AbortController();

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: history,
          context_paths: Array.from(selected),
          temporary_documents: temporaryDocuments,
          skill: skillSelect ? skillSelect.value : "",
        }),
        signal: abortCtrl.signal,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(err.error || "Något gick fel");
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        acc += decoder.decode(value, { stream: true });
        bubble.textContent = acc;
        chatScroll.scrollTop = chatScroll.scrollHeight;
      }
      if (acc.trim()) history.push({ role: "assistant", content: acc });
      renderContextMeter();
    } catch (err) {
      if (err.name === "AbortError") {
        acc += (acc ? "\n\n" : "") + "(avbrutet)";
      } else {
        acc = "Fel: " + err.message;
      }
      bubble.textContent = acc;
    } finally {
      streaming = false;
      abortCtrl = null;
      setSending(false);
    }
  }

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    if (streaming) {
      if (abortCtrl) abortCtrl.abort();
      return;
    }
    const q = chatInput.value.trim();
    if (!q) return;
    chatInput.value = "";
    chatInput.style.height = "auto";
    send(q);
  });

  chatInput.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 160) + "px";
  });
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      chatForm.requestSubmit();
    }
  });

  renderCtx();
  renderTemporaryDocuments();
})();
