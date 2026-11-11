export function createProfessionalViews({ state, esc, dateOnly, dateTime }) {
  const memberOptions = (selected = '') => {
    const members = state.data.professional_workspace?.assigned_members || [];
    return `<label>Socio asignado<select name="socio_id" required><option value="">Selecciona un socio</option>${members.map(member => `<option value="${member.socio_id}" ${String(member.socio_id) === String(selected) ? 'selected' : ''}>${esc(member.nombre)}</option>`).join('')}</select></label>`;
  };

  const card = (title, items, columns, render) => `<section class="card"><div class="card-h"><h3>${esc(title)}</h3></div>${items.length ? `<div class="table-wrap"><table><thead><tr>${columns.map(column => `<th>${esc(column)}</th>`).join('')}</tr></thead><tbody>${items.map(render).join('')}</tbody></table></div>` : '<div class="empty">Aún no hay registros.</div>'}</section>`;
  const formStart = (action, title, fields) => `<form class="card data-form professional-form" data-professional-form><input type="hidden" name="accion" value="${action}"><h3>${esc(title)}</h3><div class="form-grid">${memberOptions()}${fields}</div><button class="button button-dark" type="submit">Guardar registro</button></form>`;
  const notesField = '<label class="form-span">Observaciones<textarea name="observaciones" rows="2"></textarea></label>';

  function exerciseRows() {
    const exerciseRow = () => `<fieldset class="form-subgrid exercise-row" data-exercise-row>
      <label>Ejercicio<input name="ejercicio_nombre" required maxlength="120"></label>
      <label>Series<input name="ejercicio_series" type="number" min="1" max="100" required></label>
      <label>Repeticiones<input name="ejercicio_repeticiones" required maxlength="40"></label>
      <label>Carga (kg)<input name="ejercicio_carga_kg" type="number" min="0" step="0.01"></label>
      <label>Descanso (segundos)<input name="ejercicio_descanso_segundos" type="number" min="0" max="86400"></label>
      <label>Duración (segundos)<input name="ejercicio_duracion_segundos" type="number" min="0" max="86400"></label>
      <label class="form-span">Notas del ejercicio<input name="ejercicio_observaciones" maxlength="1000"></label>
      <button class="link link-danger" type="button" data-remove-exercise>Quitar ejercicio</button>
    </fieldset>`;
    return `<div data-exercise-list>${exerciseRow()}</div><button class="link" type="button" data-add-exercise>+ Agregar ejercicio</button>`;
  }

  function routineRows() {
    const routineRow = () => `<fieldset class="form-section form-span" data-routine-row>
      <legend>Bloque de rutina</legend>
      <label>Día o bloque<input name="rutina_dia" required maxlength="40" placeholder="Ej. Día 1 · Tren superior"></label>
      ${exerciseRows()}
      <button class="link link-danger" type="button" data-remove-routine>Quitar bloque</button>
    </fieldset>`;
    return `<div class="form-span"><h4>Rutinas por día o bloque</h4><div data-routine-list>${routineRow()}</div><button class="link" type="button" data-add-routine>+ Agregar día o bloque</button></div>`;
  }

  function personalTrainer() {
    const data = state.data.professional_workspace || {};
    return `<div class="notice">Los socios visibles son los que Administración asignó a tu perfil.</div>
      ${formStart('EVALUACION_INICIAL', 'Evaluación inicial', `<label>Objetivo del socio<textarea name="objetivo" required rows="2"></textarea></label><label>Condición física inicial<textarea name="condicion_inicial" required rows="2"></textarea></label><label class="form-span">Antecedentes relevantes<textarea name="antecedentes" rows="2"></textarea></label>`)}
      ${formStart('PLAN_ENTRENAMIENTO', 'Crear plan y rutina', `<label>Título del plan<input name="titulo" required maxlength="120"></label><label>Objetivo<textarea name="objetivo" required rows="2"></textarea></label><label>Fecha de inicio<input name="fecha_inicio" type="date" required></label><label>Fecha de término<input name="fecha_fin" type="date"></label>${routineRows()}${notesField}`)}
      ${formStart('SESION_ENTRENAMIENTO', 'Registrar sesión realizada', `<label>Plan asociado<select name="plan_id"><option value="">Sin plan asociado</option>${(data.plans || []).map(plan => `<option value="${plan.plan_id}">${esc(plan.titulo)} · ${esc(plan.socio)}</option>`).join('')}</select></label><label>Duración (minutos)<input name="duracion_minutos" type="number" min="1" max="1440"></label>${notesField}`)}
      ${formStart('PROGRESO', 'Registrar avance de objetivo', `<label>Objetivo evaluado<input name="objetivo" required></label><label>Avance (%)<input name="progreso" type="number" min="0" max="100" required></label>${notesField}`)}
      ${card('Evaluaciones iniciales', data.evaluations || [], ['Socio', 'Objetivo', 'Condición inicial', 'Antecedentes', 'Fecha'], item => `<tr><td>${esc(item.socio)}</td><td>${esc(item.objetivo)}</td><td>${esc(item.condicion_inicial)}</td><td>${esc(item.antecedentes || '—')}</td><td>${dateTime(item.evaluada_en)}</td></tr>`)}
      ${card('Planes y rutinas', data.plans || [], ['Socio', 'Plan', 'Objetivo', 'Rutinas y ejercicios', 'Vigencia'], item => `<tr><td>${esc(item.socio)}</td><td>${esc(item.titulo)}</td><td>${esc(item.objetivo)}</td><td>${(item.rutinas || []).map(routine => `<strong>${esc(routine.dia)}</strong>${(routine.ejercicios || []).map(exercise => `<small>${esc(exercise.nombre)} · ${exercise.series} × ${esc(exercise.repeticiones)}${exercise.carga_kg ? ` · ${esc(exercise.carga_kg)} kg` : ''}</small>`).join('')}`).join('')}</td><td>${dateOnly(item.fecha_inicio)}${item.fecha_fin ? ` – ${dateOnly(item.fecha_fin)}` : ''}</td></tr>`)}
      ${card('Sesiones realizadas', data.sessions || [], ['Socio', 'Fecha', 'Plan', 'Duración', 'Observaciones'], item => `<tr><td>${esc(item.socio)}</td><td>${dateTime(item.realizada_en)}</td><td>${esc((data.plans || []).find(plan => Number(plan.plan_id) === Number(item.plan_id))?.titulo || '—')}</td><td>${item.duracion_minutos ? `${item.duracion_minutos} min` : '—'}</td><td>${esc(item.observaciones || '—')}</td></tr>`)}
      ${card('Historial de progreso', data.progress || [], ['Socio', 'Objetivo', 'Avance', 'Observaciones', 'Fecha'], item => `<tr><td>${esc(item.socio)}</td><td>${esc(item.objetivo)}</td><td>${item.progreso}%</td><td>${esc(item.observaciones || '—')}</td><td>${dateTime(item.registrado_en)}</td></tr>`)}`;
  }

  function coach() {
    const data = state.data.professional_workspace || {};
    return `<div class="notice">Los socios visibles son los que Administración asignó a tu perfil.</div>
      ${formStart('OBJETIVO', 'Definir objetivo y plan de acción', `<label>Objetivo<input name="titulo" required maxlength="120"></label><label>Fecha objetivo<input name="fecha_objetivo" type="date"></label><label>Asistencia esperada (días por semana)<input name="asistencias_semanales" type="number" min="1" max="7"></label><label class="form-span">Plan de acción<textarea name="descripcion" rows="3"></textarea></label>`)}
      ${formStart('SESION_COACHING', 'Registrar sesión de acompañamiento', `<label>Objetivo asociado<select name="objetivo_id"><option value="">Sin objetivo asociado</option>${(data.goals || []).map(goal => `<option value="${goal.objetivo_id}">${esc(goal.titulo)} · ${esc(goal.socio)}</option>`).join('')}</select></label><label>Adherencia (%)<input name="adherencia" type="number" min="0" max="100"></label><label class="form-span">Compromisos acordados<textarea name="compromisos" rows="2"></textarea></label>${notesField}`)}
      ${formStart('ESTADO_OBJETIVO', 'Actualizar estado de un objetivo', `<label>Objetivo<select name="objetivo_id" required><option value="">Selecciona un objetivo</option>${(data.goals || []).map(goal => `<option value="${goal.objetivo_id}">${esc(goal.titulo)} · ${esc(goal.socio)}</option>`).join('')}</select></label><label>Estado<select name="estado" required><option value="PENDIENTE">Pendiente</option><option value="EN_CURSO">En curso</option><option value="CUMPLIDO">Cumplido</option><option value="PAUSADO">Pausado</option></select></label>`)}
      ${card('Objetivos', data.goals || [], ['Socio', 'Objetivo', 'Plan de acción', 'Meta', 'Estado'], item => `<tr><td>${esc(item.socio)}</td><td>${esc(item.titulo)}</td><td>${esc(item.descripcion || '—')}</td><td>${item.fecha_objetivo ? dateOnly(item.fecha_objetivo) : '—'}${item.asistencias_semanales ? `<small>${item.asistencias_semanales} días de asistencia por semana</small>` : ''}</td><td>${esc(item.estado)}</td></tr>`)}
      ${card('Sesiones y adherencia', data.sessions || [], ['Socio', 'Fecha', 'Compromisos', 'Adherencia', 'Observaciones'], item => `<tr><td>${esc(item.socio)}</td><td>${dateTime(item.realizada_en)}</td><td>${esc(item.compromisos || '—')}</td><td>${item.adherencia === null ? '—' : `${item.adherencia}%`}</td><td>${esc(item.observaciones || '—')}</td></tr>`)}`;
  }

  function physicalTrainer() {
    const data = state.data.professional_workspace || {};
    return `<div class="notice">Los socios visibles son los que Administración asignó a tu perfil.</div>
      ${formStart('EVALUACION_FISICA', 'Registrar prueba o evaluación física', `<label>Prueba<input name="prueba" required maxlength="120" placeholder="Ej. Test de Cooper"></label><label>Capacidad<select name="capacidad" required><option value="RESISTENCIA">Resistencia</option><option value="FUERZA">Fuerza</option><option value="VELOCIDAD">Velocidad</option><option value="FLEXIBILIDAD">Flexibilidad</option><option value="COMPOSICION">Composición corporal</option><option value="OTRA">Otra</option></select></label><label>Resultado<input name="resultado" type="number" min="0" step="0.001" required></label><label>Unidad<input name="unidad" required maxlength="30" placeholder="Ej. segundos, kg, cm"></label>${notesField}`)}
      ${formStart('PLANIFICACION_FISICA', 'Diseñar planificación por etapas', `<label>Nombre del plan<input name="titulo" required maxlength="120"></label><label>Objetivo de rendimiento<textarea name="objetivo" required rows="2"></textarea></label><label>Etapa o período<input name="etapa" required maxlength="80" placeholder="Ej. Preparación general"></label><label>Fecha de inicio<input name="fecha_inicio" type="date" required></label><label>Fecha de término<input name="fecha_fin" type="date"></label><label>Volumen semanal<input name="volumen_semanal" type="number" min="0" step="0.01"></label><label>Intensidad (1 a 10)<input name="intensidad" type="number" min="1" max="10"></label>${notesField}`)}
      ${card('Evaluaciones y pruebas físicas', data.evaluations || [], ['Socio', 'Prueba', 'Capacidad', 'Resultado', 'Fecha', 'Observaciones'], item => `<tr><td>${esc(item.socio)}</td><td>${esc(item.prueba)}</td><td>${esc(item.capacidad)}</td><td>${esc(item.resultado)} ${esc(item.unidad)}</td><td>${dateTime(item.evaluada_en)}</td><td>${esc(item.observaciones || '—')}</td></tr>`)}
      ${card('Planificaciones y etapas', data.plans || [], ['Socio', 'Plan', 'Etapa', 'Objetivo', 'Período', 'Volumen / intensidad'], item => `<tr><td>${esc(item.socio)}</td><td>${esc(item.titulo)}</td><td>${esc(item.etapa)}</td><td>${esc(item.objetivo)}</td><td>${dateOnly(item.fecha_inicio)}${item.fecha_fin ? ` – ${dateOnly(item.fecha_fin)}` : ''}</td><td>${item.volumen_semanal ?? '—'} / ${item.intensidad ?? '—'}</td></tr>`)}`;
  }

  function teamView() {
    const specialty = state.data.professional_profile?.tipo;
    const titles = {
      PERSONAL_TRAINER: ['Entrenamiento personal', 'Evaluaciones, planes, rutinas y progreso de tus socios.'],
      COACH: ['Acompañamiento y constancia', 'Objetivos, compromisos, sesiones y adherencia de tus socios.'],
      PREPARADOR_FISICO: ['Evaluación y rendimiento físico', 'Pruebas, planificación por etapas y resultados de tus deportistas.'],
    };
    const [title, description] = titles[specialty] || ['Seguimiento profesional', ''];
    const members = state.data.professional_workspace?.assigned_members || [];
    if (!members.length) {
      return `<div class="head-row"><div><h2>${esc(title)}</h2><p>${esc(description)}</p></div></div><div class="notice">Aún no tienes socios asignados. Administración gestiona estas asignaciones; solicita que se vinculen a tu perfil.</div>`;
    }
    const content = specialty === 'PERSONAL_TRAINER' ? personalTrainer()
      : specialty === 'COACH' ? coach()
        : specialty === 'PREPARADOR_FISICO' ? physicalTrainer()
          : '<div class="notice">Esta especialidad no puede acceder a herramientas de seguimiento individual.</div>';
    return `<div class="head-row"><div><h2>${esc(title)}</h2><p>${esc(description)}</p></div></div>${content}`;
  }

  return { teamView };
}
