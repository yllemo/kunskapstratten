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
  let contextWindow = Number(CHAT_DATA.context_window) || 32768;
  document.addEventListener('settings-saved', event => {
    const settings = event.detail;
    contextWindow = settings.ai.context_window;
    CHAT_DATA.memory = settings.memory;
    CHAT_DATA.system_prompt = settings.ai.system_prompt;
    chatInput.disabled = chatSendBtn.disabled = !settings.ai.enabled;
    document.querySelectorAll('.chat-model-label, .chat-meta').forEach(el => { el.textContent = settings.ai.model + ' · ' + settings.ai.base_url; });
    renderContextMeter();
  });
  document.getElementById('toggleContext').onclick = () => {
    const open = document.getElementById('chatSidebar').classList.toggle('is-open');
    document.getElementById('toggleContext').setAttribute('aria-expanded', String(open));
  };
  document.getElementById('exportChat').onclick = () => {
    if (streaming || !history.length) {
      const status = document.getElementById('chatExportStatus');
      status.hidden = false;
      status.textContent = streaming ? 'Vänta tills svaret är klart innan du sparar.' : 'Starta en konversation först.';
      return;
    }
    document.getElementById('exportName').value = history[0].content.slice(0, 100);
    document.getElementById('exportStatus').textContent = '';
    document.getElementById('exportDialog').showModal();
  };
  document.getElementById('exportCancel').onclick = () => document.getElementById('exportDialog').close();
  document.getElementById('exportForm').onsubmit = async event => {
    event.preventDefault();
    event.submitter.disabled = true;
    const status = document.getElementById('exportStatus');
    try {
      const response = await fetch('/api/chat/export', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title:document.getElementById('exportName').value, messages:history})});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      const link = document.createElement('a');
      link.href = result.url;
      link.target = '_blank';
      link.rel = 'noopener';
      link.textContent = 'Sparat! Öppna dokumentet';
      status.replaceChildren(link);
    } catch(error) { status.textContent = error.message; }
    finally { event.submitter.disabled = false; }
  };

  function tokenEstimate(text) {
    return Math.ceil((text || "").length / 4);
  }

  function renderContextMeter() {
    const documentTokens = Array.from(selected).reduce((sum, path) => sum + tokenEstimate(docsByPath[path]?.body), 0)
      + temporaryDocuments.reduce((sum, doc) => sum + tokenEstimate(doc.body), 0);
    const historyTokens = history.reduce((sum, message) => sum + tokenEstimate(message.content) + 4, 0);
    const skill = skillsBySlug[skillSelect?.value];
    const skillTokens = skill ? tokenEstimate(skill.description + "\n" + skill.instructions) : 0;
    const memoryTokens = tokenEstimate(CHAT_DATA.memory);
    const used = documentTokens + historyTokens + skillTokens + memoryTokens + tokenEstimate(CHAT_DATA.system_prompt) + 200;
    document.getElementById('contextMemory').textContent = memoryTokens.toLocaleString('sv-SE');
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
    const status = document.getElementById('chatSkillStatus');
    status.textContent = '';
    skillDescription.textContent = skill ? skill.description : "Välj en skill. Den används först när du skickar nästa prompt.";
    if (!skill || streaming) { renderContextMeter(); return; }
    if (skill.document_error) { status.textContent = skill.document_error; return; }
    const paths = skill.document_paths || [];
    const missing = paths.filter(path => !docsByPath[path]);
    if (missing.length) {
      status.textContent = 'Skillen kan inte användas. Saknade dokument: ' + missing.join(', ') + '. Uppdatera skillens dokumentval.';
      return;
    }
    if (paths.length) {
      selected.clear();
      paths.forEach(path => selected.add(path));
      document.querySelectorAll('.doc-checkbox').forEach(check => { check.checked = selected.has(check.value); });
      renderCtx();
    }
    renderContextMeter();
    status.textContent = `${skill.name} är vald med ${selected.size} KB-dokument och används när du skickar nästa prompt.`;
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
    const label = document.createElement('span');
    label.className = 'chat-role';
    label.textContent = role === 'user' ? 'Du' : 'AI · Assistent';
    wrap.appendChild(label);
    wrap.appendChild(bubble);
    chatScroll.appendChild(wrap);
    chatScroll.scrollTop = chatScroll.scrollHeight;
    return bubble;
  }

  function setSending(on) {
    if (skillSelect) skillSelect.disabled = on;
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
      acc += decoder.decode();
      if (acc.trim()) history.push({ role: "assistant", content: acc });
      renderContextMeter();
    } catch (err) {
      if (err.name === "AbortError") {
        acc += (acc ? "\n\n" : "") + "(avbrutet)";
        history.push({ role: 'assistant', content: acc });
      } else {
        acc = "Fel: " + err.message;
      }
      bubble.textContent = acc;
    } finally {
      streaming = false;
      abortCtrl = null;
      setSending(false);
      renderContextMeter();
      const nearBottom = chatScroll.scrollHeight - chatScroll.scrollTop - chatScroll.clientHeight < 100;
      if (window.renderChatMarkdown) {
        await window.renderChatMarkdown(bubble, acc);
        if (nearBottom) chatScroll.scrollTop = chatScroll.scrollHeight;
      }
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
