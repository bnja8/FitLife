/* FitLife · Mockup interactivo (datos de ejemplo, sin backend) */
const $ = (s, r = document) => r.querySelector(s);
const pad = n => String(n).padStart(2, '0');
const key = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const money = n => n === 0 ? 'Incluida' : '$' + n.toLocaleString('es-CL');
const DAYS = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
const DAYS_L = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const parse = k => { const [y, m, d] = k.split('-').map(Number); return new Date(y, m - 1, d); };
const longDate = k => { const d = parse(k); return `${DAYS_L[d.getDay()]} ${d.getDate()} de ${MONTHS[d.getMonth()]}`; };

const TODAY = new Date(); TODAY.setHours(0, 0, 0, 0);
const ACTIVITIES = ['Spinning', 'Yoga', 'Funcional', 'Fútbol', 'Sala de máquinas'];

/* ---------- Datos de ejemplo ---------- */
const TEMPLATES = [
  ['Spinning 45\'', 'Spinning', '07:00', 20, 0, 'Camila Rojas'],
  ['Sala de máquinas · Turno', 'Sala de máquinas', '10:00', 40, 0, 'Monitor de sala'],
  ['Yoga Flow', 'Yoga', '09:30', 15, 0, 'Andrea Soto'],
  ['Funcional HIIT', 'Funcional', '12:30', 18, 0, 'Diego Paredes'],
  ['Spinning 45\'', 'Spinning', '18:30', 20, 0, 'Camila Rojas'],
  ['Fútbol 7 · Cancha 1', 'Fútbol', '19:00', 14, 8000, 'Pablo Núñez'],
  ['Yoga Restaurativo', 'Yoga', '20:00', 15, 0, 'Andrea Soto'],
];
let nextId = 1;
function seedClasses() {
  const list = [];
  for (let i = 0; i < 14; i++) {
    TEMPLATES.forEach((t, j) => {
      if ((i + j) % 5 === 0) return;
      const id = nextId++;
      let booked = (id * 5 + 3) % (t[3] + 1);
      if (id % 4 === 0) booked = t[3];
      list.push({ id, name: t[0], type: t[1], date: key(addDays(TODAY, i)), time: t[2], cap: t[3], price: t[4], ins: t[5], booked });
    });
  }
  return list;
}

const PLANS = [
  { id: 'basic', name: 'Plan Básico', price: 17990, desc: 'Sala de máquinas, acceso 6:00 a 23:00' },
  { id: 'black', name: 'Plan Black', price: 24990, desc: 'Máquinas + clases grupales ilimitadas' },
  { id: 'pro', name: 'Plan Pro', price: 34990, desc: 'Todo Black + asesoría de entrenador' },
];

const state = {
  role: null, view: '', page: 'home', cookies: false, user: { name: 'Valentina Muñoz', email: 'valentina@correo.cl' },
  authTab: 'login',
  plan: 'black', status: 'Activa', expires: key(addDays(TODAY, 21)),
  classes: seedClasses(), reservations: [], waitlist: [],
  day: 0, filter: 'Todas',
  aforo: 142, aforoMax: 200,
  reportRange: 'Semana', resTab: 'Máquinas', staffRole: 'monitor', done: {},
  alerts: [
    { id: 1, lvl: 'high', t: 'Aforo sobre el 85% en sala de máquinas', s: 'Hace 4 min' },
    { id: 2, lvl: 'mid', t: '3 membresías vencen mañana', s: 'Hace 1 h' },
    { id: 3, lvl: 'mid', t: 'Spinning 18:30 con lista de espera de 5 personas', s: 'Hace 2 h' },
    { id: 4, lvl: 'low', t: 'Cinta de correr #4 requiere mantención', s: 'Ayer' },
  ],
  resources: {
    'Máquinas': [['Cinta de correr #1', 'Cardio', 'Operativa'], ['Cinta de correr #4', 'Cardio', 'Mantención'], ['Prensa de piernas', 'Fuerza', 'Operativa'], ['Bicicleta spinning #12', 'Cardio', 'Operativa']],
    'Deportes': [['Fútbol 7', 'Cancha 1', 'Operativa'], ['Pádel', 'Cancha 2', 'Operativa'], ['Básquetbol', 'Gimnasio', 'Mantención']],
    'Espacios': [['Sala Spinning', 'Capacidad 20', 'Operativa'], ['Sala Yoga', 'Capacidad 15', 'Operativa'], ['Zona funcional', 'Capacidad 18', 'Operativa']],
  },
  users: [
    ['Valentina Muñoz', 'valentina@correo.cl', 'Black', 'Activa'], ['Matías Fuentes', 'matias.f@correo.cl', 'Básico', 'Vencida'],
    ['Javiera Pinto', 'jpinto@correo.cl', 'Pro', 'Activa'], ['Nicolás Araya', 'naraya@correo.cl', 'Black', 'Congelada'],
    ['Daniela Vera', 'dvera@correo.cl', 'Básico', 'Activa'], ['Sebastián Rojas', 'srojas@correo.cl', 'Black', 'Vencida'],
  ],
  userQ: '', userF: 'Todos',
};

/* ---------- Utilidades UI ---------- */
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toast.h); toast.h = setTimeout(() => t.hidden = true, 2600);
}
function openModal(html) { const m = $('#modal'); m.innerHTML = `<div class="modal-box">${html}</div>`; m.hidden = false; }
function closeModal() { $('#modal').hidden = true; }
function qrSvg(seed) {
  const n = 21; let r = '', s = seed;
  const rnd = () => (s = (s * 9301 + 49297) % 233280) / 233280;
  const finder = (x, y) => `<rect x="${x}" y="${y}" width="7" height="7" fill="#111"/><rect x="${x + 1}" y="${y + 1}" width="5" height="5" fill="#fff"/><rect x="${x + 2}" y="${y + 2}" width="3" height="3" fill="#111"/>`;
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
    const inF = (x < 8 && y < 8) || (x > 12 && y < 8) || (x < 8 && y > 12);
    if (!inF && rnd() > .52) r += `<rect x="${x}" y="${y}" width="1" height="1" fill="#111"/>`;
  }
  return `<svg viewBox="0 0 21 21" shape-rendering="crispEdges"><rect width="21" height="21" fill="#fff"/>${r}${finder(0, 0)}${finder(14, 0)}${finder(0, 14)}</svg>`;
}
const statusBadge = s => `<span class="badge ${s === 'Activa' ? 'ok' : s === 'Vencida' ? 'bad' : 'info'}">${s}</span>`;
const stateBadge = s => `<span class="badge ${s === 'Operativa' ? 'ok' : 'warn'}">${s}</span>`;

