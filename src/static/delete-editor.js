(() => {
  const button = document.getElementById('deleteItemBtn');
  if (!button) return;
  button.addEventListener('click', async () => {
    const status = document.getElementById('saveStatus');
    const save = document.getElementById('saveDocBtn') || document.getElementById('saveSkillBtn');
    if (save.disabled) return;
    button.disabled = save.disabled = true;
    try {
      const preview = await fetch(button.dataset.url);
      const plan = await preview.json();
      if (!preview.ok) throw new Error(plan.error);
      if (!window.confirm('Radera permanent?\n\n' + plan.files.join('\n') +
          '\n\nKopplat original i processed och importhistorik tas också bort om de finns. Skillens valda KB-filer tas INTE bort. Osparade ändringar försvinner. Detta kan inte ångras.')) return;
      const response = await fetch(button.dataset.url, {
        method: 'DELETE', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({confirm: true, version: plan.version})
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      window.location.href = button.dataset.back;
    } catch (error) {
      status.textContent = error.message;
      status.className = 'save-status err';
    } finally {
      button.disabled = save.disabled = false;
    }
  });
})();
