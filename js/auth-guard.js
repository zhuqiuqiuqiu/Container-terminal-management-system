(() => {
  const protectedPage = document.body.dataset.authPage;
  if (!protectedPage) return;

  const pageLabels = {
    home: '首页大屏',
    container: '集装箱管理',
    yard: '堆场管理',
    ship: '船舶计划管理',
    'terminal-operations': '码头作业模块',
    import: '进口闭环管理',
    equipment: '设备管理',
    dangerous: '危险品管理',
    finance: '财务计费',
    users: '用户权限管理',
  };

  const hrefPages = [
    ['index.html', 'home'],
    ['container-management.html', 'container'],
    ['yard-management.html', 'yard'],
    ['ship-plan-management.html', 'ship'],
    ['terminal-operations.html', 'terminal-operations'],
    ['import-lifecycle.html', 'import'],
    ['equipment-management.html', 'equipment'],
    ['dangerous-management.html', 'dangerous'],
    ['finance-billing.html', 'finance'],
    ['user-management.html', 'users'],
  ];

  function pageFromHref(href) {
    const text = href || '';
    const item = hrefPages.find(([needle]) => text.includes(needle));
    return item ? item[1] : '';
  }

  function applyRoleUi(user) {
    const allowedPages = new Set(user.pages || []);
    document.body.dataset.userRole = user.role || '';
    document.querySelectorAll('a[href]').forEach((link) => {
      const page = pageFromHref(link.getAttribute('href'));
      if (page && !allowedPages.has(page)) {
        link.hidden = true;
        link.setAttribute('aria-hidden', 'true');
      }
    });
    document.querySelectorAll('[data-role-only]').forEach((node) => {
      const roles = node.dataset.roleOnly.split(',').map((item) => item.trim()).filter(Boolean);
      if (roles.length && !roles.includes(user.role)) node.hidden = true;
    });
    document.querySelectorAll('[data-permission]').forEach((node) => {
      const permission = node.dataset.permission;
      const permissions = user.permissions || [];
      if (!permissions.includes('*') && !permissions.includes(permission)) node.hidden = true;
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
      window.__CURRENT_USER__ = user;
      if (user.pages && !user.pages.includes(protectedPage)) {
        window.location.replace('/index.html');
        return;
      }
      const userNameNode = document.querySelector('[data-user-name]');
      const userRoleNode = document.querySelector('[data-user-role]');
      if (userNameNode) userNameNode.textContent = user.username;
      if (userRoleNode) userRoleNode.textContent = user.role;
      applyRoleUi(user);
      window.dispatchEvent(new CustomEvent('auth:user', { detail: user }));
    })
    .catch(() => {
      window.location.replace('/login.html');
    });
})();
