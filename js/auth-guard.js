(() => {
  const protectedPage = document.body.dataset.authPage;
  if (!protectedPage) return;

  fetch('/api/auth/me', { credentials: 'same-origin' })
    .then((resp) => {
      if (!resp.ok) throw new Error('unauthorized');
      return resp.json();
    })
    .then((data) => {
      const user = data && data.data ? data.data : null;
      if (!user) throw new Error('unauthorized');
      window.__CURRENT_USER__ = user;
      const userNameNode = document.querySelector('[data-user-name]');
      const userRoleNode = document.querySelector('[data-user-role]');
      if (userNameNode) userNameNode.textContent = user.username;
      if (userRoleNode) userRoleNode.textContent = user.role;
    })
    .catch(() => {
      window.location.replace('/login.html');
    });
})();