/* ---------- Render principal ---------- */
function render() {
  const app = $('#app');
  document.body.className = state.role === 'client' || !state.role ? 'theme-client' : state.role === 'staff' ? 'theme-admin theme-staff' : 'theme-admin';
  if (!state.role) app.innerHTML = state.page === 'auth' ? siteHeader(pubCfg()) + authView() : homeView();
  else if (state.role === 'client') app.innerHTML = clientView();
  else if (state.role === 'admin') app.innerHTML = adminView();
  else app.innerHTML = staffView();
  window.scrollTo(0, 0);
}
function go(view) { state.view = view; render(); }
function login(role) {
  state.role = role;
  state.view = { client: 'sub', admin: 'dash', staff: 'day' }[role];
  render();
}

/* ---------- Autenticación ---------- */
function authView() {
  const reg = state.authTab === 'register';
  return `<div class="auth">
    <section class="auth-hero">
      <span></span>
      <div><h1>Entra, reserva y <span>entrena</span>.</h1><p>Tu membresía, tus clases y tu acceso con QR en un solo lugar.</p></div>
      <small style="color:#777">© 2026 FitLife</small>
    </section>
    <section class="auth-form"><div class="auth-box">
      <button class="back" data-act="tohome">← Volver al inicio</button><div class="tabs"><button class="${!reg ? 'on' : ''}" data-act="authtab" data-v="login">Iniciar sesión</button><button class="${reg ? 'on' : ''}" data-act="authtab" data-v="register">Crear cuenta</button></div>
      <form data-form="auth">
        ${reg ? `<div class="field"><label>Nombre completo</label><input required placeholder="Ej: Valentina Muñoz"></div>` : ''}
        <div class="field"><label>Correo</label><input type="email" required placeholder="tucorreo@ejemplo.cl"></div>
        <div class="field"><label>Contraseña</label><input type="password" required placeholder="••••••••"></div>
        ${reg ? `<div class="field"><label>RUT</label><input required placeholder="12.345.678-9"></div>` : ''}
        <button class="btn" style="width:100%">${reg ? 'Crear cuenta' : 'Ingresar'}</button>
      </form>
      <p class="demo">Demo: entrar como <button data-act="login" data-v="admin">Administrador</button><button data-act="login" data-v="staff">Instructor</button></p>
    </div></section></div>`;
}

/* ---------- Navbar y menú lateral (compartido en todo el sitio) ---------- */
function siteHeader(c) {
  const badge = b => b ? `<em class="count">${b}</em>` : '';
  const lnk = ([l, act, v, k, b]) => `<button class="${c.active === k ? 'on' : ''}" data-act="${act}" data-v="${v ?? ''}">${l}${badge(b)}</button>`;
  const dit = ([l, act, v, k, b]) => `<button class="d-item ${c.active === k ? 'on' : ''}" data-act="${act}" data-v="${v ?? ''}">${l}${badge(b)}</button>`;
  const u = c.user;
  return `<header class="h-head"><div class="h-in">
    <button class="logo" data-act="${c.home[0]}" data-v="${c.home[1]}">Fit<b>Life</b></button>
    <nav class="h-nav">${c.links.map(lnk).join('')}</nav>
    ${u ? `<span class="h-user"><span class="avatar sm">${initials(u.name)}</span><span><b>${u.name}</b><small>${u.role}</small></span></span>` : ''}
    <button class="btn" data-act="${c.cta[1]}" data-v="${c.cta[2]}">${c.cta[0]}</button>
    <button class="burger" data-act="menu" aria-label="Abrir menú"><i></i><i></i><i></i></button>
  </div></header>
  <div class="ov" data-act="menu"></div>
  <aside class="drawer" id="drawer" aria-label="Menú lateral">
    <div class="d-head"><button class="logo" data-act="${c.home[0]}" data-v="${c.home[1]}">Fit<b>Life</b></button><button class="d-close" data-act="menu" aria-label="Cerrar menú">✕</button></div>
    <button class="btn" data-act="${c.cta[1]}" data-v="${c.cta[2]}">${c.cta[0]}</button>
    ${u ? `<div class="d-user"><span class="avatar">${initials(u.name)}</span><div><b>${u.name}</b><small>${u.role}</small></div></div>` : ''}
    ${c.groups.map(g => `${g.label ? `<span class="d-label">${g.label}</span>` : ''}${g.items.map(dit).join('')}`).join('')}
  </aside>`;
}
function toggleDrawer(force) {
  const d = $('#drawer'), o = $('.ov');
  if (!d || !o) return;
  const open = force === undefined ? !d.classList.contains('open') : force;
  d.classList.toggle('open', open); o.classList.toggle('open', open);
  document.body.style.overflow = open ? 'hidden' : '';
}
const pubCfg = () => ({
  home: ['tohome', ''], active: '', user: null, cta: ['¡Inscríbete ya!', 'toauth', 'register'],
  links: [['Planes', 'scrollto', 'planes'], ['Clases', 'scrollto', 'clases'], ['Cómo funciona', 'scrollto', 'como'], ['Tu espacio', 'toauth', 'login']],
  groups: [
    { items: [['Planes', 'scrollto', 'planes'], ['Clases y deportes', 'scrollto', 'clases'], ['Cómo funciona', 'scrollto', 'como'], ['Tu espacio', 'toauth', 'login']] },
    { label: 'Ayuda', items: [['Preguntas frecuentes', 'chat', ''], ['Contáctanos', 'chat', '']] },
  ],
});
const clientCfg = () => {
  const L = [['Mi suscripción', 'go', 'sub', 'sub'], ['Clases', 'go', 'classes', 'classes'], ['Mis reservas', 'go', 'res', 'res']];
  return {
    home: ['go', 'sub'], active: state.view, links: L, cta: ['Reservar clase', 'go', 'classes'],
    user: { name: state.user.name, role: 'Membresía ' + state.status.toLowerCase() },
    groups: [{ label: 'Mi cuenta', items: L }, { label: 'Más', items: [['Ayuda', 'chat', ''], ['Cerrar sesión', 'logout', '']] }],
  };
};

