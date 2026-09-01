(() => {
  const $ = id => document.getElementById(id);
  const dialog = $('settingsDialog');
  let provider = 'ollama';
  let resetToken = null;
  let resetBusy = false;
  const tabs = [...dialog.querySelectorAll('[role=tab]')];
  function selectTab(tab) {
    tabs.forEach(item => {
      const selected = item === tab;
      item.setAttribute('aria-selected', String(selected));
      item.tabIndex = selected ? 0 : -1;
      $(item.getAttribute('aria-controls')).hidden = !selected;
    });
    $('settingsSave').hidden = tab.id === 'tab-reset';
    $('settingsStatus').hidden = tab.id === 'tab-reset';
  }
  tabs.forEach((tab,index) => {
    tab.onclick = () => selectTab(tab);
    tab.onkeydown = event => {
      const target = event.key === 'ArrowRight' ? (index+1)%tabs.length : event.key === 'ArrowLeft' ? (index+tabs.length-1)%tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length-1 : null;
      if (target !== null) { event.preventDefault(); selectTab(tabs[target]); tabs[target].focus(); }
    };
  });
  // Gör även ogiltiga fält i dolda flikar tillgängliga vid formulärvalidering.
  $('settingsForm').addEventListener('invalid', event => {
    const panel = event.target.closest('[role=tabpanel]');
    if (panel) selectTab($(panel.getAttribute('aria-labelledby')));
  }, true);
  function clearReset() {
    resetToken = null;
    $('resetConsent').checked = false;
    $('resetPrepare').disabled = true;
    $('resetVerification').hidden = true;
    $('resetAnswer').value = '';
    $('resetExecute').disabled = true;
    $('resetStatus').textContent = '';
  }
  $('resetConsent').onchange = () => {
    $('resetPrepare').disabled = !$('resetConsent').checked;
    resetToken = null;
    $('resetVerification').hidden = true;
  };
  $('resetAnswer').oninput = () => {
    $('resetExecute').disabled = !resetToken || !$('resetConsent').checked || !$('resetAnswer').value.trim();
  };
  $('resetPrepare').onclick = async () => {
    $('resetPrepare').disabled = true;
    $('resetStatus').textContent = 'Kontrollerar mappar och filer…';
    resetToken = null;
    $('resetVerification').hidden = true;
    try {
      const result = await api('/api/reset/challenge', {});
      resetToken = result.token;
      $('resetQuestion').textContent = result.question;
      $('resetSummary').textContent = `${result.total} filer kommer att raderas:`;
      $('resetTargets').replaceChildren(...result.targets.map(target => {
        const item = document.createElement('li');
        item.textContent = `${target.path} — ${target.scope}: ${target.files} filer`;
        return item;
      }));
      $('resetAnswer').value = '';
      $('resetExecute').disabled = true;
      $('resetVerification').hidden = false;
      $('resetStatus').textContent = '';
    } catch(error) { $('resetStatus').textContent = error.message; }
    finally { $('resetPrepare').disabled = !$('resetConsent').checked; }
  };
  $('resetExecute').onclick = async () => {
    if (!resetToken || !$('resetConsent').checked || resetBusy) return;
    resetBusy = true;
    $('resetExecute').disabled = $('resetPrepare').disabled = true;
    $('resetStatus').textContent = 'Raderar… Stäng inte appen.';
    try {
      const result = await api('/api/reset', {token:resetToken,confirmed:true,answer:$('resetAnswer').value.trim()});
      $('resetStatus').textContent = `${result.removed} filer raderades. Laddar en tom kunskapsbank…`;
      location.assign('/browse');
    } catch(error) {
      $('resetStatus').textContent = error.message;
      resetToken = null;
      $('resetExecute').disabled = true;
      $('resetPrepare').disabled = !$('resetConsent').checked;
    } finally { resetBusy = false; }
  };
  dialog.addEventListener('cancel', event => { if (resetBusy) event.preventDefault(); });
  dialog.addEventListener('close', clearReset);
  const presets = {openai: 'https://api.openai.com/v1', lmstudio: 'http://localhost:1234/v1', ollama: 'http://localhost:11434'};
  function showProvider() {
    document.querySelectorAll('[data-provider]').forEach(button => {
      button.classList.toggle('active', button.dataset.provider === provider);
      button.setAttribute('aria-pressed', String(button.dataset.provider === provider));
    });
    $('providerNote').textContent = provider === 'ollama' ? 'Ollama – anslutningen görs från servern. /v1 läggs till automatiskt för API-anrop.' : provider === 'lmstudio' ? 'LM Studio – starta den lokala servern. Standardport är 1234.' : 'OpenAI-kompatibel tjänst – ange serverns bas-URL inklusive /v1.';
  }
  async function api(url, data) {
    const response = await fetch(url, data ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)} : {});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Begäran misslyckades');
    return result;
  }
  function values() {
    return {title:$('kbTitle').value, memory:$('kbMemory').value, preview_enabled:$('previewEnabled').checked, ai:{provider, enabled:$('aiEnabled').checked, base_url:$('aiBaseUrl').value, api_key:$('aiApiKey').value, clear_api_key:$('clearApiKey').checked, model:$('aiModel').value, temperature:Number($('aiTemperature').value), context_window:Number($('aiContextWindow').value), system_prompt:$('aiSystemPrompt').value}};
  }
  $('settingsBtn').onclick = async () => {
    clearReset();
    selectTab($('tab-ai'));
    dialog.showModal();
    $('settingsStatus').textContent = 'Läser inställningar…';
    try {
      const data = await api('/api/settings');
      provider = data.ai.provider;
      $('kbTitle').value = data.title;
      $('previewEnabled').checked = data.preview_enabled;
      $('kbMemory').value = data.memory;
      $('aiEnabled').checked = data.ai.enabled;
      $('aiBaseUrl').value = data.ai.base_url;
      $('aiApiKey').value = '';
      $('clearApiKey').checked = false;
      $('aiModel').value = data.ai.model;
      $('aiModelSelect').replaceChildren(new Option('— skriv eller hämta —', ''));
      $('aiTemperature').value = data.ai.temperature;
      $('temperatureValue').value = data.ai.temperature;
      $('aiContextWindow').value = data.ai.context_window;
      $('aiSystemPrompt').value = data.ai.system_prompt;
      $('settingsStatus').textContent = data.ai.has_api_key ? 'En API-nyckel är sparad.' : '';
      showProvider();
    } catch(error) { $('settingsStatus').textContent = error.message; }
  };
  $('settingsClose').onclick = $('settingsCancel').onclick = () => { if (!resetBusy) dialog.close(); };
  document.querySelectorAll('[data-provider]').forEach(button => button.onclick = () => {
    provider = button.dataset.provider;
    $('aiBaseUrl').value = presets[provider];
    $('aiApiKey').value = '';
    $('clearApiKey').checked = true;
    $('aiModelSelect').replaceChildren(new Option('— skriv eller hämta —', ''));
    showProvider();
  });
  $('aiModelSelect').onchange = () => { if ($('aiModelSelect').value) $('aiModel').value = $('aiModelSelect').value; };
  $('aiTemperature').oninput = () => { $('temperatureValue').value = $('aiTemperature').value; };
  for (const [id, action] of [['fetchModels','models'], ['testConnection','test']]) {
    $(id).onclick = async () => {
      $(id).disabled = true;
      $('settingsStatus').textContent = 'Ansluter…';
      try {
        const result = await api('/api/settings/' + action, values());
        if (result.models) $('aiModelSelect').replaceChildren(new Option('— välj modell —', ''), ...result.models.map(model => new Option(model, model)));
        $('settingsStatus').textContent = result.models ? `${result.models.length} modeller hittades.` : 'Anslutningen fungerar!';
      } catch(error) { $('settingsStatus').textContent = error.message; }
      finally { $(id).disabled = false; }
    };
  }
  $('settingsForm').onsubmit = async event => {
    event.preventDefault();
    if ($('tab-reset').getAttribute('aria-selected') === 'true' || resetBusy) return;
    const button = event.submitter;
    button.disabled = true;
    try {
      await api('/api/settings', values());
      $('settingsStatus').textContent = 'Sparat på lokal disk.';
      document.querySelector('.brand').textContent = $('kbTitle').value;
      document.title = document.title.replace(/ – .*$/, '') + ' – ' + $('kbTitle').value;
      document.querySelector('.site-footer span').textContent = $('kbTitle').value + ' · körs lokalt på ' + location.host;
      document.dispatchEvent(new CustomEvent('settings-saved', {detail: values()}));
      dialog.close();
    } catch(error) { $('settingsStatus').textContent = error.message; }
    finally { button.disabled = false; }
  };
})();
