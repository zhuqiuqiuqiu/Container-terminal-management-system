(() => {
  const logoutBtn = document.getElementById('logoutBtn');
  const userRole = document.getElementById('homeUserRole');
  const userName = document.getElementById('homeUserName');

  if (logoutBtn) {
    logoutBtn.addEventListener('click', async () => {
      await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'same-origin',
      });
      window.location.replace('/login.html');
    });
  }

  fetch('/api/auth/me', { credentials: 'same-origin' })
    .then((resp) => {
      if (!resp.ok) throw new Error('unauthorized');
      return resp.json();
    })
    .then((data) => {
      const user = data && data.data ? data.data : null;
      if (!user) throw new Error('unauthorized');
      if (userName) userName.textContent = user.username;
      if (userRole) userRole.textContent = user.role;
    })
    .catch(() => {
      window.location.replace('/login.html');
    });
})();