/* ---------- Home (landing) ---------- */
function homeView() {
  const until = addDays(TODAY, 7), ut = `${pad(until.getDate())}/${pad(until.getMonth() + 1)}`;
  const ribbon = Array(10).fill(`<span>| HASTA EL ${ut} </span>`).join('');
  const feats = {
    basic: ['Sala de máquinas', 'Horario 6:00 a 23:00', 'Acceso con código QR'],
    black: ['Todo lo del plan Básico', 'Clases grupales ilimitadas', 'Reserva con lista de espera'],
    pro: ['Todo lo del plan Black', 'Asesoría de entrenador', 'Evaluación física mensual'],
  };
  const classes = [
    ['Spinning', 'Cardio de alta energía con música y luces.', '07:00 · 18:30'],
    ['Yoga', 'Flexibilidad y calma para equilibrar tu semana.', '09:30 · 20:00'],
    ['Funcional', 'Circuitos HIIT para fuerza y resistencia.', '12:30'],
    ['Fútbol 7', 'Reserva cancha y elige tu horario.', '19:00'],
  ];
  const steps = [
    ['01', 'Elige tu plan', 'Contrata online y paga con tarjeta, WebPay o transferencia.'],
    ['02', 'Reserva tu clase', 'Mira el calendario, elige fecha y hora o únete a la lista de espera.'],
    ['03', 'Entra con tu QR', 'Muestra tu código en el torniquete y valida tu acceso en milisegundos.'],
  ];
  return `${siteHeader(pubCfg())}
  <main id="top">
    <div class="promo"><div class="marq"><div>${ribbon}${ribbon}</div></div></div>
    <section class="hero-h">
      <div class="hero-vis"><div class="glow"></div>
        <div class="fcard f1"><small>Reserva tu clase</small><b>Spinning 18:30</b><div class="bar"><i style="width:80%"></i></div><small>4 cupos disponibles</small></div>
        <div class="fcard f2"><span class="okdot">✓</span><div><b>Acceso permitido</b><small>Plan Black · 0,04 s</small></div></div>
        <div class="fcard f3">${qrSvg(11)}</div>
      </div>
      <div class="hero-copy">
        <div class="h-logo">Fit<b>Life</b></div>
        <div class="mode"><span>MODO ENTRENA</span><i class="toggle"><b>ON</b><u>⚡</u></i></div>
        <div class="offer"><span class="o1">1ª MENSUALIDAD</span><b class="o2">50% OFF</b><span class="o3">PLAN BLACK</span></div>
        <button class="btn big" data-act="toauth" data-v="register">¡Inscríbete ya!</button>
        <p>Reserva clases, controla tu membresía y entra con QR.</p>
      </div>
    </section>

    <section class="sec" id="como"><div class="sec-in">
      <h2 class="sec-t">Así de simple</h2>
      <div class="steps">${steps.map(s => `<div class="step"><span>${s[0]}</span><h3>${s[1]}</h3><p>${s[2]}</p></div>`).join('')}</div>
    </div></section>

    <section class="sec alt" id="planes"><div class="sec-in">
      <h2 class="sec-t">Elige tu plan</h2><p class="sec-s">Sin contratos largos. Cambia de plan cuando quieras.</p>
      <div class="h-plans">${PLANS.map(p => `<div class="h-plan ${p.id === 'black' ? 'hot' : ''}">${p.id === 'black' ? '<span class="ribbon">Más elegido</span>' : ''}
        <h3>${p.name}</h3><div class="pr">$${p.price.toLocaleString('es-CL')}<small>/mes</small></div>
        <ul>${feats[p.id].map(f => `<li>${f}</li>`).join('')}</ul>
        <button class="btn ${p.id === 'black' ? '' : 'ghost'}" data-act="toauth" data-v="register">Elegir plan</button></div>`).join('')}</div>
    </div></section>

    <section class="sec" id="clases"><div class="sec-in">
      <h2 class="sec-t">Clases y deportes</h2><p class="sec-s">Reserva en segundos y asegura tu cupo.</p>
      <div class="tiles">${classes.map((c, i) => `<div class="tile t${i % 2}"><h3>${c[0]}</h3><p>${c[1]}</p><small>${c[2]}</small><button data-act="toauth" data-v="login">Reservar →</button></div>`).join('')}</div>
    </div></section>

    <section class="cta"><h2>Empieza hoy con 50% OFF</h2><p>Tu primera mensualidad del plan Black a mitad de precio.</p><button class="btn dark big" data-act="toauth" data-v="register">¡Inscríbete ya!</button></section>
  </main>
  <footer class="h-foot"><div class="sec-in"><div class="logo">Fit<b>Life</b></div>
    <div class="foot-links"><button data-act="toauth" data-v="login">Tu espacio</button><button data-act="scrollto" data-v="planes">Planes</button><button data-act="scrollto" data-v="clases">Clases</button></div>
    <small>© 2026 FitLife. Todos los derechos reservados.</small></div></footer>
  <button class="wa" data-act="chat" title="Ayuda"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L3 21l1.9-6.2A8 8 0 1 1 21 12z"/></svg></button>
  ${state.cookies ? '' : `<div class="cookie"><p>Utilizamos cookies para personalizar anuncios y mejorar tu experiencia en el sitio. Al continuar navegando, aceptas nuestra política de privacidad.</p><button class="btn-w" data-act="cookies">OK</button><a>Saber más</a></div>`}`;
}

