(() => {
  const panel = document.getElementById('articlePreview');
  if (!panel) return;
  const content = document.getElementById('previewContent');
  const title = document.getElementById('previewTitle');
  const close = document.getElementById('previewClose');
  const cache = new Map();
  let controller;

  const enabled = () => panel.dataset.enabled === 'true';
  const textElement = (tag, className, value) => {
    const element = document.createElement(tag);
    element.className = className;
    element.textContent = value;
    return element;
  };
  const hide = () => {
    panel.hidden = true;
  };
  function render(doc) {
    title.textContent = doc.title;
    content.replaceChildren(textElement('p', 'preview-meta', `${doc.source_type} · Ändrad ${doc.modified} · ${doc.rel_path}`));
    if (doc.summary) content.append(textElement('p', 'preview-summary', doc.summary));
    if (doc.tags.length) {
      const tags = document.createElement('div');
      tags.className = 'card-tags preview-tags';
      doc.tags.forEach(tag => {
        const link = textElement('a', 'tag-chip small', `#${tag}`);
        link.href = `${panel.dataset.browseUrl}?tag=${encodeURIComponent(tag)}`;
        tags.append(link);
      });
      content.append(tags);
    }
    if (doc.frontmatter) {
      const details = document.createElement('details');
      details.className = 'preview-frontmatter';
      details.open = true;
      const summary = document.createElement('summary');
      summary.textContent = 'YAML-frontmatter';
      details.append(summary, textElement('pre', 'preview-yaml', `---\n${doc.frontmatter}\n---`));
      content.append(details);
    }
    content.append(textElement('pre', 'preview-body', doc.body || 'Dokumentet saknar brödtext.'));
    if (doc.truncated) content.append(textElement('p', 'preview-truncated', 'Förhandsvisningen är förkortad. Öppna dokumentet för att läsa resten.'));
    document.getElementById('previewOpen').href = doc.urls.open;
    document.getElementById('previewEdit').href = doc.urls.edit;
    document.getElementById('previewChat').href = doc.urls.chat;
  }
  document.querySelectorAll('.preview-trigger').forEach(trigger => trigger.addEventListener('click', async event => {
    if (!enabled() || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault();
    panel.hidden = false;
    title.textContent = 'Laddar…';
    content.replaceChildren(textElement('p', 'preview-loading', 'Hämtar dokumentet…'));
    controller?.abort();
    controller = new AbortController();
    try {
      let doc = cache.get(trigger.dataset.previewUrl);
      if (!doc) {
        const response = await fetch(trigger.dataset.previewUrl, {signal: controller.signal});
        doc = await response.json();
        if (!response.ok) throw new Error(doc.error || 'Dokumentet kunde inte hämtas.');
        cache.set(trigger.dataset.previewUrl, doc);
      }
      render(doc);
      close.focus();
    } catch (error) {
      if (error.name !== 'AbortError') content.replaceChildren(textElement('p', 'form-error', error.message));
    }
  }));
  close.addEventListener('click', hide);
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !panel.hidden) hide(); });
  document.addEventListener('settings-saved', event => {
    panel.dataset.enabled = String(Boolean(event.detail.preview_enabled));
    if (!enabled()) hide();
  });
})();
