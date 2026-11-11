import { createDashboardForms } from './dashboard/forms.js';
import { createDashboardViews } from './dashboard/views.js';
import { bindDashboardEvents } from './dashboard/events.js';
import { getInstructorSpecialty, instructorSpecialties } from './dashboard/specialties.js';

(() => {
  const token = sessionStorage.getItem('fitlife-token');
  const content = document.getElementById('page-content');
  const nav = document.getElementById('main-nav');
  const drawerNav = document.getElementById('drawer-nav');
  const state = {
    data: null, route: 'home', credentialUrl: null, cameraStream: null, scanTimer: null,
    scanStarting: false, scanInProgress: false,
    adminEntityData: null, adminEntityKey: 'personas', attendanceSessionId: null,
    selectedInstallationId: null,
    selectedAdminInstallationId: null,
    membershipInstallationId: '',
    selectedGymWeekday: null,
    classImageTrigger: null,
  };
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
  const initials = value => value.trim().split(/\s+/).filter(Boolean).map(part => part[0]).slice(0, 2).join('').toUpperCase();
  const money = value => '$' + Number(value || 0).toLocaleString('es-CL');
  const dateTime = value => new Intl.DateTimeFormat('es-CL', {
    weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value));
  const dateOnly = value => new Intl.DateTimeFormat('es-CL', {
    day: 'numeric', month: 'long', year: 'numeric',
  }).format(new Date(`${value}T12:00:00`));
  const weekdayInChile = value => {
    const weekday = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Santiago', weekday: 'short',
    }).format(new Date(value));
    return { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 }[weekday];
  };
  const roleLabels = {
    ADMINISTRADOR: 'Administrador',
    RECEPCIONISTA: 'Recepción',
    INSTRUCTOR: 'Equipo FitLife',
    SOCIO: 'Socio FitLife',
  };
  const professionalLabels = {
    MONITOR: 'Monitor',
    PERSONAL_TRAINER: 'Entrenador personal',
    COACH: 'Coach',
    PREPARADOR_FISICO: 'Preparador físico',
  };
  const menuGroups = {
    home: 'Principal',
    classes: 'Gestión',
    memberships: 'Gestión',
    installations: 'Gestión',
    'installation-detail': 'Gestión',
    users: 'Gestión',
    reports: 'Análisis',
    alerts: 'Análisis',
    access: 'Operación',
    reservations: 'Mi actividad',
    credential: 'Mi actividad',
    sessions: 'Mi jornada',
    attendance: 'Mi jornada',
    team: 'Mi jornada',
    gym: 'Mi espacio',
    plans: 'Mi actividad',
  };
  const statusClass = status => ({
    ACTIVA: 'ok', RESERVADA: 'ok', OPERATIVA: 'ok', AUTORIZADO: 'ok',
    EN_CURSO: 'info', EN_ESPERA: 'info', PENDIENTE: 'warn', CONGELADA: 'warn', MANTENCION: 'warn',
    VENCIDA: 'bad', CANCELADA: 'bad', FUERA_SERVICIO: 'bad', RECHAZADO: 'bad',
  }[status] || 'muted');
  const badge = status => `<span class="badge ${statusClass(status)}">${esc(String(status || '').replaceAll('_', ' ').toLowerCase())}</span>`;

  async function api(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    });
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json() : await response.blob();
    if (!response.ok) throw new Error(data.error || 'No se pudo completar la solicitud.');
    return data;
  }

  function toast(message, error = false) {
    const container = document.getElementById('toast-container');
    const item = document.createElement('div');
    item.className = `toast-message ${error ? 'toast-error' : ''}`;
    item.textContent = message;
    container.append(item);
    setTimeout(() => item.remove(), 3500);
  }

  function confirmTrialRedemption(button) {
    const dialog = document.getElementById('trial-confirmation');
    const plan = (state.data.plans || []).find(item =>
      String(item.plan_id) === button.dataset.redeemTrial,
    );
    const installation = (state.data.installations || []).find(item =>
      String(item.instalacion_id) === button.dataset.redeemInstallation,
    );
    const planName = plan?.nombre || 'este plan';
    const installationName = installation?.nombre || 'la sede seleccionada';
    document.getElementById('trial-confirmation-message').textContent =
      `¿Quieres activar ${planName} en ${installationName}? La prueba gratuita se puede canjear una sola vez. No necesitas ingresar datos de pago y no se generará ningún cobro.`;
    dialog.returnValue = '';
    dialog.showModal();
    return new Promise(resolve => {
      dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), { once: true });
    });
  }

  function setInstallationCapacityVisibility(inputId, enabled) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const label = input.closest('label');
    input.disabled = !enabled;
    input.required = enabled;
    label?.classList.toggle('hidden', !enabled);
    if (enabled && Number(input.value) < 1) input.value = '1';
    if (!enabled) input.value = '0';
  }

  function stopScanner() {
    state.cameraStream?.getTracks().forEach(track => track.stop());
    state.cameraStream = null;
    clearInterval(state.scanTimer);
    state.scanTimer = null;
    state.scanInProgress = false;
    const video = document.getElementById('scanner-video');
    if (video) {
      video.pause();
      video.srcObject = null;
    }
    const button = document.getElementById('scan-camera');
    if (button) {
      button.textContent = 'Activar cámara QR';
      button.disabled = false;
    }
  }

  function roleName(data) {
    if (data.professional_profile?.tipo) return professionalLabels[data.professional_profile.tipo] || 'Equipo FitLife';
    return data.roles.map(role => roleLabels[role] || role).join(' · ');
  }

  function menus(data) {
    const roles = data.roles;
    if (roles.includes('ADMINISTRADOR')) {
      return [
        ['home', 'Resumen', '⌂'], ['gym', 'Tu gimnasio', '⌖'], ['classes', 'Cursos y clases', '◷'],
        ['memberships', 'Planes y membresías', '◇'], ['installations', 'Sedes', '⌖'], ['users', 'Usuarios', '♙'],
        ['reports', 'Reportes', '▤'], ['alerts', 'Alertas', '♧'], ['access', 'Control de acceso', '⌁'],
      ];
    }
    if (roles.includes('RECEPCIONISTA')) {
      return [['home', 'Resumen', '⌂'], ['gym', 'Tu gimnasio', '⌖'], ['access', 'Control de acceso', '⌁'], ['alerts', 'Accesos recientes', '♧']];
    }
    if (roles.includes('INSTRUCTOR')) {
      const specialty = getInstructorSpecialty(data);
      return [
        ['home', specialty?.navigation[0][1] || 'Mi jornada', '⌂'],
        ['gym', 'Tu gimnasio', '⌖'],
        ...(specialty?.navigation.slice(1) || []),
      ];
    }
    return [['home', 'Mi suscripción', '⌂'], ['plans', 'Planes disponibles', '◇'], ['gym', 'Tu gimnasio', '⌖'], ['classes', 'Clases y actividades', '◷'], ['reservations', 'Mis reservas', '▤'], ['credential', 'Mi credencial QR', '⌁']];
  }

  function shell() {
    const data = state.data;
    const user = data.user;
    const fullName = `${user.nombres} ${user.apellido_paterno || ''}`.trim();
    const role = roleName(data);
    document.body.className = data.roles.includes('SOCIO') && !data.roles.some(item => ['ADMINISTRADOR', 'INSTRUCTOR', 'RECEPCIONISTA'].includes(item))
      ? 'theme-client' : data.professional_profile?.tipo ? 'theme-admin theme-staff' : 'theme-admin';
    document.getElementById('user-name').textContent = fullName;
    document.getElementById('user-role').textContent = role;
    document.getElementById('user-avatar').textContent = user.nombres.slice(0, 1).toUpperCase();
    document.getElementById('top-name').textContent = fullName;
    document.getElementById('top-role').textContent = role;
    document.getElementById('top-avatar').textContent = initials(fullName);
    document.getElementById('current-year').textContent = new Date().getFullYear();
    const alertCount = [
      ...(data.occupancy || []).filter(item => Number(item.porcentaje_ocupacion || 0) >= 85),
      ...(data.waitlist || []),
      ...(data.machines || []).filter(item => item.estado !== 'OPERATIVA'),
      ...(Number(data.summary?.membresias_vencidas || 0) > 0 ? [true] : []),
    ].length;
    const groups = [];
    const menuItems = menus(data);
    for (const [route, label] of menuItems) {
      const group = menuGroups[route] || 'FitLife';
      let section = groups.find(item => item.label === group);
      if (!section) {
        section = { label: group, items: [] };
        groups.push(section);
      }
      section.items.push(
        `<button class="drawer-nav-item ${state.route === route ? 'active' : ''}" type="button" data-route="${route}"${state.route === route ? ' aria-current="page"' : ''}><span>${esc(label)}</span>${route === 'alerts' && alertCount ? `<span class="drawer-count">${alertCount}</span>` : ''}</button>`
      );
    }
    drawerNav.innerHTML = groups.map(group =>
      `<div class="drawer-nav-group"><span class="drawer-nav-label">${esc(group.label)}</span>${group.items.join('')}</div>`
    ).join('');
    const topItems = data.roles.includes('ADMINISTRADOR')
      ? menuItems.filter(([route]) => ['home', 'installations', 'classes', 'memberships'].includes(route))
      : menuItems.slice(0, 5);
    const topLabels = {
      home: data.roles.includes('ADMINISTRADOR') ? 'Dashboard' : menuItems.find(item => item[0] === 'home')?.[1] || 'Inicio',
      gym: 'Tu gimnasio',
      classes: data.roles.includes('ADMINISTRADOR') ? 'Cursos' : 'Clases',
      machines: 'Recursos',
      installations: 'Sedes',
      reports: 'Reportes',
      alerts: 'Alertas',
    };
    nav.innerHTML = topItems.map(([route, label]) =>
      `<button class="top-nav-item ${state.route === route ? 'active' : ''}" type="button" data-route="${route}"${state.route === route ? ' aria-current="page"' : ''}>${esc(topLabels[route] || label)}${route === 'alerts' && alertCount ? `<span class="top-nav-count">${alertCount}</span>` : ''}</button>`
    ).join('');
    const isAdmin = data.roles.includes('ADMINISTRADOR');
    const specialty = data.roles.includes('INSTRUCTOR') ? getInstructorSpecialty(data) : null;
    const actionLabel = isAdmin
      ? '+ Agregar curso'
      : specialty?.navigation[1]?.[1] || (specialty ? specialty.navigation[0][1] : 'Explorar clases');
    document.querySelectorAll('[data-quick-action]').forEach(button => {
      button.textContent = actionLabel;
      button.dataset.actionRoute = isAdmin ? 'classes' : data.roles.includes('INSTRUCTOR') ? 'sessions' : 'classes';
      button.dataset.actionAdmin = isAdmin ? 'true' : 'false';
      if (specialty && specialty.navigation[1]?.[0] !== 'sessions') {
        button.dataset.actionRoute = specialty.navigation[1]?.[0] || 'home';
      }
    });
  }

  const dashboardForms = createDashboardForms({ state, esc, professionalLabels, api });
  const {
    locationFieldsHTML, updateCityOther, updateCityOptions, normalizeLocationPayload,
    parseScheduleRange, setScheduleRange, updatePlanScopeFields, filterPlanSites,
    updatePlanSiteCityFilter, updateClassResources, renderAdminField, loadAdminRecords,
  } = dashboardForms;
  const dashboardViews = createDashboardViews({
    token, content, state, esc, money, dateTime, dateOnly, weekdayInChile,
    roleLabels, professionalLabels, badge, locationFieldsHTML, parseScheduleRange,
    updateClassResources, instructorSpecialties,
  });
  const { view, sessionsTable } = dashboardViews;

  async function refresh(nextRoute = state.route) {
    state.data = await api('/api/dashboard');
    if (state.data.roles.includes('INSTRUCTOR')) {
      state.data.professional_workspace = await api('/api/professional/workspace');
    }
    state.route = nextRoute;
    shell();
    view();
    if (state.route === 'users' && state.data.roles.includes('ADMINISTRADOR')) {
      const directory = await api('/api/admin/data');
      state.adminEntities = directory.entities;
      const selector = document.getElementById('admin-data-entity');
      selector.innerHTML = state.adminEntities.map(item =>
        `<option value="${esc(item.key)}">${esc(item.label)}</option>`
      ).join('');
      await loadAdminRecords(state.adminEntityKey);
    }
  }

  async function showCredential() {
    const modal = document.getElementById('credential-modal');
    const imageTarget = document.getElementById('credential-qr');
    const user = state.data.user;
    const staffCredential = state.data.roles.includes('INSTRUCTOR');
    const membership = (state.data.memberships || []).find(item => item.estado === 'ACTIVA') || (state.data.memberships || [])[0];
    if (!staffCredential && (!membership || membership.estado !== 'ACTIVA')) {
      toast('Necesitas una membresía vigente para generar tu credencial QR.', true);
      return;
    }
    const fullName = `${user.nombres} ${user.apellido_paterno || ''} ${user.apellido_materno === '-' ? '' : user.apellido_materno || ''}`.trim();
    const profileType = state.data.professional_profile?.tipo;
    document.getElementById('credential-modal').querySelector('.membership-card').classList.toggle('staff-card', staffCredential);
    document.getElementById('credential-title').textContent = staffCredential ? 'Credencial del equipo' : 'Credencial de socio';
    document.getElementById('credential-description').textContent = staffCredential
      ? 'Presenta este QR para registrar tu entrada o salida.'
      : 'Presenta el código QR en el acceso de tu sede.';
    document.getElementById('credential-label').textContent = staffCredential ? 'EQUIPO FITLIFE' : 'SOCIO FITLIFE';
    document.getElementById('credential-name').textContent = fullName;
    document.getElementById('credential-plan').textContent = staffCredential
      ? professionalLabels[profileType] || 'Personal FitLife'
      : `${membership.plan} · ${membership.estado}`;
    const benefits = document.getElementById('credential-benefits');
    benefits.textContent = !staffCredential && membership.incluye_estacionamiento
      ? 'Beneficio incluido: estacionamiento (según disponibilidad de cupos en la sede).'
      : '';
    benefits.classList.toggle('hidden', staffCredential || !membership?.incluye_estacionamiento);
    document.getElementById('credential-validity').textContent = staffCredential
      ? 'Acceso de personal · Credencial vigente mientras tu perfil esté activo'
      : membership?.fecha_fin
        ? `Vigente hasta ${dateOnly(membership.fecha_fin)}`
        : 'Tu acceso requiere una membresía vigente.';
    imageTarget.innerHTML = '<span class="spinner"></span>';
    modal.classList.remove('hidden');
    try {
      const image = await api('/api/auth/credential/qr', { method: 'POST' });
      if (state.credentialUrl) URL.revokeObjectURL(state.credentialUrl);
      state.credentialUrl = URL.createObjectURL(image);
      imageTarget.innerHTML = `<img src="${state.credentialUrl}" alt="Código QR personal FitLife">`;
    } catch (error) {
      imageTarget.textContent = error.message;
      toast(error.message, true);
    }
  }

  function phoneDigits(value) {
    let digits = value.replace(/\D/g, '');
    if (digits.length === 11 && digits.startsWith('56')) digits = digits.slice(2);
    return digits.slice(0, 9);
  }

  function validatePhoneField(input) {
    const digits = phoneDigits(input.value);
    const invalid = digits.length > 0 && digits.length !== 9;
    input.setAttribute('aria-invalid', String(invalid));
    input.closest('[data-phone-field]').classList.toggle('phone-invalid', invalid);
    const error = input.parentElement.nextElementSibling;
    error.classList.toggle('hidden', !invalid);
    return !invalid;
  }

  function cleanPersonName(input) {
    const start = input.selectionStart;
    const end = input.selectionEnd;
    const cleaned = [...input.value.normalize('NFC')]
      .filter(character => /\p{L}|\s/u.test(character))
      .join('')
      .replace(/\s+/g, ' ')
      .slice(0, 100);
    if (cleaned !== input.value) {
      input.value = cleaned;
      const position = Math.min(cleaned.length, start ?? cleaned.length);
      input.setSelectionRange(position, Math.min(cleaned.length, end ?? position));
    }
  }

  function blockInvalidPersonNameInput(event) {
    if (typeof event.data === 'string'
      && [...event.data].some(character => !/[\p{L}\p{M}\s]/u.test(character))) {
      event.preventDefault();
    }
  }

  function validatePersonName(input, showEmpty = false) {
    const value = input.value.trim();
    const letters = [...value].filter(character => /\p{L}/u.test(character)).length;
    const required = input.dataset.nameRequired === 'true';
    const error = document.getElementById(input.getAttribute('aria-describedby'));
    const invalid = (required && !value) || (value && letters < 3);
    error.textContent = !value && required && showEmpty
      ? 'Este campo es obligatorio.'
      : value && letters < 3 ? 'Ingresa al menos 3 letras.' : '';
    error.classList.toggle('hidden', !error.textContent);
    input.setAttribute('aria-invalid', String(Boolean(invalid)));
    return !invalid;
  }

  function prepareInstallationPayload(form, payload) {
    for (const fieldName of ['horario_lunes_viernes', 'horario_sabados_dom_festivos']) {
      const [start, end] = [...form.querySelectorAll(`[data-schedule-field="${fieldName}"]`)]
        .map(input => input.value);
      payload[fieldName] = `${start} - ${end}`;
    }
    for (const fieldName of [
      'tiene_lockers', 'tiene_estacionamiento', 'tiene_vestidores', 'tiene_duchas',
    ]) {
      payload[fieldName] = form.elements[fieldName].checked;
    }
    for (const [enabledField, countField] of [
      ['tiene_lockers', 'cantidad_lockers'],
      ['tiene_estacionamiento', 'cupos_estacionamiento'],
      ['tiene_vestidores', 'cantidad_vestidores'],
      ['tiene_duchas', 'cantidad_duchas'],
    ]) {
      payload[countField] = payload[enabledField] ? Number(form.elements[countField].value) : 0;
    }
    payload.planes_ids = [...form.querySelectorAll('input[name="planes_ids"]:checked')]
      .map(input => Number(input.value));
    return payload;
  }

  bindDashboardEvents({
    state, esc, api, toast, refresh, prepareInstallationPayload, confirmTrialRedemption,
    setInstallationCapacityVisibility, stopScanner, showCredential, phoneDigits,
    validatePhoneField, cleanPersonName, blockInvalidPersonNameInput, validatePersonName,
    normalizeLocationPayload, updateCityOther, updateCityOptions, setScheduleRange,
    updatePlanScopeFields, filterPlanSites, updatePlanSiteCityFilter, updateClassResources,
    loadAdminRecords, view, sessionsTable,
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      document.getElementById('credential-modal').classList.add('hidden');
      const imageModal = document.getElementById('class-image-modal');
      if (!imageModal.classList.contains('hidden')) {
        imageModal.classList.add('hidden');
        document.getElementById('class-image-full').removeAttribute('src');
        state.classImageTrigger?.focus();
        state.classImageTrigger = null;
      }
    }
  });

  if (!token) {
    location.replace('/iniciar-sesion/');
    return;
  }

  const urlParams = new URLSearchParams(location.search);
  const paymentResult = urlParams.get('pago');
  const requestedSection = urlParams.get('section');
  const sectionRoutes = {
    membership: 'membership',
    classes: 'classes',
    plans: 'plans',
    reservations: 'reservations',
    gym: 'gym',
    credential: 'home',
  };
  const initialRoute = paymentResult === 'aprobado'
    ? 'membership'
    : paymentResult ? 'plans'
      : sectionRoutes[requestedSection] || 'home';
  refresh(initialRoute).then(() => {
    if (requestedSection === 'credential') showCredential();
    const paymentMessages = {
      aprobado: ['Pago aprobado. Tu membresía ya está activa.', false],
      cancelado: ['Cancelaste el pago. No se realizó ningún cobro.', true],
      rechazado: ['Webpay no aprobó el pago. Puedes intentarlo nuevamente.', true],
      verificacion: ['Estamos verificando el pago. Revisa tu membresía en unos momentos.', true],
      'sin-confirmar': ['No recibimos la confirmación del pago.', true],
    };
    if (paymentMessages[paymentResult]) {
      const [message, isError] = paymentMessages[paymentResult];
      toast(message, isError);
      history.replaceState(null, '', '/panel/');
    }
  }).catch(error => {
    if (error.message.includes('Inicia sesión')) {
      sessionStorage.removeItem('fitlife-token');
      location.replace('/iniciar-sesion/');
    } else {
      content.innerHTML = `<div class="notice notice-error">${esc(error.message)}</div>`;
    }
  });

  window.setInterval(() => {
    if (document.hidden || !state.data || state.route !== 'home'
        || !state.data.roles.some(role => ['ADMINISTRADOR', 'RECEPCIONISTA'].includes(role))) return;
    refresh('home').catch(error => toast(error.message, true));
  }, 30000);
})();