/* ---------- Cliente ---------- */
function clientView() {
  const nav = [['sub', 'Mi suscripción'], ['classes', 'Clases'], ['res', 'Mis reservas']];
  const body = { sub: clientSub, classes: clientClasses, res: clientRes }[state.view]();
  return `${siteHeader(clientCfg())}<main class="page">${body}</main>`;
}
function clientSub() {
  const p = PLANS.find(x => x.id === state.plan);
  return `<h2>Mi suscripción</h2><p class="sub">Hola, ${state.user.name.split(' ')[0]}. Este es el estado de tu membresía.</p>
  <div class="grid2">
    <div class="sub-card"><span class="tag">${statusBadgeText()}</span><h3>${p.name}</h3><p style="color:#aaa">${p.desc}</p>
      <div class="meta"><div>Próximo pago<b>${'$' + p.price.toLocaleString('es-CL')}</b></div><div>Vence<b>${longDate(state.expires)}</b></div></div></div>
    <div class="card qr-card"><b>Tu código de acceso</b>${qrSvg(state.plan.length * 77 + 5)}<p class="muted" style="font-size:13px">Muéstralo en el torniquete</p></div>
  </div>
  <h3 class="section-title">Cambiar de plan</h3>
  <div class="plans">${PLANS.map(x => `<div class="plan ${x.id === state.plan ? 'cur' : ''}"><h4>${x.name}</h4><div class="price">$${x.price.toLocaleString('es-CL')}<small> /mes</small></div><p class="muted" style="font-size:13px">${x.desc}</p>
    ${x.id === state.plan ? `<span class="badge ok" style="align-self:flex-start;margin-top:10px">Plan actual</span>` : `<button class="btn sm ghost" data-act="buyplan" data-v="${x.id}">Elegir plan</button>`}</div>`).join('')}</div>`;
}
const statusBadgeText = () => 'Membresía ' + state.status.toLowerCase();
function clientClasses() {
  const k = key(addDays(TODAY, state.day));
  const list = state.classes.filter(c => c.date === k && (state.filter === 'Todas' || c.type === state.filter)).sort((a, b) => a.time.localeCompare(b.time));
  const days = Array.from({ length: 7 }, (_, i) => { const d = addDays(TODAY, i); return `<button class="day ${i === state.day ? 'on' : ''}" data-act="day" data-v="${i}">${i === 0 ? 'Hoy' : DAYS[d.getDay()]}<b>${d.getDate()}</b></button>`; }).join('');
  return `<h2>Reserva tu clase</h2><p class="sub">Elige fecha, actividad y horario disponible.</p>
  <div class="days">${days}</div>
  <div class="chips">${['Todas', ...ACTIVITIES].map(a => `<button class="chip ${state.filter === a ? 'on' : ''}" data-act="filter" data-v="${a}">${a}</button>`).join('')}</div>
  <div>${list.length ? list.map(slotRow).join('') : '<div class="empty">No hay clases para este filtro.</div>'}</div>`;
}
function slotRow(c) {
  const full = c.booked >= c.cap, mine = state.reservations.includes(c.id), wl = state.waitlist.includes(c.id);
  const left = c.cap - c.booked;
  let act = `<button class="btn sm" data-act="reserve" data-v="${c.id}">Reservar</button>`;
  if (mine) act = `<span class="badge ok">Reservada</span>`;
  else if (wl) act = `<span class="badge info">En lista de espera</span>`;
  else if (full) act = `<button class="btn sm ghost" data-act="reserve" data-v="${c.id}">Lista de espera</button>`;
  return `<div class="slot"><div class="time">${c.time}</div>
    <div><h4>${c.name}</h4><small>${c.ins} · ${money(c.price)}</small></div>
    <div class="cup">${full ? 'Clase llena' : left + ' cupos disponibles'}<div class="bar ${full ? 'full' : ''}"><i style="width:${c.booked / c.cap * 100}%"></i></div></div>
    <div class="act">${act}</div></div>`;
}
function clientRes() {
  const mine = state.classes.filter(c => state.reservations.includes(c.id)).sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time));
  const wl = state.classes.filter(c => state.waitlist.includes(c.id));
  const row = (c, extra) => `<div class="res"><div><b>${c.name}</b><br><small class="muted">${longDate(c.date)} · ${c.time} · ${c.ins}</small></div>${extra}</div>`;
  return `<h2>Mis reservas</h2><p class="sub">Tus próximas clases y listas de espera.</p>
  ${mine.length ? mine.map(c => row(c, `<button class="btn sm ghost" data-act="cancel" data-v="${c.id}">Cancelar</button>`)).join('') : '<div class="empty">Aún no tienes reservas.<br><br><button class="btn sm" data-act="go" data-v="classes">Ver clases</button></div>'}
  ${wl.length ? `<h3 class="section-title">Lista de espera</h3>` + wl.map(c => row(c, `<span class="badge info">Posición ${c.id % 4 + 1}</span>`)).join('') : ''}`;
}

/* ---------- Reserva / pago ---------- */
let pending = null, method = 'Tarjeta';
function startReserve(id) {
  const c = state.classes.find(x => x.id === id);
  if (c.booked >= c.cap) {
    state.waitlist.push(id); render();
    return toast('Te agregamos a la lista de espera. Te avisaremos si se libera un cupo.');
  }
  pending = { type: 'class', id }; method = 'Tarjeta';
  checkout(c.name, `${longDate(c.date)} · ${c.time}`, c.price);
}
function startPlan(id) {
  const p = PLANS.find(x => x.id === id);
  pending = { type: 'plan', id }; method = 'Tarjeta';
  checkout(p.name, 'Cobro mensual', p.price);
}
function checkout(title, sub, amount) {
  openModal(`<h3>${amount ? 'Confirmar y pagar' : 'Confirmar reserva'}</h3><p class="sub">${title} · ${sub}</p>
    <div class="summary"><span>Total</span><span>${amount ? '$' + amount.toLocaleString('es-CL') : 'Incluida en tu plan'}</span></div>
    ${amount ? `<div class="methods">${['Tarjeta', 'WebPay', 'Transferencia'].map(m => `<button class="method ${m === method ? 'on' : ''}" data-act="method" data-v="${m}" data-amt="${amount}" data-t="${title}" data-s="${sub}">${m}</button>`).join('')}</div>
    ${method === 'Tarjeta' ? `<div class="field"><label>Número de tarjeta</label><input placeholder="4242 4242 4242 4242"></div><div class="row2"><div class="field"><label>Vence</label><input placeholder="MM/AA"></div><div class="field"><label>CVV</label><input placeholder="123"></div></div>` : `<p class="muted" style="font-size:13px;margin-bottom:16px">Serás redirigido a ${method} para completar el pago (simulado).</p>`}` : ''}
    <div class="modal-actions"><button class="btn ghost" data-act="close">Cancelar</button><button class="btn" data-act="pay">${amount ? 'Pagar $' + amount.toLocaleString('es-CL') : 'Confirmar'}</button></div>`);
}
function completePay() {
  if (pending.type === 'class') {
    const c = state.classes.find(x => x.id === pending.id);
    c.booked++; state.reservations.push(c.id);
    openModal(`<div class="ok-mark">✓</div><h3 style="text-align:center">¡Reserva confirmada!</h3><p class="sub" style="text-align:center;margin-top:6px">${c.name}<br>${longDate(c.date)} · ${c.time}</p><div class="modal-actions" style="justify-content:center"><button class="btn" data-act="close">Listo</button></div>`);
  } else {
    state.plan = pending.id; state.status = 'Activa'; state.expires = key(addDays(TODAY, 30));
    openModal(`<div class="ok-mark">✓</div><h3 style="text-align:center">Plan actualizado</h3><p class="sub" style="text-align:center;margin-top:6px">Tu membresía quedó activa por 30 días.</p><div class="modal-actions" style="justify-content:center"><button class="btn" data-act="close">Listo</button></div>`);
  }
  render();
}

/* ---------- Administrador ---------- */
const ICONS = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  chart: '<path d="M18 20V10M12 20V4M6 20v-6"/>',
  bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0"/>',
  box: '<path d="M21 8l-9-5-9 5v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  scan: '<path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2M7 12h10"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
};
const ic = n => `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[n]}</svg>`;
const initials = n => n.split(' ').map(w => w[0]).slice(0, 2).join('');
const ADMIN_NAV = [['dash', 'Dashboard', 'grid', 'Principal'], ['courses', 'Cursos', 'calendar', 'Gestión'], ['resrc', 'Recursos', 'box', 'Gestión'], ['users', 'Usuarios', 'users', 'Gestión'], ['report', 'Reportes', 'chart', 'Análisis'], ['alerts', 'Alertas', 'bell', 'Análisis']];
const STAFF_NAV = [['day', 'Mi jornada', 'clock', 'Trabajo'], ['scan', 'Validar acceso', 'scan', 'Trabajo']];

