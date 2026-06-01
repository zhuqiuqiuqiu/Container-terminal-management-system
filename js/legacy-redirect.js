(() => {
  const params = new URLSearchParams(window.location.search);
  const view = params.get('view');
  if (view === 'containers') {
    window.location.replace('pages/container-management.html');
    return;
  }
  if (view === 'yardmap') {
    window.location.replace('pages/yard-management.html');
    return;
  }
  window.location.replace('index.html');
})();
