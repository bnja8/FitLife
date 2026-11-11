import { createProfessionalViews } from './professional.js';

export function createDashboardViews(context) {
  const {
    token, content, state, esc, money, dateTime, dateOnly, weekdayInChile,
    roleLabels, professionalLabels, badge, locationFieldsHTML, parseScheduleRange,
    updateClassResources, instructorSpecialties,
  } = context;
  const professionalViews = createProfessionalViews({ state, esc, dateOnly, dateTime });

  function heading(title, description, action = '') {
    return `<div class="head-row"><div><h2>${title}</h2><p>${description}</p></div>${action}</div>`;
  }

  function hubCards(items) {
    return `<section class="hub-grid" aria-label="Accesos a módulos">${items.map((item, index) =>
      `<button class="hub-card hub-tone-${index % 8}" type="button" ${item.form ? `data-toggle-form="${item.form}"` : `data-route="${item.route}"`}>
        <span class="hub-card-top"><span class="hub-icon" aria-hidden="true">${item.icon}</span><span class="hub-open" aria-hidden="true">↗</span></span>
        <span class="hub-card-title">${esc(item.title)}</span><span class="hub-card-description">${esc(item.description)}</span>
      </button>`
    ).join('')}</section>`;
  }

  function summaryView() {
    const data = state.data;
    const isAdmin = data.roles.includes('ADMINISTRADOR') || data.roles.includes('RECEPCIONISTA');
    if (isAdmin) {
      const receptionLocation = data.roles.includes('RECEPCIONISTA') && !data.roles.includes('ADMINISTRADOR')
        ? `<div class="notice">${data.user.recepcionista_instalacion
          ? `Tu cuenta de recepción está asignada a ${esc(data.user.recepcionista_instalacion)}. Los puntos de acceso y registros visibles están limitados a esa sede.`
          : 'Tu cuenta de recepción aún no tiene una sede asignada. Solicita a Administración que la configure.'}</div>`
        : '';
      const modules = data.roles.includes('ADMINISTRADOR')
        ? [
          { route: 'classes', title: 'Cursos y clases', description: 'Horarios, cupos y lista de espera', icon: '◷' },
          { route: 'machines', title: 'Recursos', description: 'Máquinas y salas del gimnasio', icon: '▦' },
          { route: 'memberships', title: 'Planes y membresías', description: 'Beneficios y asignaciones pendientes', icon: '◇' },
          { route: 'users', title: 'Usuarios', description: 'Cuentas y perfiles del equipo', icon: '♙' },
          { route: 'reports', title: 'Reportes', description: 'Actividad y datos de FitLife', icon: '▤' },
          { route: 'alerts', title: 'Alertas', description: 'Elementos que requieren atención', icon: '♧' },
        ]
        : [
          { route: 'access', title: 'Control de acceso', description: 'Validar credenciales QR', icon: '⌁' },
          { route: 'alerts', title: 'Accesos recientes', description: 'Revisar actividad del gimnasio', icon: '♧' },
        ];
      const summary = data.summary || {};
      const occupancy = data.occupancy || [];
      const accessPercent = occupancy.length
        ? Math.round(occupancy.reduce((sum, item) => sum + Number(item.porcentaje_ocupacion || 0), 0) / occupancy.length)
        : 0;
      const alerts = [
        ...occupancy.filter(item => Number(item.porcentaje_ocupacion || 0) >= 85)
          .map(item => ({ title: `Aforo alto en ${item.instalacion}`, detail: `${item.porcentaje_ocupacion}% de ocupación`, status: 'Alerta' })),
        ...(data.waitlist || []).slice(0, 2).map(item => ({ title: `${item.socio} está en lista de espera`, detail: `Sesión #${item.sesion_id}`, status: 'En espera' })),
        ...(data.machines || []).filter(item => item.estado !== 'OPERATIVA')
          .map(item => ({ title: `${item.nombre} requiere atención`, detail: item.estado.replaceAll('_', ' '), status: 'Mantención' })),
      ];
      return `${heading(`Hola, ${esc(data.user.nombres)}.`, 'Aquí tienes el estado actual de FitLife y las tareas que requieren atención.', '<span class="live">En vivo</span>')}
        ${receptionLocation}
        <div class="kpis">
          <article class="card kpi"><span class="lbl">Aforo actual</span><strong class="val">${Number(summary.presentes || 0)} <small>personas</small></strong><div class="bar"><i style="width:${Math.min(accessPercent, 100)}%"></i></div><small>${accessPercent}% de la capacidad total</small></article>
          <article class="card kpi"><span class="lbl">Socios activos</span><strong class="val">${Number(summary.socios || 0).toLocaleString('es-CL')}</strong><span class="badge ok">Registrados</span></article>
          <article class="card kpi"><span class="lbl">Clases de hoy</span><strong class="val">${Number(summary.clases_hoy || 0)}</strong><span class="badge info">Programadas / en curso</span></article>
          <article class="card kpi"><span class="lbl">Membresías vencidas</span><strong class="val">${Number(summary.membresias_vencidas || 0)}</strong><span class="badge ${summary.membresias_vencidas ? 'warn' : 'ok'}">Requieren revisión</span></article>
        </div>
        <section class="dashboard-shortcuts" aria-labelledby="dashboard-shortcuts-title"><h3 id="dashboard-shortcuts-title">Accesos rápidos</h3>${hubCards(modules)}</section>
        <div class="two">
          <section class="card"><div class="card-h"><h3>Aforo por sede</h3></div>${occupancy.length ? occupancy.map(item => `<div class="occupancy-row"><div><strong>${esc(item.instalacion)}</strong><small>${item.personas_presentes} / ${item.aforo_maximo} personas</small></div><div class="occupancy-meter"><div class="bar"><i style="width:${Math.min(Number(item.porcentaje_ocupacion || 0), 100)}%"></i></div><small>${Number(item.porcentaje_ocupacion || 0)}%</small></div></div>`).join('') : '<p class="empty">Todavía no hay sedes registradas.</p>'}</section>
          <section class="card"><div class="card-h"><h3>Alertas para revisar</h3><button class="link" data-route="alerts">Ver todas</button></div>${alerts.length ? alerts.slice(0, 5).map(item => `<div class="alert-row"><span class="alert-dot"></span><div><strong>${esc(item.title)}</strong><small>${esc(item.detail)}</small></div>${badge(item.status)}</div>`).join('') : '<p class="empty">Todo está en orden por ahora.</p>'}</section>
        </div>
        <section class="card"><div class="card-h"><h3>Últimos accesos</h3><button class="link" data-route="access">Control de acceso</button></div>${accessTable(data.recent_access || [])}</section>`;
    }

    if (data.roles.includes('INSTRUCTOR')) {
      const upcoming = (data.instructor_sessions || []).filter(item => new Date(item.fin) >= new Date());
      const profile = data.professional_profile;
      const specialty = instructorSpecialties[profile?.tipo];
      const recordsTitle = specialty?.recordsTitle;
      const attendees = data.attendees || [];
      const workspace = data.professional_workspace || {};
      const workspaceHistory = ['evaluations', 'plans', 'sessions', 'progress', 'goals']
        .flatMap(key => workspace[key] || [])
        .sort((left, right) => new Date(right.creado_en || right.registrado_en || right.evaluada_en || right.realizada_en)
          - new Date(left.creado_en || left.registrado_en || left.evaluada_en || left.realizada_en));
      const today = new Date().toDateString();
      const todaySessions = upcoming.filter(item => new Date(item.inicio).toDateString() === today).length;
      const todayRecords = workspaceHistory.filter(item =>
        new Date(item.creado_en || item.registrado_en || item.evaluada_en || item.realizada_en).toDateString() === today,
      ).length;
      const description = specialty?.description || 'Consulta las herramientas de tu perfil profesional.';
      return `${heading(`Hola, ${esc(data.user.nombres)}.`, description, '<span class="live">Tu jornada</span>')}
        ${hubCards(specialty?.cards || [])}
        <div class="kpis">
          <article class="card kpi"><span class="lbl">${profile?.tipo === 'MONITOR' ? 'Clases de hoy' : 'Registros de hoy'}</span><strong class="val">${profile?.tipo === 'MONITOR' ? todaySessions : todayRecords}</strong><span class="badge info">En tu jornada</span></article>
          <article class="card kpi"><span class="lbl">Especialidad</span><strong class="val val-small">${esc(profile?.especialidad || professionalLabels[profile?.tipo] || 'Entrenamiento')}</strong><span class="badge ok">Perfil profesional</span></article>
        </div>
        ${profile?.tipo === 'MONITOR'
          ? `<section class="card"><div class="card-h"><h3>Próximas clases asignadas</h3><button class="link" data-route="sessions">Ver clases e historial</button></div>${sessionsTable(upcoming.slice(0, 8), true)}</section>
             <section class="card"><div class="card-h"><h3>Participantes inscritos</h3><small>${attendees.filter(item => item.estado === 'RESERVADA').length} reservas confirmadas</small><button class="link" data-route="attendance">Revisar asistencia</button></div>${attendees.length ? `<div class="table-wrap"><table><thead><tr><th>Socio</th><th>Clase</th><th>Inicio</th><th>Estado</th></tr></thead><tbody>${attendees.slice(0, 8).map(item => `<tr><td>${esc(item.socio)}</td><td>${esc(item.clase)}</td><td>${dateTime(item.inicio)}</td><td>${badge(item.estado)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Todavía no hay participantes inscritos en tus clases.</div>'}</section>`
          : `<section class="card"><div class="card-h"><h3>${esc(recordsTitle || 'Registros recientes')}</h3><button class="link" data-route="team">Abrir módulo</button></div>${workspaceHistory.length ? `<div class="table-wrap"><table><thead><tr><th>Socio</th><th>Registro</th><th>Fecha</th></tr></thead><tbody>${workspaceHistory.slice(0, 8).map(item => `<tr><td>${esc(item.socio || '—')}</td><td>${esc(item.titulo || item.prueba || item.objetivo || 'Sesión registrada')}</td><td>${dateTime(item.creado_en || item.registrado_en || item.evaluada_en || item.realizada_en)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Todavía no hay registros profesionales.</div>'}</section>
             ${workspace.assigned_members?.length ? '' : '<div class="notice">Administración todavía no ha asignado socios a tu perfil.</div>'}`}`;
    }

    const membership = (data.memberships || []).find(item => ['ACTIVA', 'CONGELADA'].includes(item.estado)) || data.memberships?.[0];
    const reservations = data.reservations || [];
    const upcoming = reservations.filter(item => ['RESERVADA', 'EN_ESPERA'].includes(item.estado) && new Date(item.inicio) >= new Date()).slice(0, 3);
    return `${heading(`Hola, ${esc(data.user.nombres)}.`, 'Qué bueno tenerte de vuelta. Revisa tu membresía y encuentra tu próxima actividad.') }
      <div class="two member-overview">
        <section class="card"><div class="card-h"><h3>Mi membresía</h3>${membership?.estado === 'ACTIVA' ? '<button class="link" data-credential>Ver credencial QR</button>' : ''}</div>${membership ? `<div class="membership-summary"><div><span class="eyebrow">PLAN ACTUAL</span><h3>${esc(membership.plan)}</h3><span>${membership.fecha_inicio && membership.fecha_fin ? `${dateOnly(membership.fecha_inicio)} — ${dateOnly(membership.fecha_fin)}` : 'Pendiente de confirmación de pago'}</span></div>${badge(membership.estado)}</div>` : '<div class="empty">No tienes una membresía registrada. Consulta en recepción para activarla.</div>'}</section>
        <section class="card"><div class="card-h"><h3>Mis próximas clases</h3><button class="link" data-route="reservations">Ver reservas</button></div>${upcoming.length ? upcoming.map(item => `<div class="upcoming-item"><div><strong>${esc(item.nombre)}</strong><small>${dateTime(item.inicio)} · ${esc(item.sala)}</small></div>${badge(item.estado)}</div>`).join('') : '<div class="empty">Todavía no tienes clases reservadas.</div>'}</section>
      </div>
      ${(data.training || []).length ? `<section class="card"><div class="card-h"><h3>Mi progreso y objetivos</h3></div>${data.training.map(item => `<div class="upcoming-item"><div><strong>${esc(item.titulo)}</strong><small>${esc(item.tipo)} · ${esc(item.profesional)}${item.fecha_objetivo ? ` · Meta: ${dateOnly(item.fecha_objetivo)}` : ''}</small>${item.detalle ? `<small>${esc(item.detalle)}</small>` : ''}</div><span class="badge info">${item.progreso}%</span></div>`).join('')}</section>` : ''}
      <section class="card"><div class="card-h"><h3>Encuentra una clase para ti</h3><button class="link" data-route="classes">Ver calendario</button></div>${sessionsTable((data.sessions || []).slice(0, 4), false)}</section>`;
  }

  function sessionsTable(sessions, staff) {
    if (!sessions.length) return `<div class="empty">No hay clases ${staff ? 'registradas' : 'programadas'} para mostrar.</div>`;
    return `<div class="table-wrap"><table><thead><tr><th>Imagen</th><th>Clase</th><th>Fecha y hora</th><th>${staff ? 'Sala' : 'Instructor'}</th><th>Cupos</th>${staff ? '<th>Estado</th>' : '<th></th>'}</tr></thead><tbody>${sessions.map(item => {
      const occupied = Number(item.cupos_ocupados || 0);
      const total = Number(item.cupos_totales || 0);
      const stateAction = staff && ['PROGRAMADA', 'EN_CURSO'].includes(item.estado)
        ? `<button class="link" data-session-status="${item.sesion_id}" data-next-status="${item.estado === 'PROGRAMADA' ? 'EN_CURSO' : 'FINALIZADA'}">${item.estado === 'PROGRAMADA' ? 'Iniciar' : 'Finalizar'}</button>${item.estado === 'PROGRAMADA' ? `<button class="link link-danger" data-session-status="${item.sesion_id}" data-next-status="CANCELADA">Cancelar</button>` : ''}`
        : '';
      const editAction = staff && state.data.roles.includes('ADMINISTRADOR')
        && item.estado === 'PROGRAMADA' && new Date(item.inicio) > new Date()
        ? `<button class="link" data-session-edit="${item.sesion_id}">Editar</button>` : '';
      const attendanceAction = staff && state.data.roles.includes('INSTRUCTOR')
        && ['EN_CURSO', 'FINALIZADA'].includes(item.estado) && new Date(item.inicio) <= new Date()
        ? `<button class="link" data-attendance-session="${item.sesion_id}">Registrar asistencia</button>` : '';
      const image = item.imagen_url
        ? `<button class="class-image-trigger" type="button" data-class-image="${esc(item.imagen_url)}" data-class-title="${esc(item.nombre || item.actividad)}" aria-label="Ampliar imagen de ${esc(item.nombre || item.actividad)}"><img class="class-image-thumb" src="${esc(item.imagen_url)}" alt="" loading="lazy"></button>`
        : '<span class="class-image-placeholder" aria-label="Esta clase no tiene imagen">◷</span>';
      return `<tr><td class="class-image-cell">${image}</td><td><strong>${esc(item.nombre || item.actividad)}</strong><small class="table-sub">${esc(item.actividad || '')}</small>${staff && item.descripcion_sesion ? `<small class="table-sub">${esc(item.descripcion_sesion)}</small>` : ''}${staff && item.intensidad ? `<small class="table-sub">Intensidad ${esc(item.intensidad.toLowerCase())}</small>` : ''}${staff && item.observaciones ? `<small class="table-sub">Observaciones: ${esc(item.observaciones)}</small>` : ''}</td><td>${dateTime(item.inicio)}</td><td>${esc(staff ? item.sala : item.instructor)}</td><td>${total ? `${occupied}/${total}` : '—'}${item.cupos_disponibles !== undefined ? `<small class="table-sub">${item.cupos_disponibles} disponibles</small>` : ''}</td><td>${staff ? `${badge(item.estado)} ${stateAction} ${attendanceAction} ${editAction}` : `<button class="button button-primary button-small" data-reserve="${item.sesion_id}" ${Number(item.cupos_disponibles) <= 0 ? 'data-waitlist="true"' : ''}>${Number(item.cupos_disponibles) <= 0 ? 'Lista de espera' : 'Reservar'}</button>`}</td></tr>`;
    }).join('')}</tbody></table></div>`;
  }

  function classView() {
    return `${heading('Clases y actividades', 'Explora el calendario y reserva el horario que mejor te quede.')}
      <div class="class-filters"><label>Fecha<input id="date-filter" type="date"></label><label>Actividad<select id="activity-filter"><option value="">Todas las actividades</option>${(state.data.activities || []).map(item => `<option value="${item.actividad_id}">${esc(item.nombre)}</option>`).join('')}</select></label><span>Las clases con valor registran el pago como pendiente. La pasarela de pago aún no está configurada.</span></div>
      <div id="class-list">${sessionsTable(state.data.sessions || [], false)}</div>`;
  }

  function monitorClassesView() {
    const data = state.data;
    const sessions = data.instructor_sessions || [];
    const upcoming = sessions.filter(item => new Date(item.fin) >= new Date());
    const history = sessions.filter(item => new Date(item.fin) < new Date());
    const assignedSites = data.installations || [];
    return `${heading('Mis clases', 'Programa tus sesiones grupales, consulta participantes y revisa el historial.', `<button class="button button-dark" data-toggle-form="monitor-class-form" ${assignedSites.length ? '' : 'disabled'}>+ Programar clase</button>`)}
      ${assignedSites.length ? '' : '<div class="notice">Tu perfil aún no tiene una sede asignada. Administración debe asignarte a una sede y sus salas antes de que puedas programar clases.</div>'}
      ${sessions.length ? `<form class="card data-form" id="class-observation-form"><h3>Registrar observaciones de una clase</h3><div class="form-grid"><label>Clase<select name="sesion_id" required><option value="">Selecciona una clase</option>${sessions.map(item => `<option value="${item.sesion_id}">${esc(item.nombre || item.actividad)} · ${dateTime(item.inicio)}</option>`).join('')}</select></label><label class="form-span">Novedades, incidencias o comentarios<textarea name="observaciones" rows="3" maxlength="3000" required></textarea></label></div><button class="button button-dark" type="submit">Guardar observaciones</button></form>` : ''}
      <form class="card data-form workflow-form hidden" id="monitor-class-form">
        <div class="workflow-heading"><div><span class="eyebrow">PLANIFICACIÓN</span><h3>Programar una clase grupal</h3></div><p>Solo puedes programar en sedes y salas asignadas a tu perfil.</p></div>
        <div class="form-grid">
          <label>Actividad<input name="actividad" required maxlength="100" placeholder="Ej. Spinning"></label>
          <label>Nombre de la sesión<input name="nombre" maxlength="120" placeholder="Ej. Spinning resistencia"></label>
          <label class="form-span">Descripción de la sesión<textarea name="descripcion_sesion" rows="2"></textarea></label>
          <label>Intensidad<select name="intensidad" required><option value="BAJA">Baja</option><option value="MODERADA">Moderada</option><option value="ALTA">Alta</option></select></label>
          <label>Sede<select name="instalacion_id" data-class-installation required><option value="">Selecciona una sede asignada</option>${(data.installations || []).map(item => `<option value="${item.instalacion_id}">${esc(item.nombre)}</option>`).join('')}</select></label>
          <input type="hidden" name="instructor_id" value="${data.instructor_id}">
          <label>Sala<select name="sala_id" required disabled><option value="">Primero selecciona una sede</option></select></label>
          <label>Inicio<input name="inicio" type="datetime-local" required></label>
          <label>Término<input name="fin" type="datetime-local" required></label>
          <label>Cupos máximos<input name="cupos_totales" type="number" min="1" required></label>
          <label class="form-span">Observaciones o preparación<textarea name="observaciones" rows="2"></textarea></label>
        </div><div class="form-actions"><button class="button button-primary" type="submit">Guardar clase</button><button class="button button-light" type="button" data-reset-form="monitor-class-form">Cancelar</button></div>
      </form>
      ${upcoming.length ? `<section class="card"><div class="card-h"><h3>Próximas clases</h3><span>${upcoming.length} programadas</span></div>${sessionsTable(upcoming, true)}</section>` : '<section class="card empty">No tienes clases futuras programadas. Usa “Programar clase” para crear una sesión.</section>'}
      ${history.length ? `<section class="card"><div class="card-h"><h3>Historial de clases</h3></div>${sessionsTable(history, true)}</section>` : ''}`;
  }

  function membershipView() {
    const memberships = state.data.memberships || [];
    const activeMembership = memberships.find(item => item.estado === 'ACTIVA');
    return `${heading('Mi suscripción', 'Consulta el estado y la vigencia de tu membresía.', activeMembership ? '<button class="button button-dark" data-credential>Ver credencial QR</button>' : '')}
      ${memberships.length ? `<div class="plans">${memberships.map(item => `<article class="plan ${['ACTIVA', 'CONGELADA'].includes(item.estado) ? 'cur' : ''}"><span class="eyebrow">${esc(item.estado)}</span><h3>${esc(item.plan)}</h3><p class="muted">${esc(item.sede || 'Sede no asignada')} · ${item.fecha_inicio && item.fecha_fin ? `${dateOnly(item.fecha_inicio)} a ${dateOnly(item.fecha_fin)}` : 'Pendiente de confirmación de pago'}</p><strong class="price">${money(item.precio_acordado)}</strong>${badge(item.estado)}${planBenefitLabels(item).length ? `<ul class="benefit-list">${planBenefitLabels(item).map(benefit => `<li>${esc(benefit)}</li>`).join('')}</ul>` : ''}</article>`).join('')}</div>` : '<section class="card empty">No tienes una membresía registrada. Contacta a recepción para conocer los planes disponibles.</section>'}`;
  }

  function customerPlansView() {
    const plans = state.data.plans || [];
    const memberships = state.data.memberships || [];
    const installations = state.data.gym_locations || [];
    const trialRedeemed = memberships.some(item => item.es_prueba_gratuita);
    const globalMembership = memberships.find(item =>
      item.acceso_todas_sedes && ['ACTIVA', 'CONGELADA', 'PENDIENTE'].includes(item.estado),
    );
    const selectedInstallation = installations.find(
      installation => String(installation.instalacion_id) === String(state.membershipInstallationId),
    );
    const locationPlans = selectedInstallation
      ? plans.filter(plan => plan.acceso_todas_sedes || (selectedInstallation.plan_ids || [])
        .some(planId => String(planId) === String(plan.plan_id)))
      : [];
    const currentMembership = globalMembership || (selectedInstallation && memberships.find(item =>
      Number(item.instalacion_id) === Number(selectedInstallation.instalacion_id)
      && ['ACTIVA', 'CONGELADA', 'PENDIENTE'].includes(item.estado)
    ));
    return `${heading('Planes disponibles', 'Elige una membresía para comenzar o continuar tu entrenamiento.')}
      <div class="notice">Elige tu sede principal. Las pruebas gratuitas se canjean una sola vez por socio y no requieren medio de pago. Los planes pagados se contratan por Webpay; FitLife no recopila ni almacena datos de tarjetas. Las membresías globales habilitan sus beneficios en todas las sedes.</div>
      ${installations.length ? `<form id="membership-site-form" class="class-filters">
        <label>Sede de la membresía<select id="membership-installation" name="instalacion_id" required>
          <option value="">Selecciona la sede donde quieres asociar tu membresía</option>
          ${installations.map(installation => `<option value="${installation.instalacion_id}" ${String(installation.instalacion_id) === String(state.membershipInstallationId) ? 'selected' : ''}>${esc(installation.nombre)}</option>`).join('')}
        </select></label>
        <span>Esta será la sede principal de la membresía, incluso si eliges acceso global.</span>
      </form>` : '<section class="card empty">Todavía no hay sedes disponibles.</section>'}
      ${selectedInstallation ? `<section class="card view-panel"><div class="card-h"><div><h3>${esc(selectedInstallation.nombre)}</h3><p class="form-hint">Planes disponibles en esta sede.</p></div></div>
          ${currentMembership ? `<div class="notice">${currentMembership.estado === 'PENDIENTE'
            ? 'Tu membresía está pendiente de confirmación de pago.'
            : currentMembership.acceso_todas_sedes
              ? `Ya tienes una membresía global ${currentMembership.estado.toLowerCase()} con sede principal en ${esc(currentMembership.sede || 'la sede seleccionada')}.`
              : `Ya tienes una membresía ${currentMembership.estado.toLowerCase()} en esta sede.`}</div>` : ''}
          ${locationPlans.length ? `<div class="plans">${locationPlans.map(plan => {
            const benefits = planBenefitLabels(plan);
            const price = Number(plan.precio_referencia);
            return `<article class="plan">
              <span class="eyebrow">${plan.es_prueba_gratuita ? 'Prueba gratuita · ' : ''}${Number(plan.duracion_dias)} días${plan.acceso_todas_sedes ? ' · Todas las sedes' : ''}</span><h3>${esc(plan.nombre)}</h3>
              <p class="muted">${esc(plan.descripcion || 'Una opción para acompañar tu entrenamiento.')}</p>
              <strong class="price">${plan.es_prueba_gratuita ? 'Gratis' : `${money(price)}<small> CLP</small>`}</strong>
              ${benefits.length ? `<ul class="benefit-list">${benefits.map(benefit => `<li>${esc(benefit)}</li>`).join('')}</ul>` : ''}
              ${plan.es_prueba_gratuita
                ? `<button class="button button-dark" type="button" data-redeem-trial="${plan.plan_id}" data-redeem-installation="${selectedInstallation.instalacion_id}" ${currentMembership || trialRedeemed ? 'disabled' : ''}>${trialRedeemed ? 'Prueba ya canjeada' : 'Canjear prueba gratuita'}</button>`
                : `<button class="button button-dark" type="button" data-purchase-plan="${plan.plan_id}" data-purchase-installation="${selectedInstallation.instalacion_id}" ${currentMembership ? 'disabled' : ''}>
                  ${price === 0 ? 'Activar plan gratis' : 'Pagar con Webpay'}
                </button>${price > 0 ? '<small class="form-hint">Webpay permite pagar con débito o crédito. No se acepta efectivo.</small>' : ''}`}
            </article>`;
          }).join('')}</div>` : '<div class="empty">Todavía no hay planes disponibles en esta sede.</div>'}</section>`
        : installations.length ? '<section class="card empty">Selecciona una sede para consultar sus planes y asociar ahí tu membresía.</section>' : ''}`;
  }

  function planBenefitLabels(plan) {
    return [
      plan.incluye_entrenador_personal ? 'Entrenador personal' : '',
      plan.incluye_lockers ? 'Acceso a lockers' : '',
      plan.incluye_estacionamiento ? 'Estacionamiento' : '',
      plan.acceso_todas_sedes ? 'Acceso a todas las sedes' : '',
      plan.es_prueba_gratuita ? 'Prueba gratuita' : '',
      ...(plan.otros_beneficios || '').split('\n').filter(Boolean),
    ].filter(Boolean);
  }

  function reservationsView() {
    const reservations = state.data.reservations || [];
    return `${heading('Mis reservas', 'Tus cupos confirmados y lugares en lista de espera.')}
      <section class="card">${reservations.length ? `<div class="table-wrap"><table><thead><tr><th>Actividad</th><th>Fecha y hora</th><th>Sala</th><th>Estado</th><th></th></tr></thead><tbody>${reservations.map(item => `<tr><td><strong>${esc(item.nombre)}</strong><small class="table-sub">${esc(item.actividad)}</small></td><td>${dateTime(item.inicio)}</td><td>${esc(item.sala)}</td><td>${badge(item.estado)}</td><td>${['RESERVADA', 'EN_ESPERA'].includes(item.estado) && new Date(item.inicio) > new Date() ? `<button class="link link-danger" data-cancel="${item.reserva_id}">Cancelar</button>` : ''}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Aún no tienes reservas. <button class="link" data-route="classes">Encuentra tu próxima clase.</button></div>'}</section>`;
  }

  function adminClassesView() {
    const data = state.data;
    const futureClasses = data.sessions || [];
    const allClasses = data.admin_sessions || futureClasses;
    return `${heading('Cursos y clases', 'Administra actividades, instructores, horarios y cupos.', '<button class="button button-dark" data-toggle-form="class-form">+ Agregar clase</button>')}
      <form class="card data-form workflow-form hidden" id="class-form">
        <div class="workflow-heading"><div><span class="eyebrow">NUEVA ACTIVIDAD</span><h3>Programar una clase</h3></div><p>Completa los datos esenciales; instructor y sala se habilitan al elegir la sede.</p></div>
        <div class="form-grid">
          <fieldset class="form-section form-span"><legend><span>1</span> Información de la clase</legend><div class="form-subgrid">
            <label>Actividad<input name="actividad" required placeholder="Ej. Spinning, Yoga, Fútbol"></label>
            <label>Nombre visible <small class="field-optional">Opcional</small><input name="nombre" placeholder="Ej. Spinning 45 min"></label>
            <label>Precio (CLP) <small class="field-optional">Gratis por defecto</small><input name="precio" type="number" min="0" step="500" value="0"></label>
          </div></fieldset>
          <fieldset class="form-section form-span"><legend><span>2</span> Sede y equipo</legend><div class="form-subgrid">
            <label>Sede<select name="instalacion_id" data-class-installation required><option value="">Selecciona una sede</option>${(data.installations || []).map(item => `<option value="${item.instalacion_id}">${esc(item.nombre)}</option>`).join('')}</select></label>
            <label>Instructor<select name="instructor_id" data-class-instructor required disabled><option value="">Primero selecciona una sede</option></select></label>
            <label>Sala<select name="sala_id" data-class-room required disabled><option value="">Primero selecciona una sede</option></select></label>
          </div></fieldset>
          <fieldset class="form-section form-span"><legend><span>3</span> Horario y cupos</legend><div class="form-subgrid">
            <label>Inicio<input name="inicio" type="datetime-local" required></label>
            <label>Término<input name="fin" type="datetime-local" required></label>
            <label>Cupos máximos<input name="cupos_totales" type="number" min="1" required placeholder="Ej. 20"></label>
          </div></fieldset>
          <label class="form-span upload-field">Imagen de la clase <small class="field-optional">Opcional · JPG, PNG o WEBP · máximo 5 MB</small><input id="class-image" name="imagen" type="file" accept="image/jpeg,image/png,image/webp"></label>
          <div class="class-image-preview form-span hidden" id="class-image-preview"><img id="class-image-preview-img" alt="Vista previa de la imagen de clase"><span id="class-image-preview-label"></span></div>
        </div><div class="form-actions"><button class="button button-primary" type="submit">Guardar clase</button><button class="button button-light" type="button" data-reset-form="class-form">Cancelar</button></div>
      </form>
      <div class="stats overview-stats" aria-label="Resumen de próximas clases"><div class="stat"><strong>${futureClasses.length}</strong>Próximas clases</div><div class="stat"><strong>${futureClasses.filter(item => Number(item.cupos_disponibles) === 0).length}</strong>Sin cupos</div><div class="stat"><strong>${futureClasses.reduce((sum, item) => sum + Number(item.cupos_ocupados || 0), 0)}</strong>Reservas próximas</div></div>
      <section class="card view-panel"><div class="card-h"><div><h3>Clases y cursos registrados</h3><p class="form-hint">Incluye clases pasadas y todos los estados registrados.</p></div></div>${sessionsTable(allClasses, true)}</section>
      ${(data.waitlist || []).length ? `<section class="card"><div class="card-h"><h3>Lista de espera</h3></div><div class="table-wrap"><table><thead><tr><th>Socio</th><th>Clase</th><th>Posición</th><th>Fecha</th></tr></thead><tbody>${data.waitlist.map(item => `<tr><td>${esc(item.socio)}</td><td>#${item.sesion_id}</td><td>${item.posicion_espera}</td><td>${dateTime(item.creada_en)}</td></tr>`).join('')}</tbody></table></div></section>` : ''}`;
  }

  function machinesView() {
    const machines = state.data.machines || [];
    const rooms = state.data.rooms || [];
    const installations = state.data.installations || [];
    return `${heading('Recursos', 'Administra equipos y salas disponibles en el gimnasio.')}
      ${hubCards([
        { route: 'installations', title: 'Sedes registradas', description: `${installations.length} sedes · administra máquinas y salas dentro de cada sede`, icon: '⌖' },
      ])}
    `;
  }

  function machinesHubView() {
    const machines = state.data.machines || [];
    return `${heading('Máquinas', 'Consulta y administra los equipos del gimnasio.', '<button class="button button-dark" data-toggle-form="machine-form">+ Agregar máquina</button>')}
      <form class="card data-form hidden" id="machine-form"><h3>Agregar máquina</h3><div class="form-grid"><label>Nombre<input name="nombre" required placeholder="Ej. Cinta de correr #4"></label><label>Categoría<input name="categoria" required placeholder="Cardio, fuerza…"></label><label class="form-span">Observación<input name="observacion" placeholder="Detalle opcional"></label></div><div class="form-actions"><button class="button button-primary" type="submit">Guardar máquina</button><button class="button button-light" type="button" data-reset-form="machine-form">Cancelar</button></div></form>
      <section class="card"><div class="card-h"><h3>Máquinas</h3></div>${machines.length ? `<div class="table-wrap"><table><thead><tr><th>Máquina</th><th>Categoría</th><th>Observación</th><th>Estado</th></tr></thead><tbody>${machines.map(item => `<tr><td><strong>${esc(item.nombre)}</strong></td><td>${esc(item.categoria)}</td><td>${esc(item.observacion || '—')}</td><td><select class="inline-select" data-machine="${item.maquina_id}">${[['OPERATIVA', 'Operativa'], ['MANTENCION', 'Mantención'], ['FUERA_SERVICIO', 'Fuera de servicio']].map(([value, label]) => `<option value="${value}" ${item.estado === value ? 'selected' : ''}>${label}</option>`).join('')}</select></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Aún no hay máquinas registradas.</div>'}</section>`;
  }

  function roomsHubView() {
    const rooms = state.data.rooms || [];
    const installations = state.data.installations || [];
    return `${heading('Salas', 'Administra las salas y su capacidad por sede.', '<button class="button button-dark" data-toggle-form="room-form">+ Agregar sala</button>')}
      <form class="card data-form hidden" id="room-form"><h3>Agregar sala</h3><div class="form-grid"><label>Nombre de la sala<input name="nombre" maxlength="100" required placeholder="Ej. Sala multiuso"></label><label>Sede<select name="instalacion_id" required ${installations.length ? '' : 'disabled'}><option value="">Selecciona una sede</option>${installations.map(item => `<option value="${item.instalacion_id}">${esc(item.nombre)}</option>`).join('')}</select></label><label>Capacidad máxima<input name="capacidad" type="number" min="1" required placeholder="Ej. 25"></label></div>${installations.length ? '' : '<p class="notice">Primero crea una sede para poder asociar la sala.</p>'}<div class="form-actions"><button class="button button-primary" type="submit" ${installations.length ? '' : 'disabled'}>Guardar sala</button><button class="button button-light" type="button" data-reset-form="room-form">Cancelar</button></div></form>
      <section class="card"><div class="card-h"><h3>Salas registradas</h3></div>${rooms.length ? `<div class="table-wrap"><table><thead><tr><th>Sala</th><th>Sede</th><th>Capacidad</th></tr></thead><tbody>${rooms.map(item => `<tr><td><strong>${esc(item.nombre)}</strong></td><td>${esc(item.instalacion)}</td><td>${Number(item.capacidad)} personas</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Aún no hay salas registradas.</div>'}</section>`;
  }

  function gymView() {
    const installations = state.data.gym_locations || [];
    const activeMembership = (state.data.memberships || []).find(item => item.estado === 'ACTIVA');
    const homeInstallationId = activeMembership?.instalacion_id;
    const memberLocations = state.data.roles?.includes('SOCIO') && activeMembership
      ? activeMembership.acceso_todas_sedes
        ? installations
        : installations.filter(item => Number(item.instalacion_id) === Number(homeInstallationId))
      : installations;
    const globalAccess = Boolean(activeMembership?.acceso_todas_sedes);
    return `${heading('Tu gimnasio', 'Conoce las sedes disponibles y encuentra la que mejor se acomoda a tu rutina.')}
      ${activeMembership ? `<div class="notice">${globalAccess
        ? `Tu sede principal es ${esc(activeMembership.sede || 'la sede de tu membresía')}. Tu membresía también habilita sus beneficios en todas las sedes activas.`
        : `Esta es la sede asociada a tu membresía activa: ${esc(activeMembership.sede || 'sede no asignada')}.`}</div>` : ''}
      ${memberLocations.length ? `<div class="gym-location-list">${memberLocations.map(installation => `
        <article class="gym-location-card">
          <div class="gym-location-mark" aria-hidden="true">F</div>
          <div class="gym-location-copy"><span class="eyebrow">${Number(installation.instalacion_id) === Number(homeInstallationId) ? 'SEDE PRINCIPAL' : globalAccess ? 'ACCESO GLOBAL' : 'SEDE'}</span><h3>${esc(installation.nombre)}</h3><p>${esc([installation.direccion, [installation.ciudad, installation.region].filter(Boolean).join(', ')].filter(Boolean).join(' · ') || 'Dirección por confirmar')}</p>
            ${!installation.direccion || !installation.horario_lunes_viernes || !installation.horario_sabados_dom_festivos || installation.latitud === null || installation.longitud === null
              ? '<span class="form-hint">Algunos datos de esta sede están por confirmar.</span>' : ''}
            <div class="gym-plan-list" aria-label="Suscripciones disponibles"><span class="gym-plans-label">Suscripciones</span>${(installation.planes || []).length ? installation.planes.map(plan => `<span class="pill">${esc(plan)}</span>`).join('') : '<span class="form-hint">Por confirmar</span>'}</div>
          </div>
          <button class="button button-dark" type="button" data-route="gym-detail" data-installation-id="${installation.instalacion_id}">Ver sede <span aria-hidden="true">↗</span></button>
        </article>`).join('')}</div>` : '<section class="card"><div class="empty">Todavía no hay sedes disponibles. Vuelve a revisar más adelante.</div></section>'}`;
  }

  function gymDetailView() {
    const installation = (state.data.gym_locations || []).find(
      item => String(item.instalacion_id) === String(state.selectedInstallationId),
    );
    if (!installation) {
      return `${heading('Sede', 'No encontramos la sede solicitada.', '<button class="button button-light button-small" data-route="gym">Volver a Tu gimnasio</button>')}`;
    }
    if (state.selectedGymWeekday === null) state.selectedGymWeekday = weekdayInChile(new Date());
    const hasCoordinates = installation.latitud !== null && installation.latitud !== ''
      && installation.longitud !== null && installation.longitud !== '';
    const mapUrl = hasCoordinates
      ? (installation.mapa_url || `https://maps.google.com/?q=${encodeURIComponent(`${installation.latitud},${installation.longitud}`)}`)
      : null;
    const weekdays = [['LUN', 1], ['MAR', 2], ['MIÉ', 3], ['JUE', 4], ['VIE', 5], ['SÁB', 6], ['DOM', 0]];
    const groupClasses = (state.data.gym_sessions || []).filter(session =>
      Number(session.instalacion_id) === Number(installation.instalacion_id)
      && weekdayInChile(session.inicio) === state.selectedGymWeekday,
    );
    const characteristics = (installation.caracteristicas || '').split('\n').map(item => item.trim()).filter(Boolean);
    return `${heading('Sede', esc(installation.nombre), '<button class="button button-light button-small" data-route="gym">← Volver a Tu gimnasio</button>')}
      <div class="gym-detail-grid">
        <section class="card gym-detail-card"><span class="eyebrow">HORARIO</span>
          <div class="gym-hours-row"><strong>Lun a Vie</strong><span>${esc(installation.horario_lunes_viernes || 'Horario por confirmar')}</span></div>
          <div class="gym-hours-row"><strong>Sáb a Dom/Feriados</strong><span>${esc(installation.horario_sabados_dom_festivos || 'Horario por confirmar')}</span></div>
        </section>
        <section class="card gym-detail-card"><span class="eyebrow">DIRECCIÓN</span>
          <p class="gym-address">${esc(installation.direccion || 'Dirección por confirmar')}</p>
          ${installation.ciudad || installation.region ? `<p>${esc([installation.ciudad, installation.region].filter(Boolean).join(', '))}</p>` : ''}
          ${mapUrl ? `<a class="button button-dark" href="${mapUrl}" target="_blank" rel="noopener noreferrer">Ver mapa <span aria-hidden="true">↗</span></a>` : '<p class="form-hint">El mapa estará disponible cuando se configuren las coordenadas de la sede.</p>'}
        </section>
      </div>
      <section class="card gym-section-card"><div class="card-h"><h3>Áreas</h3></div>${(installation.areas || []).length ? `<div class="gym-pill-list">${installation.areas.map(area => `<span class="pill">${esc(area)}</span>`).join('')}</div>` : '<p class="empty">Las áreas de esta sede se informarán próximamente.</p>'}</section>
      <section class="card gym-section-card"><div class="card-h"><h3>Características de esta sede</h3></div>${characteristics.length ? `<ul class="gym-feature-list">${characteristics.map(item => `<li>${esc(item)}</li>`).join('')}</ul>` : '<p class="empty">Las características de esta sede se informarán próximamente.</p>'}</section>
      <section class="card gym-section-card"><div class="card-h"><div><h3>Horarios de clases grupales de esta sede</h3><p class="form-hint">Escoge un día para revisar las próximas clases.</p></div></div>
        <div class="gym-weekday-tabs" role="group" aria-label="Escoge un día">${weekdays.map(([label, day]) => `<button class="gym-weekday-tab ${state.selectedGymWeekday === day ? 'active' : ''}" type="button" data-gym-day="${day}" aria-pressed="${state.selectedGymWeekday === day}">${label}</button>`).join('')}</div>
        ${groupClasses.length ? `<div class="gym-class-list">${groupClasses.map(session => `<article class="gym-class-row"><div><strong>${esc(session.nombre)}</strong><small>${esc(session.actividad)} · ${esc(session.sala)}</small></div><div class="gym-class-meta"><strong>${dateTime(session.inicio)}</strong><small>${esc(session.instructor)}</small></div></article>`).join('')}</div>` : '<p class="empty">No hay clases grupales programadas para este día.</p>'}
      </section>`;
  }

  function installationsView() {
    const installations = state.data.installations || [];
    return `${heading('Sedes registradas', 'Administra cada sede, su aforo, lockers y estacionamiento.', '<button class="button button-dark" data-toggle-form="installation-form">+ Agregar sede</button>')}
      <form class="card data-form workflow-form hidden" id="installation-form">
        <div class="workflow-heading"><div><span class="eyebrow">NUEVA UBICACIÓN</span><h3>Agregar sede</h3></div><p>Registra la información principal y selecciona las suscripciones y servicios disponibles.</p></div>
        <input type="hidden" name="imagen_url">
        <input type="hidden" name="caracteristicas">
        <div class="form-grid">
          <fieldset class="form-section form-span"><legend><span>1</span> Datos de la sede</legend><div class="form-subgrid">
            <label>Nombre de la sede<input name="nombre" maxlength="100" required placeholder="Ej. FitLife Centro"></label>
            <label>Dirección<input name="direccion" maxlength="200" required placeholder="Calle y número"></label>
            ${locationFieldsHTML(state.data.location_options)}
            <label>Aforo máximo<input name="aforo_maximo" type="number" min="1" required placeholder="Ej. 200"></label>
          </div></fieldset>
          <fieldset class="form-section form-span"><legend><span>2</span> Horarios y ubicación</legend><div class="form-subgrid">
            <div class="schedule-field"><span class="schedule-field-title">Horario · Lun a Vie</span><input type="hidden" name="horario_lunes_viernes"><div class="schedule-range">
              <label>Desde<input type="time" data-schedule-field="horario_lunes_viernes" data-schedule-part="start" step="60" aria-label="Horario de lunes a viernes, desde" required></label>
              <span aria-hidden="true">a</span>
              <label>Hasta<input type="time" data-schedule-field="horario_lunes_viernes" data-schedule-part="end" step="60" aria-label="Horario de lunes a viernes, hasta" required></label>
            </div></div>
            <div class="schedule-field"><span class="schedule-field-title">Horario · Sáb a Dom/Feriados</span><input type="hidden" name="horario_sabados_dom_festivos"><div class="schedule-range">
              <label>Desde<input type="time" data-schedule-field="horario_sabados_dom_festivos" data-schedule-part="start" step="60" aria-label="Horario de sábados, domingos y feriados, desde" required></label>
              <span aria-hidden="true">a</span>
              <label>Hasta<input type="time" data-schedule-field="horario_sabados_dom_festivos" data-schedule-part="end" step="60" aria-label="Horario de sábados, domingos y feriados, hasta" required></label>
            </div></div>
            <label class="form-span">Ubicación en Google Maps<input name="mapa_url" type="url" required maxlength="2000" placeholder="https://maps.app.goo.gl/..." aria-describedby="installation-map-hint"><small class="form-hint" id="installation-map-hint">Comparte la ubicación desde Google Maps y pega el enlace.</small></label>
          </div></fieldset>
          <fieldset class="form-section form-span"><legend><span>3</span> Suscripciones y servicios</legend><div class="form-subgrid">
            <div class="form-span gym-plan-select"><strong>Suscripciones disponibles en esta sede</strong>${(state.data.plans || []).some(plan => !plan.acceso_todas_sedes) ? state.data.plans.filter(plan => !plan.acceso_todas_sedes).map(plan => `<label class="form-check"><input type="checkbox" name="planes_ids" value="${plan.plan_id}"> ${esc(plan.nombre)}</label>`).join('') : '<p class="form-hint">Las membresías globales aparecen automáticamente; crea un plan local para asignarlo específicamente a esta sede.</p>'}</div>
            <div class="form-check-group"><label class="form-check"><input name="tiene_lockers" id="installation-has-lockers" type="checkbox"> La sede cuenta con lockers</label>
            <label class="hidden">Cantidad de lockers<input name="cantidad_lockers" id="installation-locker-count" type="number" min="1" value="0" disabled></label></div>
            <div class="form-check-group"><label class="form-check"><input name="tiene_estacionamiento" id="installation-has-parking" type="checkbox"> La sede cuenta con estacionamiento</label>
            <label class="hidden">Cupos máximos de vehículos<input name="cupos_estacionamiento" id="installation-parking-capacity" type="number" min="1" value="0" disabled></label></div>
            <div class="form-check-group"><label class="form-check"><input name="tiene_vestidores" id="installation-has-dressing-rooms" type="checkbox"> La sede cuenta con vestidores</label>
            <label class="hidden">Vestidores máximos<input name="cantidad_vestidores" id="installation-dressing-room-capacity" type="number" min="1" value="0" disabled></label></div>
            <div class="form-check-group"><label class="form-check"><input name="tiene_duchas" id="installation-has-showers" type="checkbox"> La sede cuenta con duchas</label>
            <label class="hidden">Duchas máximas<input name="cantidad_duchas" id="installation-shower-capacity" type="number" min="1" value="0" disabled></label></div>
          </div></fieldset>
        </div><div class="form-actions"><button class="button button-primary" type="submit">Guardar sede</button><button class="button button-light" type="button" data-reset-form="installation-form">Cancelar</button></div>
      </form>
      <div class="stats overview-stats" aria-label="Resumen de sedes"><div class="stat"><strong>${installations.length}</strong>Sedes activas</div><div class="stat"><strong>${installations.reduce((total, item) => total + Number(item.aforo_maximo || 0), 0).toLocaleString('es-CL')}</strong>Aforo total</div><div class="stat"><strong>${installations.reduce((total, item) => total + Number(item.cantidad_lockers || 0), 0).toLocaleString('es-CL')}</strong>Lockers</div><div class="stat"><strong>${installations.reduce((total, item) => total + Number(item.cupos_estacionamiento || 0), 0).toLocaleString('es-CL')}</strong>Cupos de estacionamiento</div></div>
      <section class="card view-panel"><div class="card-h"><div><h3>Sedes registradas</h3><p class="form-hint">Selecciona una sede para administrar su personal, máquinas y salas.</p></div></div>${installations.length ? `<div class="table-wrap"><table><thead><tr><th>Sede</th><th>Dirección</th><th>Ciudad / región</th><th>Aforo máximo</th><th>Acciones</th></tr></thead><tbody>${installations.map(item => `<tr><td><strong>${esc(item.nombre)}</strong></td><td>${esc(item.direccion || '—')}</td><td>${esc([item.ciudad, item.region].filter(Boolean).join(', ') || '—')}</td><td>${Number(item.aforo_maximo).toLocaleString('es-CL')} personas</td><td><div class="table-actions"><button class="button button-dark button-small" type="button" data-installation-manage="${item.instalacion_id}">Administrar sede</button><button class="link" type="button" data-installation-edit="${item.instalacion_id}">Editar datos</button></div></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Aún no hay sedes registradas. Usa “Agregar sede” para crear la primera.</div>'}</section>`;
  }

  function installationAdminView() {
    const installation = (state.data.installations || []).find(
      item => String(item.instalacion_id) === String(state.selectedAdminInstallationId),
    );
    if (!installation) {
      return `${heading('Sede', 'No encontramos la sede solicitada.', '<button class="button button-light button-small" data-route="installations">Volver a Sedes</button>')}`;
    }
    const installationId = Number(installation.instalacion_id);
    const machines = (state.data.machines || []).filter(item => Number(item.instalacion_id) === installationId);
    const rooms = (state.data.rooms || []).filter(item => Number(item.instalacion_id) === installationId);
    const accessPoints = (state.data.admin_access_points || []).filter(
      item => Number(item.instalacion_id) === installationId,
    );
    const weekdayHours = parseScheduleRange(installation.horario_lunes_viernes);
    const weekendHours = parseScheduleRange(installation.horario_sabados_dom_festivos);
    const selectedPlans = new Set((installation.plan_ids || []).map(String));
    const mapUrl = installation.mapa_url
      || (installation.latitud !== null && installation.longitud !== null
        ? `https://maps.google.com/?q=${installation.latitud},${installation.longitud}`
        : '');
    const assigned = new Set((installation.instructor_ids || []).map(String));
    const professionals = state.data.instructors || [];
    return `${heading(esc(installation.nombre), `${esc([installation.direccion, installation.ciudad, installation.region].filter(Boolean).join(' · '))}`, '<button class="button button-light button-small" data-route="installations">← Volver a Sedes</button>')}
      <div class="stats overview-stats" aria-label="Resumen de recursos de la sede"><div class="stat"><strong>${professionals.filter(person => assigned.has(String(person.instructor_id))).length}</strong>Profesionales asignados</div><div class="stat"><strong>${machines.length}</strong>Máquinas</div><div class="stat"><strong>${rooms.length}</strong>Salas</div></div>
      <form class="card data-form workflow-form" id="installation-admin-settings-form">
        <div class="workflow-heading"><div><span class="eyebrow">CONFIGURACIÓN</span><h3>Datos y servicios de la sede</h3></div><p>Edita los horarios, la ubicación, las suscripciones y los servicios que ofrece esta sede.</p></div>
        <input type="hidden" name="nombre" value="${esc(installation.nombre)}">
        <input type="hidden" name="direccion" value="${esc(installation.direccion || '')}">
        <input type="hidden" name="region" value="${esc(installation.region || '')}">
        <input type="hidden" name="ciudad" value="${esc(installation.ciudad || '')}">
        <input type="hidden" name="aforo_maximo" value="${Number(installation.aforo_maximo || 1)}">
        <input type="hidden" name="caracteristicas" value="${esc(installation.caracteristicas || '')}">
        <input type="hidden" name="imagen_url" value="${esc(installation.imagen_url || '')}">
        <div class="form-grid">
          <fieldset class="form-section form-span"><legend><span>1</span> Horarios y ubicación</legend><div class="form-subgrid">
            <div class="schedule-field"><span class="schedule-field-title">Horario · Lun a Vie</span><input type="hidden" name="horario_lunes_viernes"><div class="schedule-range">
              <label>Desde<input type="time" data-schedule-field="horario_lunes_viernes" data-schedule-part="start" step="60" aria-label="Horario de lunes a viernes, desde" value="${weekdayHours[0]}" required></label>
              <span aria-hidden="true">a</span>
              <label>Hasta<input type="time" data-schedule-field="horario_lunes_viernes" data-schedule-part="end" step="60" aria-label="Horario de lunes a viernes, hasta" value="${weekdayHours[1]}" required></label>
            </div></div>
            <div class="schedule-field"><span class="schedule-field-title">Horario · Sáb a Dom/Feriados</span><input type="hidden" name="horario_sabados_dom_festivos"><div class="schedule-range">
              <label>Desde<input type="time" data-schedule-field="horario_sabados_dom_festivos" data-schedule-part="start" step="60" aria-label="Horario de sábados, domingos y feriados, desde" value="${weekendHours[0]}" required></label>
              <span aria-hidden="true">a</span>
              <label>Hasta<input type="time" data-schedule-field="horario_sabados_dom_festivos" data-schedule-part="end" step="60" aria-label="Horario de sábados, domingos y feriados, hasta" value="${weekendHours[1]}" required></label>
            </div></div>
            <label class="form-span">Ubicación en Google Maps<input name="mapa_url" type="url" required maxlength="2000" placeholder="https://maps.app.goo.gl/..." value="${esc(mapUrl)}" aria-describedby="installation-admin-map-hint"><small class="form-hint" id="installation-admin-map-hint">Comparte la ubicación desde Google Maps y pega el enlace.</small></label>
          </div></fieldset>
          <fieldset class="form-section form-span"><legend><span>2</span> Suscripciones y servicios</legend><div class="form-subgrid">
            <div class="form-span gym-plan-select"><strong>Suscripciones disponibles en esta sede</strong>${(state.data.plans || []).some(plan => !plan.acceso_todas_sedes) ? state.data.plans.filter(plan => !plan.acceso_todas_sedes).map(plan => `<label class="form-check"><input type="checkbox" name="planes_ids" value="${plan.plan_id}" ${selectedPlans.has(String(plan.plan_id)) ? 'checked' : ''}> ${esc(plan.nombre)}</label>`).join('') : '<p class="form-hint">Las membresías globales aparecen automáticamente; crea un plan local para asignarlo específicamente a esta sede.</p>'}</div>
            <div class="form-check-group"><label class="form-check"><input name="tiene_lockers" id="installation-admin-has-lockers" type="checkbox" ${installation.tiene_lockers ? 'checked' : ''} data-capacity-target="installation-admin-locker-count"> La sede cuenta con lockers</label>
            <label class="${installation.tiene_lockers ? '' : 'hidden'}">Cantidad de lockers<input name="cantidad_lockers" id="installation-admin-locker-count" type="number" min="1" value="${Number(installation.cantidad_lockers || 0)}" ${installation.tiene_lockers ? 'required' : 'disabled'}></label></div>
            <div class="form-check-group"><label class="form-check"><input name="tiene_estacionamiento" id="installation-admin-has-parking" type="checkbox" ${installation.tiene_estacionamiento ? 'checked' : ''} data-capacity-target="installation-admin-parking-capacity"> La sede cuenta con estacionamiento</label>
            <label class="${installation.tiene_estacionamiento ? '' : 'hidden'}">Cupos máximos de vehículos<input name="cupos_estacionamiento" id="installation-admin-parking-capacity" type="number" min="1" value="${Number(installation.cupos_estacionamiento || 0)}" ${installation.tiene_estacionamiento ? 'required' : 'disabled'}></label></div>
            <div class="form-check-group"><label class="form-check"><input name="tiene_vestidores" id="installation-admin-has-dressing-rooms" type="checkbox" ${installation.tiene_vestidores ? 'checked' : ''} data-capacity-target="installation-admin-dressing-room-capacity"> La sede cuenta con vestidores</label>
            <label class="${installation.tiene_vestidores ? '' : 'hidden'}">Vestidores máximos<input name="cantidad_vestidores" id="installation-admin-dressing-room-capacity" type="number" min="1" value="${Number(installation.cantidad_vestidores || 0)}" ${installation.tiene_vestidores ? 'required' : 'disabled'}></label></div>
            <div class="form-check-group"><label class="form-check"><input name="tiene_duchas" id="installation-admin-has-showers" type="checkbox" ${installation.tiene_duchas ? 'checked' : ''} data-capacity-target="installation-admin-shower-capacity"> La sede cuenta con duchas</label>
            <label class="${installation.tiene_duchas ? '' : 'hidden'}">Duchas máximas<input name="cantidad_duchas" id="installation-admin-shower-capacity" type="number" min="1" value="${Number(installation.cantidad_duchas || 0)}" ${installation.tiene_duchas ? 'required' : 'disabled'}></label></div>
          </div></fieldset>
        </div><div class="form-actions"><button class="button button-primary" type="submit">Guardar datos de la sede</button></div>
      </form>
      <section class="card view-panel"><div class="card-h"><div><h3>Profesionales de esta sede</h3><p class="form-hint">Solo el personal asignado aquí estará disponible al programar clases.</p></div></div>
        ${professionals.length ? `<form class="data-form" id="installation-staff-form"><div class="form-grid">${professionals.map(person => `<label class="form-check"><input type="checkbox" name="instructor_ids" value="${person.instructor_id}" ${assigned.has(String(person.instructor_id)) ? 'checked' : ''}> ${esc(person.nombre)} · ${esc(professionalLabels[person.tipo] || person.tipo)}${person.especialidad ? ` · ${esc(person.especialidad)}` : ''}</label>`).join('')}</div><div class="form-actions"><button class="button button-primary" type="submit">Guardar profesionales</button></div></form>` : '<p class="empty">Crea primero cuentas profesionales desde Usuarios.</p>'}
      </section>
      <section class="card view-panel"><div class="card-h"><div><h3>Puntos de acceso</h3><p class="form-hint">Define los accesos disponibles para validar credenciales en ${esc(installation.nombre)}.</p></div><button class="button button-dark button-small" type="button" data-toggle-form="installation-access-point-form">+ Agregar punto de acceso</button></div>
        <form class="data-form hidden" id="installation-access-point-form"><input type="hidden" name="instalacion_id" value="${installationId}"><div class="form-grid"><label>Nombre del punto<input name="nombre" required maxlength="100" placeholder="Ej. Entrada principal"></label><label>Movimiento permitido<select name="tipo" required><option value="BIDIRECCIONAL">Entrada y salida</option><option value="ENTRADA">Solo entrada</option><option value="SALIDA">Solo salida</option></select></label><label>Uso del punto<select name="uso" required><option value="GENERAL">Acceso general</option>${installation.tiene_estacionamiento ? '<option value="ESTACIONAMIENTO">Estacionamiento</option>' : ''}</select>${installation.tiene_estacionamiento ? '' : '<small class="form-hint">El acceso de estacionamiento estará disponible cuando la sede tenga estacionamiento habilitado.</small>'}</label></div><div class="form-actions"><button class="button button-primary" type="submit">Guardar punto de acceso</button><button class="button button-light" type="button" data-reset-form="installation-access-point-form">Cancelar</button></div></form>
        ${accessPoints.length ? `<div class="table-wrap"><table><thead><tr><th>Punto de acceso</th><th>Uso</th><th>Movimiento permitido</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>${accessPoints.map(point => `<tr><td><strong>${esc(point.nombre)}</strong></td><td>${point.uso === 'ESTACIONAMIENTO' ? 'Estacionamiento' : 'General'}${point.uso === 'ESTACIONAMIENTO' && !point.tiene_estacionamiento ? '<small class="table-sub">Oculto en validación mientras el estacionamiento esté deshabilitado</small>' : ''}</td><td>${point.tipo === 'BIDIRECCIONAL' ? 'Entrada y salida' : point.tipo === 'ENTRADA' ? 'Solo entrada' : 'Solo salida'}</td><td>${badge(point.activo ? 'ACTIVO' : 'INACTIVO')}</td><td><button class="link ${point.activo ? 'link-danger' : ''}" type="button" data-access-point="${point.punto_acceso_id}" data-active="${!point.activo}">${point.activo ? 'Desactivar' : 'Activar'}</button></td></tr>`).join('')}</tbody></table></div>` : '<p class="empty">Esta sede aún no tiene puntos de acceso. Agrega uno para que aparezca en el selector de Control de acceso.</p>'}
      </section>
      <div class="gym-detail-grid">
        <section class="card view-panel"><div class="card-h"><div><h3>Máquinas</h3><p class="form-hint">Equipos asignados a ${esc(installation.nombre)}.</p></div><button class="button button-dark button-small" type="button" data-toggle-form="installation-machine-form" ${rooms.length ? '' : 'disabled'}>+ Agregar máquina</button></div>
          ${rooms.length ? '' : '<p class="notice">Agrega una sala antes de registrar máquinas. Cada equipo debe quedar asociado a un espacio de esta sede.</p>'}
          <form class="data-form hidden" id="installation-machine-form"><input type="hidden" name="instalacion_id" value="${installationId}"><div class="form-grid"><label>Nombre<input name="nombre" required maxlength="120"></label><label>Categoría<input name="categoria" required maxlength="80"></label><label>Sala<select name="sala_id" required><option value="">Selecciona una sala</option>${rooms.map(room => `<option value="${room.sala_id}">${esc(room.nombre)}</option>`).join('')}</select></label><label class="form-span">Observación<input name="observacion" maxlength="1000" placeholder="Detalle opcional para mantenimiento o seguimiento"></label></div><div class="form-actions"><button class="button button-primary" type="submit">Guardar máquina</button><button class="button button-light" type="button" data-reset-form="installation-machine-form">Cancelar</button></div></form>
          ${machines.length ? `<div class="table-wrap"><table><thead><tr><th>Máquina</th><th>Categoría</th><th>Sala asignada</th><th>Observación</th><th>Estado</th></tr></thead><tbody>${machines.map(item => `<tr><td><strong>${esc(item.nombre)}</strong></td><td>${esc(item.categoria)}</td><td><select class="inline-select" data-machine-room="${item.maquina_id}" data-current-sala="${item.sala_id || ''}" aria-label="Sala asignada a ${esc(item.nombre)}"><option value="">${item.sala_id ? 'Selecciona sala' : 'Asignar sala'}</option>${rooms.map(room => `<option value="${room.sala_id}" ${String(item.sala_id) === String(room.sala_id) ? 'selected' : ''}>${esc(room.nombre)}</option>`).join('')}</select></td><td>${esc(item.observacion || '—')}</td><td><select class="inline-select" data-machine="${item.maquina_id}" aria-label="Estado de ${esc(item.nombre)}">${[['OPERATIVA', 'Operativa'], ['MANTENCION', 'Mantención'], ['FUERA_SERVICIO', 'Fuera de servicio']].map(([value, label]) => `<option value="${value}" ${item.estado === value ? 'selected' : ''}>${label}</option>`).join('')}</select></td></tr>`).join('')}</tbody></table></div>` : '<p class="empty">Esta sede aún no tiene máquinas.</p>'}
        </section>
        <section class="card view-panel"><div class="card-h"><div><h3>Salas</h3><p class="form-hint">Espacios de clases pertenecientes a esta sede.</p></div><button class="button button-dark button-small" type="button" data-toggle-form="installation-room-form">+ Agregar sala</button></div>
          <form class="data-form hidden" id="installation-room-form"><input type="hidden" name="instalacion_id" value="${installationId}"><div class="form-grid"><label>Nombre<input name="nombre" required maxlength="100"></label><label>Capacidad máxima<input name="capacidad" type="number" min="1" required></label></div><div class="form-actions"><button class="button button-primary" type="submit">Guardar sala</button><button class="button button-light" type="button" data-reset-form="installation-room-form">Cancelar</button></div></form>
          ${rooms.length ? `<div class="table-wrap"><table><thead><tr><th>Sala</th><th>Capacidad</th></tr></thead><tbody>${rooms.map(item => `<tr><td>${esc(item.nombre)}</td><td>${Number(item.capacidad)} personas</td></tr>`).join('')}</tbody></table></div>` : '<p class="empty">Esta sede aún no tiene salas.</p>'}
        </section>
      </div>`;
  }

  function usersView() {
    const users = state.data.users || [];
    return `${heading('Administrar usuarios', 'Consulta y gestiona el acceso de las cuentas FitLife.', '<button class="button button-dark" data-toggle-form="staff-form">+ Crear cuenta profesional</button>')}
      <form class="card data-form hidden" id="staff-form"><h3>Crear cuenta de equipo</h3><div class="form-grid">
        <label>Nombre<input name="nombres" required minlength="3" maxlength="100" data-person-name data-name-required="true" aria-describedby="staff-nombres-error"><small class="field-validation-error hidden" id="staff-nombres-error" aria-live="polite"></small></label><label>RUT<input name="rut" required inputmode="text" placeholder="12.345.678-5"></label><label>Apellido paterno<input name="apellido_paterno" required minlength="3" maxlength="100" data-person-name data-name-required="true" aria-describedby="staff-apellido-paterno-error"><small class="field-validation-error hidden" id="staff-apellido-paterno-error" aria-live="polite"></small></label>
        <label>Apellido materno<input name="apellido_materno" minlength="3" maxlength="100" data-person-name data-name-required="false" aria-describedby="staff-apellido-materno-error"><small class="field-validation-error hidden" id="staff-apellido-materno-error" aria-live="polite"></small></label><label>Correo<input name="correo" type="email" required></label>
        <label>Contraseña inicial<input name="contrasena" type="password" minlength="12" maxlength="256" autocomplete="new-password" required></label>
        <label>Rol<select name="rol" id="staff-role"><option value="INSTRUCTOR">Instructor / equipo profesional</option><option value="RECEPCIONISTA">Recepción</option></select></label>
        <label id="professional-type-field">Tipo profesional<select name="tipo_profesional"><option value="MONITOR">Monitor</option><option value="PERSONAL_TRAINER">Entrenador personal</option><option value="COACH">Coach</option><option value="PREPARADOR_FISICO">Preparador físico</option></select></label>
        <label id="specialization-field">Especialidad<input name="especialidad" placeholder="Ej. Yoga, fuerza, movilidad"></label>
        <label class="hidden" id="staff-installation-field">Sede asignada<select name="instalacion_id"><option value="">Selecciona una sede</option>${(state.data.installations || []).map(installation => `<option value="${installation.instalacion_id}">${esc(installation.nombre)}</option>`).join('')}</select></label>
      </div><div class="form-actions"><button class="button button-primary" type="submit">Crear cuenta</button><button class="button button-light" type="button" data-reset-form="staff-form">Cancelar</button></div></form>
      <section class="card">${users.length ? `<div class="table-wrap"><table><thead><tr><th>Persona</th><th>RUT</th><th>Correo</th><th>Roles</th><th>Cuenta</th><th>Acciones</th></tr></thead><tbody>${users.map(user => `<tr><td><strong>${esc(user.nombres)} ${esc(user.apellido_paterno)}</strong></td><td>${esc(user.rut)}</td><td>${esc(user.correo)}</td><td>${user.roles.map(role => `<span class="pill">${esc(roleLabels[role] || role)}${role === 'RECEPCIONISTA' && user.recepcionista_instalacion ? ` · ${esc(user.recepcionista_instalacion)}` : ''}</span>`).join(' ')}</td><td>${badge(user.activo ? 'ACTIVA' : 'INACTIVA')}</td><td><div class="table-actions"><button class="link" type="button" data-user-roles="${esc(user.rut)}">Cambiar roles</button><button class="link" type="button" data-user="${esc(user.rut)}" data-active="${!user.activo}">${user.activo ? 'Desactivar' : 'Activar'}</button></div></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No hay usuarios registrados.</div>'}</section>
      <form class="card data-form hidden" id="user-role-form"><h3 id="user-role-form-title">Cambiar roles</h3><input type="hidden" name="rut"><fieldset class="form-section"><legend>Roles de la cuenta</legend><div class="form-subgrid">
        ${[['SOCIO', 'Socio'], ['INSTRUCTOR', 'Instructor'], ['RECEPCIONISTA', 'Recepción'], ['ADMINISTRADOR', 'Administrador']].map(([value, label]) => `<label class="form-check"><input type="checkbox" name="roles" value="${value}"> ${label}</label>`).join('')}
      </div></fieldset><fieldset class="form-section hidden" id="user-role-professional-field"><legend>Perfil profesional</legend><div class="form-subgrid">
        <label>Especialidad profesional<select name="tipo_profesional"><option value="MONITOR">Monitor</option><option value="PERSONAL_TRAINER">Entrenador personal</option><option value="COACH">Coach</option><option value="PREPARADOR_FISICO">Preparador físico</option></select></label>
        <label>Especialidad <small class="field-optional">Opcional</small><input name="especialidad" maxlength="150" placeholder="Ej. Yoga, fuerza, movilidad"></label>
      </div></fieldset><fieldset class="form-section hidden" id="user-role-installation-field"><legend>Sede de recepción</legend><label>Sede asignada<select name="instalacion_id"><option value="">Selecciona una sede activa</option>${(state.data.installations || []).map(installation => `<option value="${installation.instalacion_id}">${esc(installation.nombre)}</option>`).join('')}</select></label></fieldset><div class="form-actions"><button class="button button-primary" type="submit">Guardar roles</button><button class="button button-light" type="button" data-user-role-cancel>Cancelar</button></div></form>
      <section class="card admin-data-manager">
        <div class="card-h"><div><h3>Administrar datos del sistema</h3><p class="form-hint">Gestiona las tablas operativas. Pagos y registros históricos no se pueden modificar desde aquí.</p></div></div>
        <div class="admin-data-toolbar">
          <label for="admin-data-entity">Tabla</label>
          <select id="admin-data-entity">${(state.adminEntities || []).map(item => `<option value="${esc(item.key)}" ${item.key === state.adminEntityKey ? 'selected' : ''}>${esc(item.label)}</option>`).join('')}</select>
          <button class="button button-dark" type="button" data-admin-create>+ Nuevo registro</button>
        </div>
        <div id="admin-data-feedback" class="notice hidden" role="status"></div>
        <form class="card data-form hidden" id="admin-data-form"><h3 id="admin-data-form-title">Nuevo registro</h3><div class="form-grid" id="admin-data-fields"></div><div class="form-actions"><button class="button button-primary" type="submit">Guardar</button><button class="button button-light" type="button" data-admin-cancel>Cancelar</button></div></form>
        <div id="admin-data-records"><div class="empty">Selecciona una tabla para cargar sus registros.</div></div>
      </section>`;
  }

  function membershipsAdminView() {
    const data = state.data;
    const plans = data.plans || [];
    const memberships = data.admin_memberships || [];
    const installations = data.installations || [];
    const planSiteRegions = [...new Set(installations.map(installation => installation.region).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, 'es-CL'));
    const planSiteCities = [...new Set(installations.map(installation => installation.ciudad).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, 'es-CL'));
    const planBenefits = plan => [
      plan.incluye_entrenador_personal ? 'Entrenador personal' : '',
      plan.incluye_lockers ? 'Acceso a lockers' : '',
      plan.incluye_estacionamiento ? 'Estacionamiento' : '',
      plan.acceso_todas_sedes ? 'Acceso a todas las sedes' : '',
      plan.es_prueba_gratuita ? 'Prueba gratuita' : '',
      ...(plan.otros_beneficios || '').split('\n').filter(Boolean),
    ].filter(Boolean);
    return `${heading('Planes y membresías', 'Configura planes, beneficios, pruebas gratuitas por sede y membresías globales.', '<button class="button button-dark" data-toggle-form="plan-form">+ Crear plan</button>')}
      <form class="card data-form workflow-form hidden" id="plan-form"><div class="workflow-heading"><div><span class="eyebrow">CATÁLOGO COMERCIAL</span><h3>Nuevo plan o membresía</h3></div><p>Las pruebas gratuitas se ofrecen en una sede y se pueden canjear una sola vez por socio. La membresía global permite usar sus beneficios en todas las sedes activas.</p></div><div class="form-grid">
        <fieldset class="form-section form-span"><legend><span>1</span> Datos principales</legend><div class="form-subgrid">
          <label>Tipo<select name="tipo" required><option value="">Selecciona un tipo</option><option value="PLAN">Plan</option><option value="MEMBRESIA">Membresía</option></select></label>
          <label>Nombre<input name="nombre" required maxlength="80" placeholder="Ej. Plan mensual"></label>
          <label>Duración (días)<input name="duracion_dias" type="number" min="1" required placeholder="Ej. 30"></label>
          <label>Precio (CLP)<input name="precio_referencia" type="number" min="0" step="500" required placeholder="Ej. 24990"></label>
          <label class="form-span">Descripción <small class="field-optional">Opcional</small><textarea name="descripcion" rows="2" placeholder="Describe brevemente a quién está dirigido"></textarea></label>
          <label class="form-check form-span"><input name="es_prueba_gratuita" id="plan-free-trial" type="checkbox"> Oferta de prueba gratuita para una sede (precio $0, canje único por socio)</label>
          <label class="form-check form-span"><input name="acceso_todas_sedes" id="plan-global-access" type="checkbox"> Membresía global: habilitar este plan en todas las sedes activas</label>
        </div></fieldset>
        <fieldset class="form-section form-span" id="plan-sites-fieldset"><legend><span>2</span> Sedes disponibles</legend><p class="form-hint" id="plan-sites-help">Selecciona una o más sedes donde los clientes podrán contratar este plan. Una prueba gratuita debe asociarse a una sola sede.</p>
          ${installations.length ? `<div class="plan-site-filters" aria-label="Filtrar sedes">
            <label>Buscar sede<input type="search" data-plan-site-search placeholder="Nombre o dirección" autocomplete="off"></label>
            <label>Región<select data-plan-site-region><option value="">Todas las regiones</option>${planSiteRegions.map(region => `<option value="${esc(region)}">${esc(region)}</option>`).join('')}</select></label>
            <label>Comuna<select data-plan-site-city><option value="">Todas las comunas</option>${planSiteCities.map(city => `<option value="${esc(city)}">${esc(city)}</option>`).join('')}</select></label>
          </div><p class="form-hint plan-site-count" data-plan-site-count aria-live="polite">${installations.length} ${installations.length === 1 ? 'sede' : 'sedes'}</p>
          <div class="plan-site-list">${installations.map(installation => {
            const searchText = [installation.nombre, installation.direccion, installation.ciudad, installation.region].filter(Boolean).join(' ');
            return `<label class="form-check" data-plan-site-option data-region="${esc(installation.region || '')}" data-city="${esc(installation.ciudad || '')}" data-search="${esc(searchText)}"><input type="checkbox" name="instalaciones_ids" value="${installation.instalacion_id}"> <span><strong>${esc(installation.nombre)}</strong><small>${esc([installation.ciudad, installation.region].filter(Boolean).join(', ') || installation.direccion || 'Ubicación por confirmar')}</small></span></label>`;
          }).join('')}</div>` : '<p class="empty">Primero registra una sede para poder publicar el plan.</p>'}
        </fieldset>
        <details class="form-options form-span"><summary>Configurar beneficios</summary><div class="form-subgrid">
          <label class="form-check"><input name="incluye_entrenador_personal" type="checkbox"> Incluye entrenador personal</label><label class="form-check"><input name="incluye_lockers" type="checkbox"> Incluye acceso a lockers</label><label class="form-check"><input name="incluye_estacionamiento" type="checkbox"> Incluye estacionamiento (según disponibilidad de la sede)</label>
          <label class="form-span">Otros beneficios <small>Uno por línea</small><textarea name="otros_beneficios" rows="3" maxlength="1000" placeholder="Ej. Evaluación nutricional&#10;Acceso a piscina"></textarea></label>
        </div></details>
      </div><div class="form-actions"><button class="button button-primary" type="submit">Guardar plan</button><button class="button button-light" type="button" data-reset-form="plan-form">Cancelar</button></div></form>
      <div class="stats overview-stats" aria-label="Resumen de planes y membresías"><div class="stat"><strong>${plans.length}</strong>Planes disponibles</div><div class="stat"><strong>${memberships.length}</strong>Membresías registradas</div><div class="stat"><strong>${memberships.filter(item => item.estado === 'PENDIENTE').length}</strong>Pendientes de pago</div></div>
      <section class="card view-panel"><div class="card-h"><div><h3>Planes disponibles</h3><p class="form-hint">Catálogo de precios y beneficios para las sedes.</p></div></div>${plans.length ? `<div class="table-wrap"><table><thead><tr><th>Tipo</th><th>Plan</th><th>Sedes</th><th>Duración</th><th>Precio</th><th>Beneficios</th><th>Acciones</th></tr></thead><tbody>${plans.map(plan => `<tr><td><span class="plan-type ${plan.tipo === 'MEMBRESIA' ? 'membership' : ''}">${plan.es_prueba_gratuita ? 'Prueba gratuita' : plan.acceso_todas_sedes ? 'Membresía global' : plan.tipo === 'MEMBRESIA' ? 'Membresía' : 'Plan'}</span></td><td><strong>${esc(plan.nombre)}</strong><small class="table-sub">${esc(plan.descripcion || '')}</small></td><td>${plan.acceso_todas_sedes ? '<span class="pill">Todas las sedes activas</span>' : (data.installations || []).filter(installation => (installation.plan_ids || []).some(planId => String(planId) === String(plan.plan_id))).map(installation => `<span class="pill">${esc(installation.nombre)}</span>`).join(' ') || '—'}</td><td>${Number(plan.duracion_dias)} días</td><td class="plan-price">${money(plan.precio_referencia)}</td><td>${planBenefits(plan).length ? planBenefits(plan).map(item => `<span class="pill">${esc(item)}</span>`).join(' ') : '—'}</td><td><div class="table-actions"><button class="link" type="button" data-plan-edit="${plan.plan_id}">Editar</button><button class="link link-danger" type="button" data-plan-delete="${plan.plan_id}">Desactivar</button></div></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No hay planes activos. Crea un plan para comenzar.</div>'}</section>
      <section class="card view-panel"><div class="card-h"><div><h3>Membresías</h3><p class="form-hint">Consulta las membresías registradas por sede. Las asignaciones y confirmaciones de pago se procesan fuera de esta pantalla.</p></div></div>
        ${memberships.length ? `<div class="table-wrap"><table><thead><tr><th>Sede</th><th>Socio</th><th>Plan</th><th>Beneficios</th><th>Estado</th><th>Vigencia</th><th>Precio</th></tr></thead><tbody>${memberships.map(item => `<tr><td>${esc(item.sede || 'Sede no asignada')}</td><td>${esc(item.socio)}</td><td><strong>${esc(item.plan)}</strong></td><td>${planBenefitLabels(item).length ? planBenefitLabels(item).map(benefit => `<span class="pill">${esc(benefit)}</span>`).join(' ') : '—'}</td><td>${badge(item.estado)}</td><td>${item.fecha_inicio && item.fecha_fin ? `${dateOnly(item.fecha_inicio)} – ${dateOnly(item.fecha_fin)}` : 'Pendiente de confirmación'}</td><td>${money(item.precio_acordado)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Aún no hay membresías registradas.</div>'}
      </section>`;
  }

  function accessTable(access) {
    if (!access.length) return '<div class="empty">No hay accesos recientes.</div>';
    return `<div class="table-wrap"><table><thead><tr><th>Persona</th><th>Tipo</th><th>Instalación</th><th>Acceso</th><th>Hora</th><th>Resultado</th></tr></thead><tbody>${access.map(item => `<tr><td>${esc(item.socio || 'No identificado')}</td><td>${esc(item.tipo_persona === 'PERSONAL' ? 'Equipo FitLife' : 'Socio')}</td><td>${esc(item.instalacion)}</td><td>${esc(item.tipo)}</td><td>${dateTime(item.registrado_en)}</td><td>${badge(item.resultado)}</td></tr>`).join('')}</tbody></table></div>`;
  }

  function reportsView() {
    const data = state.data;
    const summary = data.summary || {};
    return `${heading('Reportes', 'Indicadores operativos y actividad reciente.')}
      <div class="kpis">
        <article class="card kpi"><span class="lbl">Socios activos</span><strong class="val">${Number(summary.socios || 0).toLocaleString('es-CL')}</strong></article>
        <article class="card kpi"><span class="lbl">Personas en las sedes</span><strong class="val">${Number(summary.presentes || 0).toLocaleString('es-CL')}</strong></article>
        <article class="card kpi"><span class="lbl">Membresías vencidas</span><strong class="val">${Number(summary.membresias_vencidas || 0).toLocaleString('es-CL')}</strong></article>
        <article class="card kpi"><span class="lbl">Clases de hoy</span><strong class="val">${Number(summary.clases_hoy || 0).toLocaleString('es-CL')}</strong></article>
      </div><section class="card"><div class="card-h"><h3>Accesos recientes</h3><button class="button button-light button-small" data-export>Exportar CSV</button></div>${accessTable(data.recent_access || [])}</section>`;
  }

  function alertsView() {
    const data = state.data;
    const alerts = [
      ...(data.occupancy || []).filter(item => Number(item.porcentaje_ocupacion || 0) >= 85)
        .map(item => ({ title: `Aforo sobre el 85% en ${item.instalacion}`, details: `${item.personas_presentes} personas · ${item.porcentaje_ocupacion}% de ocupación`, level: 'bad' })),
      ...(data.waitlist || []).map(item => ({ title: `${item.socio} está en lista de espera`, details: `Sesión ${item.sesion_id} · ${dateTime(item.creada_en)}`, level: 'warn' })),
      ...(data.machines || []).filter(item => item.estado !== 'OPERATIVA')
        .map(item => ({ title: `${item.nombre} requiere atención`, details: `${item.categoria} · ${item.estado.replaceAll('_', ' ')}`, level: 'warn' })),
      Number(data.summary?.membresias_vencidas || 0) > 0
        ? { title: 'Membresías vencidas pendientes de revisión', details: `${data.summary.membresias_vencidas} socio(s)`, level: 'warn' }
        : null,
    ].filter(Boolean);
    return `${heading('Alertas', 'Situaciones que requieren atención en FitLife.')}
      <section class="card">${alerts.length ? alerts.map(item => `<div class="alert-row alert-row-large"><span class="alert-dot ${item.level}"></span><div><strong>${esc(item.title)}</strong><small>${esc(item.details)}</small></div><span class="badge ${item.level}">Revisar</span></div>`).join('') : '<div class="empty">No hay alertas activas.</div>'}</section>`;
  }

  function accessView() {
    const data = state.data;
    const receptionOnly = data.roles.includes('RECEPCIONISTA') && !data.roles.includes('ADMINISTRADOR');
    const unassignedReception = receptionOnly && !data.user.recepcionista_instalacion_id;
    return `${heading('Control de acceso', receptionOnly && data.user.recepcionista_instalacion ? `Sede asignada: ${esc(data.user.recepcionista_instalacion)}. Valida aquí las credenciales de esa sede.` : 'Valida credenciales QR en el punto de entrada o salida.')}
      ${unassignedReception ? '<div class="notice">Tu cuenta de recepción todavía no tiene una sede asignada. Solicita a Administración que la configure para habilitar las validaciones.</div>' : ''}
      <div class="two access-layout"><form class="card data-form" id="access-form"><h3>Validar credencial</h3><div class="scanner-container" id="scanner-container"><video id="scanner-video" muted playsinline></video><span>La cámara aparecerá aquí cuando la actives.</span></div><button class="button button-light button-small scanner-toggle" id="scan-camera" type="button">Activar cámara QR</button><label>Token QR<input id="access-token" name="credential" autocomplete="off" required placeholder="Escanea o pega el token de la credencial"></label><div class="form-grid"><label>Punto de acceso<select name="punto_acceso_id" required><option value="">Selecciona el acceso</option>${(data.access_points || []).map(point => `<option value="${point.punto_acceso_id}">${esc(point.instalacion)} · ${esc(point.nombre)}${point.uso === 'ESTACIONAMIENTO' ? ' · Estacionamiento' : ''}</option>`).join('')}</select></label><label>Movimiento<select name="tipo"><option value="ENTRADA">Entrada</option><option value="SALIDA">Salida</option></select></label></div><button class="button button-dark" type="submit">Validar acceso</button><div id="access-result"></div></form>
      <section class="card"><div class="card-h"><h3>Últimos accesos</h3></div>${accessTable(data.recent_access || [])}</section></div>`;
  }

  function attendanceView() {
    const sessions = state.data.instructor_sessions || [];
    const selectedSession = sessions.find(item => String(item.sesion_id) === String(state.attendanceSessionId));
    const attendees = (state.data.attendees || []).filter(item =>
      !state.attendanceSessionId || String(item.sesion_id) === String(state.attendanceSessionId)
    );
    const title = selectedSession ? `Asistencia · ${esc(selectedSession.nombre)}` : 'Registro de asistencia';
    const description = selectedSession
      ? `${dateTime(selectedSession.inicio)} · ${esc(selectedSession.sala)}`
      : 'Registra la asistencia de los socios inscritos en tus clases.';
    const backAction = selectedSession
      ? '<button class="button button-light button-small" data-attendance-back>Volver a mis clases</button>'
      : '';
    return `${heading(title, description, backAction)}
      <div class="notice">Puedes registrar asistencia cuando la clase haya comenzado. El sistema valida el horario, la reserva y que la clase te corresponda.</div>
      <section class="card"><div class="card-h"><h3>${selectedSession ? 'Socios inscritos en esta clase' : 'Socios inscritos en tus clases'}</h3></div>${attendees.length ? `<div class="table-wrap"><table><thead><tr><th>Socio</th><th>Clase</th><th>Inicio</th><th>Asistencia</th></tr></thead><tbody>${attendees.map(item => {
        const enabled = ['EN_CURSO', 'FINALIZADA'].includes(item.estado_sesion) && new Date(item.inicio) <= new Date();
        const attendanceControl = item.estado === 'RESERVADA'
          ? `<button class="link" data-attendance="${item.reserva_id}" data-session="${item.sesion_id}" data-attended="true" ${enabled ? '' : 'disabled'}>Asistió</button><button class="link link-danger" data-attendance="${item.reserva_id}" data-session="${item.sesion_id}" data-attended="false" ${enabled ? '' : 'disabled'}>Ausente</button>`
          : badge(item.estado);
        return `<tr><td><strong>${esc(item.socio)}</strong></td><td>${esc(item.clase)}</td><td>${dateTime(item.inicio)}</td><td>${attendanceControl}</td></tr>`;
      }).join('')}</tbody></table></div>` : `<div class="empty">${selectedSession ? 'No hay socios con reservas confirmadas para esta clase.' : 'Todavía no hay socios con reservas confirmadas en tus clases.'}</div>`}</section>
      ${selectedSession ? '' : `<section class="card"><div class="card-h"><h3>Mis clases</h3></div>${sessionsTable(sessions, true)}</section>`}`;
  }

  const teamView = professionalViews.teamView;

  function view() {
    const specialty = instructorSpecialties[state.data.professional_profile?.tipo];
    const routes = {
      home: ['Inicio', summaryView],
      gym: ['Tu gimnasio', gymView],
      'gym-detail': ['Sede', gymDetailView],
      classes: ['Cursos y clases', state.data.roles.includes('ADMINISTRADOR') ? adminClassesView : classView],
      sessions: [specialty?.navigation.find(([route]) => route === 'sessions')?.[1] || 'Mis clases', monitorClassesView],
      attendance: [specialty?.navigation.find(([route]) => route === 'attendance')?.[1] || 'Asistencia', attendanceView],
      team: [specialty?.navigation.find(([route]) => route === 'team')?.[1] || 'Seguimiento', teamView],
      membership: ['Mi suscripción', membershipView],
      plans: ['Planes disponibles', customerPlansView],
      reservations: ['Mis reservas', reservationsView],
      installations: ['Sedes registradas', installationsView],
      'installation-detail': ['Administrar sede', installationAdminView],
      memberships: ['Planes y membresías', membershipsAdminView],
      users: ['Usuarios', usersView],
      reports: ['Reportes', reportsView],
      alerts: ['Alertas', alertsView],
      access: ['Control de acceso', accessView],
    };
    if (state.data.roles.includes('INSTRUCTOR')) {
      if (!specialty?.recordsTitle) delete routes.team;
      if (state.data.professional_profile?.tipo !== 'MONITOR') {
        delete routes.sessions;
        delete routes.attendance;
      }
    }
    if (!routes[state.route]) state.route = 'home';
    const [title, render] = routes[state.route];
    document.getElementById('page-title').textContent = title;
    document.getElementById('breadcrumb-section').textContent =
      state.data.roles.includes('ADMINISTRADOR') || state.data.roles.includes('RECEPCIONISTA')
        ? 'Administración'
        : state.data.roles.includes('INSTRUCTOR') ? 'Equipo FitLife' : 'Mi espacio';
    content.innerHTML = render();
    if (state.route === 'classes' && state.data.roles.includes('ADMINISTRADOR')) {
      updateClassResources(document.getElementById('class-form'));
    }
    if (state.route === 'sessions' && state.data.professional_profile?.tipo === 'MONITOR') {
      updateClassResources(document.getElementById('monitor-class-form'));
    }
  }

  return { view, sessionsTable };
}