function shell(nav, view, sub, who, role, body) {
  const items = nav.map(([k, l]) => [l, 'go', k, k, k === 'alerts' && state.alerts.length ? state.alerts.length : '']);
  const groups = [];
  nav.forEach(([, , , g], i) => {
    if (!groups.length || groups[groups.length - 1].label !== g) groups.push({ label: g, items: [] });
    groups[groups.length - 1].items.push(items[i]);
  });
  groups.push({ label: 'Sesión', items: [['Cerrar sesión', 'logout', '']] });
  const admin = state.role === 'admin';
  const cur = nav.find(n => n[0] === view);
  const cfg = { home: ['go', admin ? 'dash' : 'day'], active: view, links: items, user: { name: who, role }, groups, cta: admin ? ['+ Agregar curso', 'editcourse', '0'] : ['Validar acceso', 'go', 'scan'] };
  return `${siteHeader(cfg)}<div class="app-main"><div class="content"><div class="crumb">${sub} <i>/</i> <b>${cur[1]}</b></div>${body}</div></div>`;
}
function adminView() {
  const v = { dash: adminDash, courses: adminCourses, report: adminReport, alerts: adminAlerts, resrc: adminResrc, users: adminUsers }[state.view]();
  return shell(ADMIN_NAV, state.view, 'Administración', 'Carolina Vega', 'Administradora · Sede Centro', v);
}

const SEV = { high: ['Alta', 'bad'], mid: ['Media', 'warn'], low: ['Baja', 'info'] };

