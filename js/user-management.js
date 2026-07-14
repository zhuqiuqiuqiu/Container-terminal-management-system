const { createApp, reactive, ref, computed, onMounted } = Vue;

createApp({
  setup() {
    const currentTime = ref('');
    const message = ref('');
    const users = ref([]);
    const roles = ref([]);
    const permissions = ref([]);
    const searchQuery = ref('');
    const showDialog = ref(false);
    const editingUserId = ref(null);
    const form = reactive({
      username: '',
      password: '',
      role: 'operator',
      permissions: [],
    });

    async function apiRequest(path, options = {}) {
      const resp = await fetch(path, {
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        ...options,
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.message || `请求失败：${resp.status}`);
      return data;
    }

    function showMessage(text) {
      message.value = text;
      window.setTimeout(() => {
        if (message.value === text) message.value = '';
      }, 3000);
    }

    function tick() {
      currentTime.value = new Date().toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      });
    }

    function normalizeUser(item) {
      return {
        id: item.id,
        username: item.username || '',
        role: item.role || '',
        roleKey: item.roleKey || item.role || 'operator',
        permissions: item.permissions || [],
        extraPermissions: item.extraPermissions || [],
        pages: item.pages || [],
        lastLoginAt: item.lastLoginAt || '',
      };
    }

    async function loadOptions() {
      const data = await apiRequest('/api/users/options');
      roles.value = data.roles || [];
      permissions.value = data.permissions || [];
    }

    async function loadUsers() {
      const data = await apiRequest('/api/users');
      users.value = Array.isArray(data) ? data.map(normalizeUser) : [];
    }

    async function refreshAll() {
      try {
        await Promise.all([loadOptions(), loadUsers()]);
      } catch (err) {
        showMessage(err.message);
      }
    }

    const rolePermissionSet = computed(() => {
      const role = roles.value.find((item) => item.value === form.role);
      return new Set(role ? role.permissions || [] : []);
    });

    const permissionMap = computed(() => {
      const map = {};
      permissions.value.forEach((item) => {
        map[item.value] = item.label;
      });
      return map;
    });

    const filteredUsers = computed(() => {
      const query = searchQuery.value.toLowerCase();
      if (!query) return users.value;
      return users.value.filter((user) => {
        const text = [
          user.username,
          user.role,
          user.roleKey,
          user.extraPermissions.join(','),
          user.pages.join(','),
        ].join(' ').toLowerCase();
        return text.includes(query);
      });
    });

    const customPermissionCount = computed(() => users.value.filter((user) => user.extraPermissions.length).length);

    function permissionLabel(value) {
      return permissionMap.value[value] || value;
    }

    function roleHasPermission(value) {
      return rolePermissionSet.value.has('*') || rolePermissionSet.value.has(value);
    }

    function roleCount(roleKey) {
      return users.value.filter((user) => user.roleKey === roleKey).length;
    }

    function pageText(pages) {
      const labels = {
        home: '首页',
        container: '集装箱',
        yard: '堆场',
        ship: '船舶',
        'terminal-operations': '作业',
        import: '进口',
        equipment: '设备',
        dangerous: '危险品',
        finance: '财务',
        users: '用户权限',
      };
      return (pages || []).map((page) => labels[page] || page).join('、') || '-';
    }

    function resetForm() {
      form.username = '';
      form.password = '';
      form.role = roles.value[0]?.value || 'operator';
      form.permissions = [];
      editingUserId.value = null;
    }

    function openDialog(user = null) {
      if (user) {
        editingUserId.value = user.id;
        form.username = user.username;
        form.password = '';
        form.role = user.roleKey;
        form.permissions = [...user.extraPermissions];
      } else {
        resetForm();
      }
      showDialog.value = true;
    }

    function closeDialog() {
      showDialog.value = false;
      resetForm();
    }

    function clearPermissions() {
      form.permissions = [];
    }

    async function saveUser() {
      try {
        const payload = {
          username: form.username,
          role: form.role,
          permissions: form.permissions.filter((permission) => !roleHasPermission(permission)),
        };
        if (form.password) payload.password = form.password;
        const path = editingUserId.value ? `/api/users/${editingUserId.value}` : '/api/users';
        const method = editingUserId.value ? 'PUT' : 'POST';
        const data = await apiRequest(path, { method, body: JSON.stringify(payload) });
        showMessage(data.message);
        closeDialog();
        await loadUsers();
      } catch (err) {
        showMessage(err.message);
      }
    }

    async function deleteUser(user) {
      if (!confirm(`确定删除账号「${user.username}」吗？`)) return;
      try {
        const data = await apiRequest(`/api/users/${user.id}`, { method: 'DELETE' });
        showMessage(data.message);
        await loadUsers();
      } catch (err) {
        showMessage(err.message);
      }
    }

    onMounted(() => {
      tick();
      window.setInterval(tick, 1000);
      refreshAll();
    });

    return {
      currentTime,
      message,
      users,
      roles,
      permissions,
      searchQuery,
      showDialog,
      editingUserId,
      form,
      filteredUsers,
      customPermissionCount,
      permissionLabel,
      roleHasPermission,
      roleCount,
      pageText,
      openDialog,
      closeDialog,
      clearPermissions,
      saveUser,
      deleteUser,
      refreshAll,
    };
  },
}).mount('#app');
