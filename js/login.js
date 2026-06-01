const form = document.getElementById('loginForm');
const message = document.getElementById('loginMessage');

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  message.textContent = '正在登录...';
  message.className = 'login-message';

  const payload = {
    username: document.getElementById('username').value.trim(),
    password: document.getElementById('password').value,
  };

  try {
    const resp = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      credentials: 'same-origin',
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.message || '登录失败');
    }
    message.textContent = '登录成功，正在进入首页...';
    message.className = 'login-message success';
    window.location.replace('/index.html');
  } catch (err) {
    message.textContent = err.message || '登录失败';
    message.className = 'login-message error';
  }
});
