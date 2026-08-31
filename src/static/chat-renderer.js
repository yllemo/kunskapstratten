/* AI-output är opålitlig Markdown: sanera alltid före HTML-infogning. */
(() => {
  let mermaidPromise;
  let renderQueue = Promise.resolve();
  let diagramId = 0;

  function copyButton(source) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'code-copy';
    button.setAttribute('aria-live', 'polite');
    button.textContent = 'Kopiera kod';
    button.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(source);
        button.textContent = 'Kopierat!';
      } catch (_) {
        // Äldre webbläsare / HTTP utan Clipboard API.
        const area = document.createElement('textarea');
        area.value = source;
        area.style.cssText = 'position:fixed;left:-10000px;top:0';
        document.body.append(area);
        area.select();
        let copied = false;
        try { copied = document.execCommand('copy'); } catch (_) {}
        area.remove();
        button.focus();
        button.textContent = copied ? 'Kopierat!' : 'Kunde inte kopiera – markera koden';
      }
      setTimeout(() => { button.textContent = 'Kopiera kod'; }, 2500);
    });
    return button;
  }

  async function renderDiagram(target, source) {
    try {
      mermaidPromise ||= import('https://cdn.jsdelivr.net/npm/mermaid@latest/dist/mermaid.esm.min.mjs');
      const { default: mermaid } = await mermaidPromise;
      mermaid.initialize({startOnLoad:false, securityLevel:'strict', theme:'default', htmlLabels:false,
        flowchart:{htmlLabels:false}, suppressErrorRendering:true});
      const { svg } = await mermaid.render('chat-diagram-' + (++diagramId), source);
      // SVG utan externa resurser, HTML eller interaktiva länkar.
      target.innerHTML = DOMPurify.sanitize(svg, {USE_PROFILES:{svg:true, svgFilters:true}, FORBID_TAGS:['foreignObject','a','image','use']});
    } catch (_) {
      target.textContent = 'Diagrammet kunde inte renderas. Kontrollera Mermaid-koden eller anslutningen till CDN.';
      target.classList.add('diagram-error');
      if (target.nextElementSibling?.tagName === 'DETAILS') target.nextElementSibling.open = true;
    }
  }

  window.renderChatMarkdown = async (bubble, source) => {
    if (!window.marked || !window.DOMPurify) {
      bubble.textContent = source;
      return;
    }
    bubble.classList.add('chat-markdown');
    bubble.innerHTML = DOMPurify.sanitize(marked.parse(source, {gfm:true, breaks:true}), {
      USE_PROFILES:{html:true}, FORBID_TAGS:['img','style','input','form','button'],
      FORBID_ATTR:['style','id','name']
    });
    bubble.querySelectorAll('a').forEach(link => {
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
    });
    const pending = [];
    bubble.querySelectorAll('pre > code').forEach(code => {
      const source = code.textContent;
      const pre = code.parentElement;
      const frame = document.createElement('section');
      frame.className = 'chat-code-block';
      const toolbar = document.createElement('div');
      toolbar.className = 'code-toolbar';
      const label = document.createElement('span');
      const language = [...code.classList].find(name => name.startsWith('language-'))?.slice(9) || 'kod';
      label.textContent = language;
      toolbar.append(label, copyButton(source));
      pre.replaceWith(frame);
      frame.append(toolbar, pre);
      if (language.toLowerCase() === 'mermaid') {
        const diagram = document.createElement('div');
        diagram.className = 'chat-diagram';
        diagram.setAttribute('role', 'img');
        diagram.setAttribute('aria-label', 'Mermaid-diagram');
        diagram.textContent = 'Renderar diagram…';
        const details = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = 'Visa Mermaid-kod';
        details.append(summary, pre);
        frame.append(diagram, details);
        renderQueue = renderQueue.then(() => renderDiagram(diagram, source));
        pending.push(renderQueue);
      }
    });
    await Promise.all(pending);
  };
})();
