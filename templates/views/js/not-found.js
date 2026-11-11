(() => {
  const menuToggle = document.getElementById('public-menu-toggle');
  const sidebar = document.getElementById('public-sidebar');
  const sidebarScrim = document.getElementById('public-sidebar-scrim');
  const profileButton = document.getElementById('public-profile');
  const guestDrawer = document.getElementById('public-drawer-guest');
  const memberDrawer = document.getElementById('public-drawer-member');
  let menuTrigger = null;

  function closePublicMenu(restoreFocus = false) {
    sidebar.classList.remove('sidebar-open');
    sidebarScrim.classList.remove('sidebar-scrim-open');
    sidebar.setAttribute('aria-hidden', 'true');
    sidebar.setAttribute('inert', '');
    menuToggle.setAttribute('aria-expanded', 'false');
    profileButton.setAttribute('aria-expanded', 'false');
    if (restoreFocus) (menuTrigger || menuToggle).focus();
    menuTrigger = null;
  }

  function openPublicMenu(trigger) {
    menuTrigger = trigger;
    sidebar.classList.add('sidebar-open');
    sidebarScrim.classList.add('sidebar-scrim-open');
    sidebar.setAttribute('aria-hidden', 'false');
    sidebar.removeAttribute('inert');
    menuToggle.setAttribute('aria-expanded', 'true');
    profileButton.setAttribute('aria-expanded', 'true');
  }

  async function loadPublicAccount() {
    const token = sessionStorage.getItem('fitlife-token');
    if (!token) return;

    try {
      const response = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        if (response.status === 401) {
          sessionStorage.removeItem('fitlife-token');
          sessionStorage.removeItem('fitlife-credential');
          return;
        }
        throw new Error('No fue posible verificar tu sesión.');
      }

      const { user } = await response.json();
      const fullName = [user.nombres, user.apellido_paterno].filter(Boolean).join(' ');
      const roles = user.roles || [];
      const role = roles.includes('SOCIO') ? 'Socio FitLife'
        : roles.includes('INSTRUCTOR') ? 'Equipo FitLife'
          : roles.includes('ADMINISTRADOR') ? 'Administrador' : 'Recepción';
      const avatar = fullName.trim().charAt(0).toUpperCase() || 'F';

      document.getElementById('public-user-name').textContent = fullName;
      document.getElementById('public-user-role').textContent = role;
      document.getElementById('public-avatar').textContent = avatar;
      document.getElementById('public-drawer-name').textContent = fullName;
      document.getElementById('public-drawer-role').textContent = role;
      document.getElementById('public-drawer-avatar').textContent = avatar;
      document.getElementById('public-auth-links').classList.add('hidden');
      profileButton.classList.remove('hidden');
      guestDrawer.classList.add('hidden');
      memberDrawer.classList.remove('hidden');
    } catch (error) {
      console.error(error);
    }
  }

  menuToggle.addEventListener('click', () => {
    if (sidebar.classList.contains('sidebar-open')) closePublicMenu();
    else openPublicMenu(menuToggle);
  });
  profileButton.addEventListener('click', () => {
    if (sidebar.classList.contains('sidebar-open')) closePublicMenu();
    else openPublicMenu(profileButton);
  });
  sidebarScrim.addEventListener('click', () => closePublicMenu(true));
  document.getElementById('public-drawer-close').addEventListener('click', () => closePublicMenu(true));
  sidebar.addEventListener('click', event => {
    if (event.target.closest('a')) closePublicMenu();
  });
  document.getElementById('public-logout').addEventListener('click', () => {
    sessionStorage.removeItem('fitlife-token');
    sessionStorage.removeItem('fitlife-credential');
    location.assign('/');
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && sidebar.classList.contains('sidebar-open')) closePublicMenu(true);
  });

  loadPublicAccount();
})();
