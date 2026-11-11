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

  const plansContainer = document.getElementById('landing-plans');
  const activitiesContainer = document.getElementById('landing-activities');
  const gymContainer = document.getElementById('landing-gym-locations');
  const gymSearch = document.getElementById('gym-search-input');
  const gymResultsCount = document.getElementById('gym-results-count');
  const gymModal = document.getElementById('public-gym-modal');
  const gymDetails = document.getElementById('public-gym-details');
  let gymLocations = [];
  let gymSessions = [];
  let selectedGymDay = null;
  let focusedGymTrigger = null;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
  const money = value => {
    const amount = Number(value);
    return '$' + (Number.isFinite(amount) ? amount : 0).toLocaleString('es-CL');
  };
  const dateParts = value => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    const options = { timeZone: 'America/Santiago' };
    return {
      weekday: new Intl.DateTimeFormat('es-CL', { ...options, weekday: 'short' }).format(date),
      day: new Intl.DateTimeFormat('es-CL', { ...options, day: '2-digit' }).format(date),
      month: new Intl.DateTimeFormat('es-CL', { ...options, month: 'short' }).format(date),
      time: new Intl.DateTimeFormat('es-CL', { ...options, hour: '2-digit', minute: '2-digit' }).format(date),
      iso: date.toISOString(),
    };
  };
  const retryButton = type => `<button class="button button-light button-small" type="button" data-retry="${type}">Intentar nuevamente</button>`;
  const weekdays = [['LUN', 1], ['MAR', 2], ['MIÉ', 3], ['JUE', 4], ['VIE', 5], ['SÁB', 6], ['DOM', 0]];
  const weekdayInChile = value => {
    const weekday = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Santiago', weekday: 'short',
    }).format(new Date(value));
    return { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 }[weekday];
  };

  async function fetchJSON(url, fallbackMessage) {
    const response = await fetch(url);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || fallbackMessage);
    return data;
  }

  function planBenefits(plan) {
    return [
      plan.incluye_entrenador_personal ? 'Entrenador personal' : '',
      plan.incluye_lockers ? 'Acceso a lockers' : '',
      plan.incluye_estacionamiento ? 'Estacionamiento' : '',
      plan.acceso_todas_sedes ? 'Acceso a todas las sedes' : '',
      plan.es_prueba_gratuita ? 'Prueba gratuita' : '',
      ...(plan.otros_beneficios || '').split('\n').filter(Boolean),
    ].filter(Boolean);
  }

  function gymCard(location) {
    const cover = location.imagen_url || '/static/images/fitlife-gym.jpg';
    const plans = location.plans || [];
    return `<article class="public-gym-card">
      <img class="public-gym-cover" src="${escape(cover)}" alt="Sede FitLife ${escape(location.nombre)}" loading="lazy" onerror="this.onerror=null;this.src='/static/images/fitlife-gym.jpg'">
      <div class="public-gym-card-content">
        <h3>${escape(location.nombre)}</h3>
        <p class="public-gym-address">${escape([location.direccion, [location.ciudad, location.region].filter(Boolean).join(', ')].filter(Boolean).join(' · ') || 'Dirección por confirmar')}</p>
        <button class="public-gym-link" type="button" data-public-gym="${location.instalacion_id}">Ver gimnasio</button>
        <div class="public-gym-plan-prices">${plans.length ? plans.map(plan => `<div><strong>${escape(plan.nombre)}${plan.acceso_todas_sedes ? ' · Todas las sedes' : ''}</strong><span>${plan.es_prueba_gratuita ? 'Gratis' : money(plan.precio_referencia)}</span></div>`).join('') : '<p class="form-hint">Suscripciones por confirmar</p>'}</div>
        <a class="button button-primary public-gym-cta" href="/iniciar-sesion/?crear=1">¡Inscríbete ahora!</a>
      </div>
    </article>`;
  }

  function renderGymLocations() {
    if (!gymLocations.length) {
      gymResultsCount.textContent = 'Sedes disponibles';
      gymContainer.innerHTML = '<div class="home-empty"><span class="empty-symbol" aria-hidden="true">⌖</span><p>Aún no hay sedes publicadas. El equipo FitLife estará cargándolas próximamente.</p></div>';
      return;
    }
    const query = gymSearch.value.trim().toLocaleLowerCase('es-CL');
    const filtered = gymLocations.filter(location =>
      `${location.nombre} ${location.direccion || ''} ${location.ciudad || ''} ${location.region || ''}`
        .toLocaleLowerCase('es-CL').includes(query),
    );
    gymResultsCount.textContent = `${filtered.length} ${filtered.length === 1 ? 'sede encontrada' : 'sedes encontradas'}`;
    gymContainer.innerHTML = filtered.length
      ? filtered.map(gymCard).join('')
      : '<div class="home-empty"><span class="empty-symbol" aria-hidden="true">⌖</span><p>No encontramos sedes con esa búsqueda.</p></div>';
  }

  function renderGymDetails(location) {
    const mapUrl = location.latitud !== null && location.longitud !== null
      ? `https://maps.google.com/?q=${encodeURIComponent(`${location.latitud},${location.longitud}`)}`
      : null;
    const classes = gymSessions.filter(session =>
      Number(session.instalacion_id) === Number(location.instalacion_id)
      && weekdayInChile(session.inicio) === selectedGymDay,
    );
    const characteristics = (location.caracteristicas || '').split('\n').map(item => item.trim()).filter(Boolean);
    gymDetails.innerHTML = `<span class="eyebrow">SEDE FITLIFE</span><h2 id="public-gym-title">${escape(location.nombre)}</h2>
      <div class="gym-public-detail-grid">
        <section><h3>Horario</h3><p><strong>Lun a Vie</strong><span>${escape(location.horario_lunes_viernes || 'Horario por confirmar')}</span></p><p><strong>Sáb a Dom/Feriados</strong><span>${escape(location.horario_sabados_dom_festivos || 'Horario por confirmar')}</span></p></section>
        <section><h3>Dirección</h3><p>${escape(location.direccion || 'Dirección por confirmar')}</p>${location.ciudad || location.region ? `<p>${escape([location.ciudad, location.region].filter(Boolean).join(', '))}</p>` : ''}${mapUrl ? `<a href="${mapUrl}" target="_blank" rel="noopener noreferrer">Ver mapa <span aria-hidden="true">↗</span></a>` : '<span>Mapa por confirmar</span>'}</section>
      </div>
      <section class="gym-public-modal-section"><h3>Áreas</h3><div class="gym-public-chips">${(location.areas || []).length ? location.areas.map(area => `<span>${escape(area)}</span>`).join('') : '<p>Áreas por confirmar.</p>'}</div></section>
      <section class="gym-public-modal-section"><h3>Características de esta sede</h3>${characteristics.length ? `<ul>${characteristics.map(item => `<li>${escape(item)}</li>`).join('')}</ul>` : '<p>Características por confirmar.</p>'}</section>
      <section class="gym-public-modal-section"><h3>Horarios de clases grupales de esta sede</h3><p>Escoge un día</p>
        <div class="gym-public-weekdays" role="group" aria-label="Escoge un día">${weekdays.map(([label, day]) => `<button class="${selectedGymDay === day ? 'active' : ''}" type="button" data-public-gym-day="${day}" aria-pressed="${selectedGymDay === day}">${label}</button>`).join('')}</div>
        ${classes.length ? `<div class="gym-public-classes">${classes.map(session => `<article><div><strong>${escape(session.nombre)}</strong><small>${escape(session.actividad)} · ${escape(session.sala)}</small></div><div><strong>${escape(new Intl.DateTimeFormat('es-CL', { timeZone: 'America/Santiago', hour: '2-digit', minute: '2-digit' }).format(new Date(session.inicio)))}</strong><small>${escape(session.instructor)}</small></div></article>`).join('')}</div>` : '<p>No hay clases grupales programadas para este día.</p>'}
      </section>`;
    gymModal.classList.remove('hidden');
    gymModal.querySelector('[data-close-public-gym]').focus();
  }

  async function loadGymLocations() {
    gymContainer.setAttribute('aria-busy', 'true');
    try {
      const data = await fetchJSON('/api/public/installations', 'No pudimos cargar las sedes.');
      gymLocations = data.installations || [];
      gymSessions = data.sessions || [];
      renderGymLocations();
    } catch (error) {
      gymResultsCount.textContent = 'Sedes disponibles';
      gymContainer.innerHTML = `<div class="home-error"><p>${escape(error.message)}</p>${retryButton('gyms')}</div>`;
    } finally {
      gymContainer.setAttribute('aria-busy', 'false');
    }
  }

  async function loadPlans() {
    plansContainer.setAttribute('aria-busy', 'true');
    plansContainer.innerHTML = '<div class="loading-state"><span class="spinner"></span> Cargando planes…</div>';
    try {
      const { plans } = await fetchJSON('/api/plans', 'No pudimos cargar los planes.');
      if (!plans.length) {
        plansContainer.innerHTML = '<div class="home-empty"><span class="empty-symbol" aria-hidden="true">◇</span><p>Aún no hay planes publicados. Vuelve pronto para conocer las opciones.</p><a class="text-link" href="/iniciar-sesion/?crear=1">Crear una cuenta <span aria-hidden="true">↗</span></a></div>';
        return;
      }
      plansContainer.innerHTML = plans.map((plan, index) => {
        const benefits = planBenefits(plan);
        const duration = Number(plan.duracion_dias);
        return `
        <article class="landing-plan">
          <div class="plan-topline"><span>${plan.es_prueba_gratuita ? 'PRUEBA GRATUITA' : plan.acceso_todas_sedes ? 'MEMBRESÍA GLOBAL' : `FITLIFE / ${String(index + 1).padStart(2, '0')}`}</span><span>${Number.isFinite(duration) ? `${duration} ${duration === 1 ? 'día' : 'días'}` : ''}</span></div>
          <h3>${escape(plan.nombre)}</h3>
          <p>${escape(plan.descripcion || 'Una opción para acompañar tu entrenamiento.')}</p>
          <p><strong>${(plan.sedes || []).length === 1 ? 'Sede' : 'Sedes'}:</strong> ${escape((plan.sedes || []).join(', ') || 'Por confirmar')}</p>
          <div class="landing-price">${plan.es_prueba_gratuita ? 'Gratis' : money(plan.precio_referencia)}<small> / ${Number.isFinite(duration) ? `${duration} ${duration === 1 ? 'día' : 'días'}` : 'vigencia'}</small></div>
          ${benefits.length
            ? `<ul class="plan-benefits">${benefits.map(benefit => `<li>${escape(benefit)}</li>`).join('')}</ul>`
            : '<p class="plan-benefits-empty">Consulta los detalles y condiciones con el equipo FitLife.</p>'}
          ${plan.es_prueba_gratuita
            ? '<p class="plan-benefits-empty">Canje único por socio. No requiere medio de pago ni genera un cobro posterior.</p>'
            : '<p class="plan-benefits-empty">Paga con débito o crédito en Webpay. No se acepta efectivo.</p>'}
          <a class="button button-dark" href="/iniciar-sesion/?continuar=planes">${plan.es_prueba_gratuita ? 'Canjear prueba' : 'Contratar plan'} <span aria-hidden="true">↗</span></a>
        </article>`;
      }).join('');
    } catch (error) {
      plansContainer.innerHTML = `<div class="home-error"><p>${escape(error.message)}</p>${retryButton('plans')}</div>`;
    } finally {
      plansContainer.setAttribute('aria-busy', 'false');
    }
  }

  async function loadActivities() {
    activitiesContainer.setAttribute('aria-busy', 'true');
    activitiesContainer.innerHTML = '<div class="loading-state"><span class="spinner"></span> Cargando próximas actividades…</div>';
    try {
      const { sessions } = await fetchJSON('/api/public/sessions', 'No pudimos cargar las actividades.');
      if (!sessions.length) {
        activitiesContainer.innerHTML = '<div class="home-empty"><span class="empty-symbol" aria-hidden="true">◷</span><p>Por ahora no hay clases próximas publicadas.</p><a class="text-link" href="/iniciar-sesion/?continuar=clases">Revisar el calendario <span aria-hidden="true">↗</span></a></div>';
        return;
      }
      activitiesContainer.innerHTML = sessions.map(session => {
        const date = dateParts(session.inicio);
        const seats = Number(session.cupos_disponibles);
        const hasSeats = Number.isFinite(seats) && seats > 0;
        const image = session.imagen_url
          ? `<img class="activity-card-image" src="${escape(session.imagen_url)}" alt="${escape(`${session.actividad || 'Actividad'}: ${session.nombre}`)}" loading="lazy">`
          : '<div class="activity-card-placeholder" aria-hidden="true"><span>F</span><small>FITLIFE · MUÉVETE A TU MANERA</small></div>';
        const formattedDate = date
          ? `<time datetime="${escape(date.iso)}"><span class="activity-date-day">${escape(date.day)}</span><span class="activity-date-copy">${escape(date.weekday)}<br>${escape(date.month)}</span><span class="activity-time">${escape(date.time)}</span></time>`
          : '<span class="activity-date-invalid">Horario por confirmar</span>';
        const seatLabel = hasSeats
          ? `${seats} ${seats === 1 ? 'cupo disponible' : 'cupos disponibles'}`
          : 'Cupos completos · lista de espera';
        const actionLabel = hasSeats ? 'Acceder para reservar' : 'Acceder a lista de espera';
        return `
        <article class="activity-card">
          <div class="activity-card-media">${image}<span class="activity-seat ${hasSeats ? 'has-seats' : 'waitlist'}">${escape(seatLabel)}</span></div>
          <div class="activity-card-content">
            <span class="activity-category">${escape(session.actividad || 'Actividad FitLife')}</span>
            <h3>${escape(session.nombre || session.actividad)}</h3>
            <div class="activity-card-meta">${formattedDate}<span class="activity-location"><span aria-hidden="true">⌖</span>${escape(session.sala || 'Sede FitLife')}${session.instructor ? `<small>${escape(session.instructor)}</small>` : ''}</span></div>
            <div class="activity-card-footer">
              <strong>${Number(session.precio) > 0 ? money(session.precio) : 'Sin costo adicional'}</strong>
              <a class="button button-light button-small" href="/iniciar-sesion/?continuar=clases">${actionLabel}<span aria-hidden="true">↗</span></a>
            </div>
          </div>
        </article>`;
      }).join('');
    } catch (error) {
      activitiesContainer.innerHTML = `<div class="home-error"><p>${escape(error.message)}</p>${retryButton('activities')}</div>`;
    } finally {
      activitiesContainer.setAttribute('aria-busy', 'false');
    }
  }

  document.addEventListener('click', event => {
    const gymTrigger = event.target.closest('[data-public-gym]');
    if (gymTrigger) {
      const location = gymLocations.find(item => String(item.instalacion_id) === gymTrigger.dataset.publicGym);
      if (!location) return;
      focusedGymTrigger = gymTrigger;
      selectedGymDay = weekdayInChile(new Date());
      gymModal.dataset.installationId = location.instalacion_id;
      renderGymDetails(location);
      return;
    }
    const gymDay = event.target.closest('[data-public-gym-day]');
    if (gymDay) {
      selectedGymDay = Number(gymDay.dataset.publicGymDay);
      const location = gymLocations.find(item => String(item.instalacion_id) === gymModal.dataset.installationId);
      if (location) renderGymDetails(location);
      return;
    }
    if (event.target.closest('[data-close-public-gym]') || event.target === gymModal) {
      gymModal.classList.add('hidden');
      focusedGymTrigger?.focus();
      focusedGymTrigger = null;
      return;
    }
    const retry = event.target.closest('[data-retry]');
    if (!retry) return;
    if (retry.dataset.retry === 'plans') loadPlans();
    if (retry.dataset.retry === 'activities') loadActivities();
    if (retry.dataset.retry === 'gyms') loadGymLocations();
  });

  if (gymSearch) {
    gymSearch.addEventListener('input', renderGymLocations);
    document.getElementById('gym-search-form').addEventListener('submit', event => event.preventDefault());
  }
  gymModal?.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      gymModal.classList.add('hidden');
      focusedGymTrigger?.focus();
      focusedGymTrigger = null;
    }
  });
  if (plansContainer) loadPlans();
  if (activitiesContainer) loadActivities();
  if (gymContainer) loadGymLocations();
  loadPublicAccount();
})();