function adminDash() {
  const pct = Math.round(state.aforo / state.aforoMax * 100);
  const k = key(TODAY);
  const today = state.classes.filter(c => c.date === k).sort((a, b) => a.time.localeCompare(b.time));
  const hours = [['6h', 12], ['8h', 48], ['10h', 92], ['12h', 120], ['14h', 88], ['16h', 110], ['18h', 172], ['20h', 150], ['22h', 40]];
  const pts = hours.map(([, v], i) => [Math.round(i * 600 / (hours.length - 1)), Math.round(170 - v / 200 * 160)]);
  const line = 'M' + pts.map(p => p.join(',')).join(' L');
  const spark = [30, 42, 38, 55, 50, 68, 72].map((v, i) => `${i * 16},${34 - v / 80 * 30}`).join(' ');
  return `<div class="head-row"><div><h2>Dashboard</h2><p>Resumen en tiempo real de la sede</p></div><span class="live">En vivo</span></div>
  <div class="kpis">
    <div class="card kpi"><div class="ring-wrap">
      <div class="ring"><svg viewBox="0 0 120 120"><circle class="ring-bg" cx="60" cy="60" r="52"/><circle id="ring" class="ring-fg" cx="60" cy="60" r="52" transform="rotate(-90 60 60)" stroke-dasharray="326.7" stroke-dashoffset="${326.7 * (1 - pct / 100)}"/></svg><div class="ring-txt"><b id="aforo-p">${pct}%</b></div></div>
      <div><div class="lbl">Aforo actual</div><div class="val"><span id="aforo-n">${state.aforo}</span> <small>personas</small></div><span class="badge ${pct >= 85 ? 'bad' : pct >= 70 ? 'warn' : 'ok'}">${pct >= 85 ? 'Aforo alto' : 'Aforo normal'}</span><p class="muted" style="font-size:12px;margin-top:8px">Capacidad máxima ${state.aforoMax}</p></div></div></div>
    <div class="card kpi"><div class="lbl">Accesos hoy</div><div class="val">638</div><svg class="spark" viewBox="0 0 96 36"><polyline points="${spark}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg><span class="badge ok">+8% vs ayer</span></div>
    <div class="card kpi"><div class="lbl">Membresías activas</div><div class="val">1.284</div><p class="muted" style="font-size:13px;margin-bottom:10px">de 1.402 registradas</p><span class="badge warn">37 por vencer</span></div>
  </div>
  <div class="two">
    <div class="card"><div class="card-h"><h3>Aforo durante el día</h3><span class="muted" style="font-size:13px">Personas en sala</span></div>
      <svg class="area" viewBox="0 0 600 180" preserveAspectRatio="none"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style="stop-color:var(--accent);stop-opacity:.22"/><stop offset="1" style="stop-color:var(--accent);stop-opacity:0"/></linearGradient></defs>
      <path d="M0,50H600M0,110H600" stroke="var(--line)" stroke-width="1" stroke-dasharray="4 5" fill="none"/><path d="${line} L600,170 L0,170Z" fill="url(#g)"/><path d="${line}" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>
      <div class="area-x">${hours.map(h => `<span>${h[0]}</span>`).join('')}</div></div>
    <div class="card"><div class="card-h"><h3>Alertas recientes</h3><button class="link" data-act="go" data-v="alerts">Ver todas</button></div>
      ${state.alerts.slice(0, 3).map(a => `<div class="alert"><span class="bubble ${a.lvl}">${ic('bell')}</span><div class="txt"><b style="font-size:14px">${a.t}</b><br><small>${a.s}</small></div></div>`).join('') || '<div class="empty">Sin alertas</div>'}</div>
  </div>
  <div class="card"><div class="card-h"><h3>Clases de hoy</h3></div><table><tr><th>Hora</th><th>Clase</th><th>Instructor</th><th>Ocupación</th><th>Estado</th></tr>
    ${today.map(c => `<tr><td><b>${c.time}</b></td><td>${c.name}</td><td class="muted">${c.ins}</td><td><div class="occ"><div class="bar ${c.booked >= c.cap ? 'full' : ''}"><i style="width:${c.booked / c.cap * 100}%"></i></div>${c.booked}/${c.cap}</div></td><td>${c.booked >= c.cap ? '<span class="badge bad">Llena</span>' : '<span class="badge ok">Disponible</span>'}</td></tr>`).join('')}</table></div>`;
}
function adminCourses() {
  const all = state.classes;
  const list = all.slice().sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time)).slice(0, 14);
  const fd = k => { const d = parse(k); return `${DAYS[d.getDay()]} ${pad(d.getDate())}/${pad(d.getMonth() + 1)}`; };
  return `<div class="head-row"><div><h2>Cursos</h2><p>Gestiona horarios, cupos y precios.</p></div><button class="btn" data-act="editcourse" data-v="0">+ Agregar curso</button></div>
  <div class="stats"><div class="stat"><b>${all.length}</b>Clases programadas</div><div class="stat"><b>${all.filter(c => c.booked >= c.cap).length}</b>Clases llenas</div><div class="stat"><b>${all.reduce((s, c) => s + c.booked, 0)}</b>Reservas totales</div></div>
  <div class="card"><table><tr><th>Curso</th><th>Fecha y hora</th><th>Cupos</th><th>Precio</th><th></th></tr>
  ${list.map(c => `<tr><td><b>${c.name}</b><br><span class="pill">${c.type}</span> <small class="muted">${c.ins}</small></td><td>${fd(c.date)}<br><small class="muted">${c.time}</small></td>
  <td><div class="occ"><div class="bar ${c.booked >= c.cap ? 'full' : ''}"><i style="width:${c.booked / c.cap * 100}%"></i></div>${c.booked}/${c.cap}</div></td><td>${c.price ? '$' + c.price.toLocaleString('es-CL') : '<span class="muted">Incluida</span>'}</td>
  <td style="text-align:right;white-space:nowrap"><button class="link" data-act="editcourse" data-v="${c.id}">Editar</button><button class="link red" data-act="delcourse" data-v="${c.id}">Eliminar</button></td></tr>`).join('')}</table></div>`;
}
function courseForm(id) {
  const c = id ? state.classes.find(x => x.id === id) : { name: '', type: 'Spinning', date: key(TODAY), time: '18:00', cap: 20, price: 0, ins: '' };
  openModal(`<h3>${id ? 'Editar curso' : 'Agregar curso'}</h3><p class="sub">Completa los datos de la clase.</p>
  <form data-form="course" data-id="${id}">
    <div class="field"><label>Nombre</label><input name="name" required value="${c.name}" placeholder="Ej: Spinning 45'"></div>
    <div class="row2"><div class="field"><label>Actividad</label><select name="type">${ACTIVITIES.map(a => `<option ${a === c.type ? 'selected' : ''}>${a}</option>`).join('')}</select></div>
    <div class="field"><label>Instructor</label><input name="ins" required value="${c.ins}" placeholder="Nombre"></div></div>
    <div class="row2"><div class="field"><label>Fecha</label><input type="date" name="date" required value="${c.date}"></div><div class="field"><label>Hora</label><input type="time" name="time" required value="${c.time}"></div></div>
    <div class="row2"><div class="field"><label>Cupos máximos</label><input type="number" min="1" name="cap" required value="${c.cap}"></div><div class="field"><label>Precio (CLP)</label><input type="number" min="0" step="500" name="price" value="${c.price}"></div></div>
    <div class="modal-actions"><button type="button" class="btn ghost" data-act="close">Cancelar</button><button class="btn">Guardar</button></div></form>`);
}
function adminReport() {
  const data = state.reportRange === 'Semana' ? [['Lun', 820], ['Mar', 790], ['Mié', 860], ['Jue', 740], ['Vie', 910], ['Sáb', 520], ['Dom', 310]] : [['Sem 1', 4900], ['Sem 2', 5200], ['Sem 3', 4750], ['Sem 4', 5480]];
  const max = Math.max(...data.map(d => d[1]));
  return `<div class="head-row"><div><h2>Reportes</h2><p>Accesos registrados por periodo.</p></div><div style="display:flex;gap:12px;align-items:center"><div class="segment" style="margin:0">${['Semana', 'Mes'].map(r => `<button class="${state.reportRange === r ? 'on' : ''}" data-act="range" data-v="${r}">${r}</button>`).join('')}</div><button class="btn ghost sm" data-act="export">Exportar CSV</button></div></div>
  <div class="card" style="margin-bottom:20px"><div class="card-h"><h3>Accesos</h3><span class="muted" style="font-size:13px">Total: ${data.reduce((s, d) => s + d[1], 0).toLocaleString('es-CL')}</span></div>
    <div class="chart">${data.map(([l, v]) => `<div><span>${v.toLocaleString('es-CL')}</span><i class="${v === max ? 'hi' : ''}" style="height:${v / max * 78}%"></i>${l}</div>`).join('')}</div></div>
  <div class="kpis" style="grid-template-columns:repeat(3,1fr)">
    <div class="card kpi"><div class="lbl">Clase más reservada</div><div class="val" style="font-size:22px">Spinning 18:30</div><span class="badge ok">95% de ocupación</span></div>
    <div class="card kpi"><div class="lbl">Hora punta</div><div class="val" style="font-size:22px">18:00 – 20:00</div><span class="badge warn">Aforo sobre 85%</span></div>
    <div class="card kpi"><div class="lbl">Ingresos del mes</div><div class="val" style="font-size:22px">$31,2 M</div><span class="badge ok">+12% vs mes anterior</span></div></div>`;
}
function adminAlerts() {
  return `<div class="head-row"><div><h2>Alertas</h2><p>Eventos que requieren tu atención.</p></div></div>
  <div class="card">${state.alerts.length ? state.alerts.map(a => `<div class="alert"><span class="bubble ${a.lvl}">${ic('bell')}</span><div class="txt"><b>${a.t}</b><br><small>${a.s}</small></div><span class="badge ${SEV[a.lvl][1]}">${SEV[a.lvl][0]}</span><button class="btn ghost sm" data-act="resolve" data-v="${a.id}">Resolver</button></div>`).join('') : '<div class="empty"><div class="ok-mark">✓</div>Todo en orden, no hay alertas pendientes.</div>'}</div>`;
}
function adminResrc() {
  const rows = state.resources[state.resTab];
  const ops = rows.filter(r => r[2] === 'Operativa').length;
  return `<div class="head-row"><div><h2>Recursos</h2><p>Máquinas, deportes y espacios del centro.</p></div><button class="btn" data-act="addres">+ Agregar</button></div>
  <div class="segment">${Object.keys(state.resources).map(r => `<button class="${state.resTab === r ? 'on' : ''}" data-act="restab" data-v="${r}">${r}</button>`).join('')}</div>
  <div class="stats"><div class="stat"><b>${ops}</b>Operativas</div><div class="stat"><b>${rows.length - ops}</b>En mantención</div></div>
  <div class="card"><table><tr><th>Nombre</th><th>Detalle</th><th>Estado</th><th></th></tr>
  ${rows.map((r, i) => `<tr><td><div class="person"><span class="bubble low">${ic('box')}</span><b>${r[0]}</b></div></td><td class="muted">${r[1]}</td><td>${stateBadge(r[2])}</td><td style="text-align:right"><button class="link" data-act="togres" data-v="${i}">${r[2] === 'Operativa' ? 'Enviar a mantención' : 'Marcar operativa'}</button></td></tr>`).join('')}</table></div>`;
}
function adminUsers() {
  const n = s => state.users.filter(u => u[3] === s).length;
  return `<div class="head-row"><div><h2>Usuarios</h2><p>Socios y estado de membresía.</p></div></div>
  <div class="stats"><div class="stat"><b>${n('Activa')}</b>Activas</div><div class="stat"><b>${n('Vencida')}</b>Vencidas</div><div class="stat"><b>${n('Congelada')}</b>Congeladas</div></div>
  <div class="toolbar"><input id="uq" placeholder="Buscar por nombre o correo" value="${state.userQ}"><select id="uf">${['Todos', 'Activa', 'Vencida', 'Congelada'].map(s => `<option ${s === state.userF ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
  <div class="card"><table><tr><th>Socio</th><th>Plan</th><th>Estado</th><th></th></tr><tbody id="utbody">${userRows()}</tbody></table></div>`;
}
function userRows() {
  const q = state.userQ.toLowerCase();
  return state.users.map((u, i) => [u, i]).filter(([u]) => (state.userF === 'Todos' || u[3] === state.userF) && (u[0] + u[1]).toLowerCase().includes(q))
    .map(([u, i]) => `<tr><td><div class="person"><span class="avatar sm">${initials(u[0])}</span><div><b>${u[0]}</b><br><small class="muted">${u[1]}</small></div></div></td><td><span class="pill">${u[2]}</span></td><td>${statusBadge(u[3])}</td>
    <td style="text-align:right"><button class="link" data-act="freeze" data-v="${i}">${u[3] === 'Congelada' ? 'Reactivar' : 'Congelar'}</button></td></tr>`).join('') || '<tr><td colspan="4" class="empty">Sin resultados</td></tr>';
}

/* ---------- Staff (instructores) ---------- */
const STAFF = {
  monitor: { label: 'Monitor de sala', desc: 'Guía general en sala: uso de máquinas y dudas de los socios.', foco: 'Zona',
    agenda: [['07:00', 'Apertura y revisión de máquinas'], ['10:00', 'Turno guiado · Sala de máquinas'], ['16:00', 'Inducción a nuevos socios']],
    people: [['Matías Fuentes', 'Zona de pesas', 'Duda técnica', 40], ['Daniela Vera', 'Cardio', 'Inducción', 65]] },
  personal: { label: 'Entrenador personal', desc: 'Evalúa el estado físico y diseña un plan exclusivo para cada alumno.', foco: 'Plan',
    agenda: [['08:00', 'Sesión 1:1 · Javiera Pinto'], ['11:00', 'Evaluación física · nuevo alumno'], ['17:30', 'Sesión 1:1 · Sebastián Rojas']],
    people: [['Javiera Pinto', 'Hipertrofia · 4 días', 'Plan al día', 80], ['Sebastián Rojas', 'Pérdida de grasa', 'Actualizar plan', 45]] },
  coach: { label: 'Coach', desc: 'Motiva, da seguimiento diario y ayuda a cumplir metas a largo plazo.', foco: 'Objetivo',
    agenda: [['09:00', 'Seguimiento semanal · grupo A'], ['13:00', 'Llamada de motivación · 3 socios'], ['19:00', 'Revisión de metas mensuales']],
    people: [['Valentina Muñoz', 'Correr 10K', 'En camino', 70], ['Nicolás Araya', 'Constancia 3x/sem', 'Sin asistir hace 6 días', 25]] },
  prep: { label: 'Preparador físico', desc: 'Rendimiento atlético, fuerza y preparación para una meta deportiva.', foco: 'Meta',
    agenda: [['07:30', 'Test de fuerza · equipo fútbol'], ['12:30', 'Funcional HIIT'], ['19:00', 'Fútbol 7 · preparación física']],
    people: [['Pablo Soto', 'Pretemporada fútbol', 'Carga alta', 85], ['Camila Díaz', 'Maratón 42K', 'Semana de descarga', 55]] },
};
function staffView() {
  const body = state.view === 'scan' ? staffScan() : staffDay();
  return shell(STAFF_NAV, state.view, 'Equipo', 'Tomás Herrera', STAFF[state.staffRole].label, body);
}
function staffDay() {
  const s = STAFF[state.staffRole];
  const doneN = s.agenda.filter((_, i) => state.done[state.staffRole + i]).length;
  return `<div class="hero"><span class="avatar">TH</span><div><h2>Hola, Tomás</h2><p>${s.label} · ${s.desc}</p></div>
    <div class="hero-stats"><div><b>${s.agenda.length}</b><small>Sesiones hoy</small></div><div><b>${doneN}</b><small>Completadas</small></div><div><b>${s.people.length}</b><small>Socios</small></div></div></div>
  <div class="segment">${Object.entries(STAFF).map(([k, v]) => `<button class="${state.staffRole === k ? 'on' : ''}" data-act="srole" data-v="${k}">${v.label}</button>`).join('')}</div>
  <div class="two" style="grid-template-columns:1.15fr 1fr">
    <div class="card"><div class="card-h"><h3>Agenda de hoy</h3><span class="muted" style="font-size:13px">${doneN}/${s.agenda.length} listas</span></div><div class="tl">
      ${s.agenda.map((a, i) => { const id = state.staffRole + i, d = state.done[id]; return `<div class="tl-item ${d ? 'done' : ''}"><div class="tl-time">${a[0]}</div><div class="tl-txt">${a[1]}</div><input type="checkbox" class="check" data-act="done" data-v="${id}" ${d ? 'checked' : ''} title="Marcar como completada"></div>`; }).join('')}</div></div>
    <div class="card"><div class="card-h"><h3>Socios a cargo</h3></div>
      ${s.people.map(p => `<div class="member"><span class="avatar sm">${initials(p[0])}</span><div class="info"><b>${p[0]}</b><br><small class="muted">${s.foco}: ${p[1]}</small><div class="bar"><i style="width:${p[3]}%"></i></div></div><span class="badge ${p[3] < 50 ? 'warn' : 'ok'}">${p[2]}</span></div>`).join('')}</div>
  </div>`;
}
function staffScan() {
  state.scans = state.scans || [['ok', 'Javiera Pinto', 'Plan Pro', '08:42'], ['ok', 'Daniela Vera', 'Plan Básico', '08:39'], ['bad', 'Matías Fuentes', 'Membresía vencida', '08:31']];
  return `<div class="head-row"><div><h2>Validar acceso</h2><p>Simula la lectura del QR de un socio en el torniquete.</p></div></div>
  <div class="two" style="grid-template-columns:1fr 1fr">
    <div class="card scan"><div class="scanner"><i class="c1"></i><i class="c2"></i><i class="c3"></i><i class="c4"></i><span>Apunta el código QR</span></div><button class="btn" data-act="scan">Simular lectura</button><div id="scan-res"></div></div>
    <div class="card"><div class="card-h"><h3>Últimos accesos</h3></div><div id="scan-list">${scanList()}</div></div>
  </div>`;
}
function scanList() {
  return state.scans.slice(0, 6).map(s => `<div class="member"><span class="avatar sm">${initials(s[1])}</span><div class="info"><b>${s[1]}</b><br><small class="muted">${s[2]}</small></div><div style="text-align:right"><span class="badge ${s[0] === 'ok' ? 'ok' : 'bad'}">${s[0] === 'ok' ? 'Permitido' : 'Denegado'}</span><br><small class="muted">${s[3]}</small></div></div>`).join('');
}
function doScan() {
  const outcomes = [['ok', 'Valentina Muñoz', 'Plan Black'], ['ok', 'Javiera Pinto', 'Plan Pro'], ['bad', 'Matías Fuentes', 'Membresía vencida'], ['bad', 'Nicolás Araya', 'Membresía congelada']];
  const o = outcomes[Math.floor(Math.random() * outcomes.length)];
  const now = new Date(), hm = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  state.scans.unshift([o[0], o[1], o[2], hm]);
  $('#scan-res').innerHTML = `<div class="result ${o[0]}"><span class="r-ic">${o[0] === 'ok' ? '✓' : '✕'}</span><div><b>${o[0] === 'ok' ? 'Acceso permitido' : 'Acceso denegado'}</b><small>${o[1]} · ${o[2]}${o[0] === 'ok' ? ' · 0,04 s' : ''}</small></div></div>`;
  $('#scan-list').innerHTML = scanList();
}

/* ---------- Eventos ---------- */
document.addEventListener('click', e => {
  if (e.target.id === 'modal') return closeModal();
  const el = e.target.closest('[data-act]'); if (!el) return;
  const v = el.dataset.v, a = el.dataset.act;
  if (a !== 'menu' && el.closest('#drawer')) toggleDrawer(false);
  switch (a) {
    case 'toauth': state.page = 'auth'; state.authTab = v; render(); break;
    case 'tohome': state.page = 'home'; render(); break;
    case 'scrollto': { const go2 = () => { const t = document.getElementById(v); if (t) t.scrollIntoView({ behavior: 'smooth' }); }; if (document.getElementById(v)) go2(); else { state.page = 'home'; render(); setTimeout(go2, 60); } break; }
    case 'menu': toggleDrawer(); break;
    case 'cookies': state.cookies = true; { const c = $('.cookie'); if (c) c.remove(); } break;
    case 'chat': toast('Chat de ayuda (simulado)'); break;
    case 'authtab': state.authTab = v; render(); break;
    case 'login': login(v); break;
    case 'logout': state.role = null; state.page = 'home'; state.authTab = 'login'; render(); break;
    case 'go': go(v); break;
    case 'day': state.day = +v; render(); break;
    case 'filter': state.filter = v; render(); break;
    case 'reserve': startReserve(+v); break;
    case 'buyplan': startPlan(v); break;
    case 'cancel': { const c = state.classes.find(x => x.id === +v); c.booked--; state.reservations = state.reservations.filter(x => x !== +v); render(); toast('Reserva cancelada'); break; }
    case 'method': method = v; checkout(el.dataset.t, el.dataset.s, +el.dataset.amt); break;
    case 'pay': completePay(); break;
    case 'close': closeModal(); break;
    case 'editcourse': courseForm(+v); break;
    case 'delcourse': state.classes = state.classes.filter(x => x.id !== +v); render(); toast('Curso eliminado'); break;
    case 'range': state.reportRange = v; render(); break;
    case 'export': toast('Reporte exportado (simulado)'); break;
    case 'resolve': state.alerts = state.alerts.filter(x => x.id !== +v); render(); toast('Alerta resuelta'); break;
    case 'restab': state.resTab = v; render(); break;
    case 'togres': { const r = state.resources[state.resTab][+v]; r[2] = r[2] === 'Operativa' ? 'Mantención' : 'Operativa'; render(); break; }
    case 'addres': openModal(`<h3>Agregar a ${state.resTab}</h3><p class="sub">Registra un nuevo elemento.</p><form data-form="res"><div class="field"><label>Nombre</label><input name="n" required></div><div class="field"><label>Detalle</label><input name="d" required></div><div class="modal-actions"><button type="button" class="btn ghost" data-act="close">Cancelar</button><button class="btn">Guardar</button></div></form>`); break;
    case 'freeze': { const u = state.users[+v]; u[3] = u[3] === 'Congelada' ? 'Activa' : 'Congelada'; $('#utbody').innerHTML = userRows(); toast('Estado actualizado'); break; }
    case 'srole': state.staffRole = v; render(); break;
    case 'done': state.done[v] = el.checked; render(); break;
    case 'scan': doScan(); break;
  }
});
document.addEventListener('submit', e => {
  e.preventDefault();
  const f = e.target, kind = f.dataset.form;
  if (kind === 'auth') { login('client'); toast('Bienvenida a FitLife'); }
  if (kind === 'course') {
    const d = Object.fromEntries(new FormData(f)), id = +f.dataset.id;
    d.cap = +d.cap; d.price = +d.price || 0;
    if (id) Object.assign(state.classes.find(x => x.id === id), d);
    else state.classes.push({ id: nextId++, booked: 0, ...d });
    closeModal(); render(); toast('Curso guardado');
  }
  if (kind === 'res') {
    const d = new FormData(f); state.resources[state.resTab].push([d.get('n'), d.get('d'), 'Operativa']);
    closeModal(); render(); toast('Elemento agregado');
  }
});
document.addEventListener('input', e => {
  if (e.target.id === 'uq') { state.userQ = e.target.value; $('#utbody').innerHTML = userRows(); }
});
document.addEventListener('change', e => {
  if (e.target.id === 'uf') { state.userF = e.target.value; $('#utbody').innerHTML = userRows(); }
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') toggleDrawer(false); });
/* Aforo en vivo (simulado) */
setInterval(() => {
  if (state.role !== 'admin' || state.view !== 'dash' || !$('#aforo-n')) return;
  state.aforo = Math.max(60, Math.min(state.aforoMax - 4, state.aforo + Math.round(Math.random() * 6 - 3)));
  const pct = Math.round(state.aforo / state.aforoMax * 100);
  $('#aforo-n').textContent = state.aforo; $('#aforo-p').textContent = pct + '%';
  $('#ring').style.strokeDashoffset = 326.7 * (1 - pct / 100);
}, 2500);

render();
