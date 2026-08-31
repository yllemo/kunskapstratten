function initTheme() {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  const current = document.documentElement.getAttribute("data-theme") || "light";
  btn.textContent = current === "dark" ? "☀" : "◐";
  btn.addEventListener("click", () => {
    const now = document.documentElement.getAttribute("data-theme");
    const next = now === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
    btn.textContent = next === "dark" ? "☀" : "◐";
    window.dispatchEvent(new CustomEvent("kunskapsbank:themechange", { detail: { theme: next } }));
  });
}
initTheme();

function initNavigation() {
  const button = document.getElementById("nav-toggle");
  const nav = document.getElementById("main-nav");
  if (!button || !nav) return;

  function closeNav() {
    button.setAttribute('aria-expanded', 'false');
    nav.classList.remove('is-open');
    button.querySelector('[aria-hidden]').textContent = '☰';
    button.querySelector('.sr-only').textContent = 'Öppna meny';
  }

  document.addEventListener('click', event => {
    if (!nav.contains(event.target) && !button.contains(event.target)) closeNav();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && nav.classList.contains('is-open')) {
      closeNav();
      button.focus();
    }
  });
  nav.addEventListener('click', event => {
    if (event.target.closest('a,button')) closeNav();
  });

  button.addEventListener("click", () => {
    const open = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(!open));
    nav.classList.toggle("is-open", !open);
    button.querySelector("[aria-hidden]").textContent = open ? "☰" : "×";
    button.querySelector(".sr-only").textContent = open ? "Öppna meny" : "Stäng meny";
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 1100) closeNav();
  });
}
initNavigation();

function initHelp() {
  const button = document.getElementById('helpBtn');
  const dialog = document.getElementById('helpDialog');
  const frame = document.getElementById('helpFrame');
  if (!button || !dialog || !frame) return;
  button.addEventListener('click', () => {
    if (!frame.hasAttribute('src')) frame.src = frame.dataset.src;
    dialog.showModal();
  });
  document.getElementById('helpClose').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
  window.addEventListener('message', event => {
    if (event.source === frame.contentWindow && event.data === 'kunskapstratten:close-help' && dialog.open) dialog.close();
  });
  dialog.addEventListener('close', () => button.focus());
}
initHelp();

async function postJSON(url, data) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data || {}),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || "Något gick fel");
  }
  return res.json();
}

function showToast(message) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => { toast.hidden = true; }, 5000);
}

const reindexBtn = document.getElementById("reindex-btn");
if (reindexBtn) {
  reindexBtn.addEventListener("click", async () => {
    reindexBtn.disabled = true;
    const original = reindexBtn.textContent;
    reindexBtn.textContent = "Uppdaterar…";
    try {
      const data = await postJSON("/api/reindex", {});
      const i = data.ingest || {};
      const s = data.skills || {};
      showToast(
        `Klart: ${i.processed ?? 0} nya filer inlästa, ` +
        `${s.skills ?? 0} bearbetningsskills tillgängliga.`
      );
    } catch (e) {
      showToast("Fel vid uppdatering: " + e.message);
    } finally {
      reindexBtn.disabled = false;
      reindexBtn.textContent = original;
    }
  });
}
