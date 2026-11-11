export function createDashboardSubmitter(context) {
  const { state, api, refresh, prepareInstallationPayload, normalizeLocationPayload,
    loadAdminRecords, toast, esc } = context;

  function submitForm(form) {
    const payload = normalizeLocationPayload(form, Object.fromEntries(new FormData(form)));
    if (form.id === 'admin-data-form') {
      const editingId = form.dataset.recordId;
      if (editingId && ['personas', 'cuentas'].includes(state.adminEntityKey)) {
        delete payload.rut;
      }
      const url = `/api/admin/data/${encodeURIComponent(state.adminEntityKey)}${editingId ? `/${encodeURIComponent(editingId)}` : ''}`;
      return api(url, {
        method: editingId ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      }).then(async result => {
        if (result.credential) await loadAdminRecords(state.adminEntityKey);
        else await refresh('users');
        toast(result.message || 'Registro guardado.');
        if (result.credential) {
          const feedback = document.getElementById('admin-data-feedback');
          feedback.textContent = `Token QR de un solo uso: ${result.credential}`;
          feedback.classList.remove('hidden');
        }

      });
    }
    if (form.id === 'class-form' || form.id === 'monitor-class-form') {
      const editingId = form.dataset.editId;
      const formData = new FormData(form);
      if (!formData.get('imagen')?.size) formData.delete('imagen');
      return api(editingId ? `/api/sessions/${editingId}` : '/api/sessions', {
        method: 'POST',
        body: formData,
      })
        .then(() => refresh(form.id === 'monitor-class-form' ? 'sessions' : 'classes')
          .then(() => toast(editingId ? 'Clase actualizada.' : 'Clase programada.')));
    }
    if (form.id === 'machine-form') {
      return api('/api/machines', { method: 'POST', body: JSON.stringify(payload) })
        .then(() => refresh('installation-detail').then(() => toast('Máquina agregada a la sede.')));
    }
    if (form.id === 'room-form') {
      return api('/api/rooms', { method: 'POST', body: JSON.stringify(payload) })
        .then(() => refresh('installation-detail').then(() => toast('Sala agregada a la sede.')));
    }
    if (form.id === 'installation-machine-form') {
      return api('/api/machines', { method: 'POST', body: JSON.stringify(payload) })
        .then(() => refresh('installation-detail').then(() => toast('Máquina agregada a la sede.')));
    }
    if (form.id === 'installation-room-form') {
      return api('/api/rooms', { method: 'POST', body: JSON.stringify(payload) })
        .then(() => refresh('installation-detail').then(() => toast('Sala agregada a la sede.')));
    }
    if (form.id === 'installation-access-point-form') {
      return api('/api/access-points', { method: 'POST', body: JSON.stringify(payload) })
        .then(() => refresh('installation-detail').then(() => toast('Punto de acceso agregado a la sede.')));
    }
    if (form.id === 'installation-admin-settings-form') {
      prepareInstallationPayload(form, payload);
      return api(`/api/installations/${state.selectedAdminInstallationId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }).then(() => refresh('installation-detail').then(() => toast('Datos de la sede actualizados.')));
    }
    if (form.id === 'installation-staff-form') {
      payload.instructor_ids = [...form.querySelectorAll('input[name="instructor_ids"]:checked')]
        .map(input => Number(input.value));
      return api(`/api/installations/${state.selectedAdminInstallationId}/instructors`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      }).then(() => refresh('installation-detail').then(() => toast('Profesionales actualizados.')));
    }
    if (form.id === 'installation-form') {
      prepareInstallationPayload(form, payload);
      const installationId = form.dataset.installationId;
      return api(installationId ? `/api/installations/${installationId}` : '/api/installations', {
        method: installationId ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      }).then(() => refresh('installations').then(() => toast(installationId ? 'Sede actualizada.' : 'Sede agregada.')));
    }
    if (form.id === 'staff-form') {
      return api('/api/users', { method: 'POST', body: JSON.stringify(payload) })
        .then(() => refresh('users').then(() => toast('Cuenta profesional creada.')));
    }
    if (form.id === 'user-role-form') {
      const rut = form.elements.rut.value;
      const roles = [...form.querySelectorAll('input[name="roles"]:checked')].map(input => input.value);
      return api(`/api/users/${encodeURIComponent(rut)}/roles`, {
        method: 'PATCH',
        body: JSON.stringify({
          roles,
          tipo_profesional: form.elements.tipo_profesional.value,
          especialidad: form.elements.especialidad.value,
          instalacion_id: form.elements.instalacion_id.value ? Number(form.elements.instalacion_id.value) : null,
        }),
      }).then(() => refresh('users').then(() => toast('Roles actualizados.')));
    }
    if (form.id === 'plan-form') {
      payload.incluye_entrenador_personal = form.elements.incluye_entrenador_personal.checked;
      payload.incluye_lockers = form.elements.incluye_lockers.checked;
      payload.incluye_estacionamiento = form.elements.incluye_estacionamiento.checked;
      payload.acceso_todas_sedes = form.elements.acceso_todas_sedes.checked;
      payload.es_prueba_gratuita = form.elements.es_prueba_gratuita.checked;
      payload.instalaciones_ids = [...form.querySelectorAll('input[name="instalaciones_ids"]:checked')]
        .map(input => Number(input.value));
      const editingId = form.dataset.planId;
      return api(editingId ? `/api/plans/${editingId}` : '/api/plans', {
        method: editingId ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      }).then(() => refresh('memberships').then(() => toast(editingId ? 'Plan actualizado.' : 'Plan creado.')));
    }
    if (form.id === 'access-form') {
      return api('/api/access/validate', { method: 'POST', body: JSON.stringify(payload) })
        .then(async result => {
          await refresh('access');
          const target = document.getElementById('access-result');
          target.innerHTML = `<div class="result ${result.resultado === 'AUTORIZADO' ? 'ok' : 'bad'}"><strong>${result.resultado === 'AUTORIZADO' ? 'Acceso permitido' : 'Acceso denegado'}</strong><small>${esc(result.motivo_rechazo || 'Validación FitLife')}</small></div>`;
        });
    }
    if (form.id === 'attendance-form') {
      const sessionId = payload.sesion_id;
      return api(`/api/sessions/${sessionId}/attendance`, {
        method: 'POST',
        body: JSON.stringify({ reserva_id: payload.reserva_id, asistio: payload.asistio === 'true' }),
      }).then(() => refresh('attendance').then(() => toast('Asistencia registrada.')));
    }
    if (form.id === 'class-observation-form') {
      return api(`/api/sessions/${payload.sesion_id}/observations`, {
        method: 'POST',
        body: JSON.stringify({ observaciones: payload.observaciones }),
      }).then(() => refresh('sessions').then(() => toast('Observaciones de clase guardadas.')));
    }
    if (form.matches('[data-professional-form]')) {
      const exercisesFor = routine => [...routine.querySelectorAll('[data-exercise-row]')].map(row => ({
          nombre: row.querySelector('[name="ejercicio_nombre"]').value,
          series: row.querySelector('[name="ejercicio_series"]').value,
          repeticiones: row.querySelector('[name="ejercicio_repeticiones"]').value,
          carga_kg: row.querySelector('[name="ejercicio_carga_kg"]').value,
          descanso_segundos: row.querySelector('[name="ejercicio_descanso_segundos"]').value,
          duracion_segundos: row.querySelector('[name="ejercicio_duracion_segundos"]').value,
          observaciones: row.querySelector('[name="ejercicio_observaciones"]').value,
        }));
      for (const key of Object.keys(payload)) {
        if (key.startsWith('ejercicio_')) delete payload[key];
      }
      if (form.elements.accion.value === 'PLAN_ENTRENAMIENTO') {
        payload.rutinas = [...form.querySelectorAll('[data-routine-row]')].map(routine => ({
          dia: routine.querySelector('[name="rutina_dia"]').value,
          ejercicios: exercisesFor(routine),
        }));
      }
      return api('/api/professional/workspace', {
        method: 'POST',
        body: JSON.stringify(payload),
      }).then(() => refresh('team').then(() => toast('Registro profesional guardado.')));
    }
    return Promise.resolve();
  }

  return submitForm;
}
