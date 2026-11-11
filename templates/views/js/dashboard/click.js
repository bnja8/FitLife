export function bindDashboardClickEvents(context) {
  const {
    state, api, toast, refresh, confirmTrialRedemption, setInstallationCapacityVisibility,
    stopScanner, showCredential, updateCityOptions, setScheduleRange, updatePlanScopeFields,
    updateClassResources, view, closeMenu, startScanner,
  } = context;

  document.addEventListener('click', async event => {
    const addExercise = event.target.closest('[data-add-exercise]');
    if (addExercise) {
      const routine = addExercise.closest('[data-routine-row]');
      const list = routine?.querySelector('[data-exercise-list]') || addExercise.form.querySelector('[data-exercise-list]');
      const row = list?.querySelector('[data-exercise-row]');
      if (row && list.children.length < 30) {
        const clone = row.cloneNode(true);
        clone.querySelectorAll('input').forEach(input => { input.value = ''; });
        list.append(clone);
      }
      return;
    }
    const removeExercise = event.target.closest('[data-remove-exercise]');
    if (removeExercise) {
      const list = removeExercise.closest('[data-exercise-list]');
      if (list?.children.length > 1) removeExercise.closest('[data-exercise-row]').remove();
      return;
    }
    const addRoutine = event.target.closest('[data-add-routine]');
    if (addRoutine) {
      const list = addRoutine.form.querySelector('[data-routine-list]');
      const routine = list?.querySelector('[data-routine-row]');
      if (routine && list.children.length < 14) {
        const clone = routine.cloneNode(true);
        clone.querySelectorAll('input').forEach(input => { input.value = ''; });
        const exercises = clone.querySelector('[data-exercise-list]');
        [...exercises.children].slice(1).forEach(item => item.remove());
        list.append(clone);
      }
      return;
    }
    const removeRoutine = event.target.closest('[data-remove-routine]');
    if (removeRoutine) {
      const list = removeRoutine.closest('[data-routine-list]');
      if (list?.children.length > 1) removeRoutine.closest('[data-routine-row]').remove();
      return;
    }
    const close = event.target.closest('[data-close-credential]');
    if (close || event.target.id === 'credential-modal') {
      document.getElementById('credential-modal').classList.add('hidden');
      return;
    }
    const resetForm = event.target.closest('[data-reset-form]');
    if (resetForm) {
      const form = document.getElementById(resetForm.dataset.resetForm);
      form?.reset();
      if (form) {
        updateCityOptions(form);
        delete form.dataset.editId;
        delete form.dataset.planId;
        form.classList.add('hidden');
        if (form.id === 'installation-form') {
          setInstallationCapacityVisibility('installation-locker-count', false);
          setInstallationCapacityVisibility('installation-parking-capacity', false);
          setInstallationCapacityVisibility('installation-dressing-room-capacity', false);
          setInstallationCapacityVisibility('installation-shower-capacity', false);
          delete form.dataset.installationId;
          form.querySelector('h3').textContent = 'Agregar sede';
          form.querySelector('button[type="submit"]').textContent = 'Guardar sede';
        }
        if (form.id === 'class-form') {
          form.querySelector('#class-image-preview')?.classList.add('hidden');
          const previewImage = form.querySelector('#class-image-preview-img');
          if (previewImage) previewImage.removeAttribute('src');
        }
        const title = form.querySelector('h3');
        const submit = form.querySelector('button[type="submit"]');
        if (form.id === 'class-form') {
          title.textContent = 'Programar una clase';
          submit.textContent = 'Guardar clase';
        }
        if (form.id === 'plan-form') {
          title.textContent = 'Nuevo plan';
          submit.textContent = 'Guardar plan';
          updatePlanScopeFields(form);
        }
        if (form.id === 'installation-form') {
          form.elements.cantidad_lockers.disabled = true;
          form.elements.cantidad_lockers.required = false;
          form.elements.cupos_estacionamiento.disabled = true;
          form.elements.cupos_estacionamiento.required = false;
          form.elements.cantidad_vestidores.disabled = true;
          form.elements.cantidad_vestidores.required = false;
          form.elements.cantidad_duchas.disabled = true;
          form.elements.cantidad_duchas.required = false;
        }
        if (form.id === 'staff-form') {
          const instructorFields = form.elements.rol.value === 'INSTRUCTOR';
          document.getElementById('professional-type-field')?.classList.toggle('hidden', !instructorFields);
          document.getElementById('specialization-field')?.classList.toggle('hidden', !instructorFields);
          document.getElementById('staff-installation-field')?.classList.toggle('hidden', instructorFields);
          form.elements.instalacion_id.required = !instructorFields;
        }
      }
      return;
    }
    const planEdit = event.target.closest('[data-plan-edit]');
    if (planEdit) {
      const plan = (state.data.plans || []).find(item => String(item.plan_id) === planEdit.dataset.planEdit);
      const form = document.getElementById('plan-form');
      if (!plan || !form) return;
      form.dataset.planId = plan.plan_id;
      for (const field of ['tipo', 'nombre', 'duracion_dias', 'precio_referencia', 'descripcion', 'otros_beneficios']) {
        form.elements[field].value = plan[field] ?? '';
      }
      form.elements.incluye_entrenador_personal.checked = Boolean(plan.incluye_entrenador_personal);
      form.elements.incluye_lockers.checked = Boolean(plan.incluye_lockers);
      form.elements.incluye_estacionamiento.checked = Boolean(plan.incluye_estacionamiento);
      form.elements.acceso_todas_sedes.checked = Boolean(plan.acceso_todas_sedes);
      form.elements.es_prueba_gratuita.checked = Boolean(plan.es_prueba_gratuita);
      form.querySelectorAll('input[name="instalaciones_ids"]').forEach(input => {
        input.checked = !plan.acceso_todas_sedes && (state.data.installations || []).some(installation =>
          String(installation.instalacion_id) === input.value
          && (installation.plan_ids || []).some(planId => String(planId) === String(plan.plan_id))
        );
      });
      updatePlanScopeFields(form);
      form.querySelector('h3').textContent = `Editar plan · ${plan.nombre}`;
      form.querySelector('button[type="submit"]').textContent = 'Guardar cambios';
      form.classList.remove('hidden');
      form.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    const planDelete = event.target.closest('[data-plan-delete]');
    if (planDelete) {
      if (!window.confirm('¿Desactivar este plan? Las membresías existentes conservarán sus datos.')) return;
      planDelete.disabled = true;
      try {
        await api(`/api/plans/${planDelete.dataset.planDelete}`, { method: 'DELETE' });
        await refresh('memberships');
        toast('Plan desactivado.');
      } catch (error) {
        toast(error.message, true);
        planDelete.disabled = false;
      }
      return;
    }
    const userRoleEdit = event.target.closest('[data-user-roles]');
    if (userRoleEdit) {
      const user = (state.data.users || []).find(item => item.rut === userRoleEdit.dataset.userRoles);
      const form = document.getElementById('user-role-form');
      if (!user || !form) return;
      form.reset();
      form.elements.rut.value = user.rut;
      form.querySelectorAll('input[name="roles"]').forEach(input => {
        input.checked = (user.roles || []).includes(input.value);
      });
      form.elements.tipo_profesional.value = user.tipo_profesional || 'MONITOR';
      form.elements.especialidad.value = user.especialidad || '';
      form.elements.instalacion_id.value = user.recepcionista_instalacion_id || '';
      document.getElementById('user-role-form-title').textContent =
        `Roles de ${user.nombres} ${user.apellido_paterno}`;
      document.getElementById('user-role-professional-field').classList.toggle(
        'hidden', !user.roles?.includes('INSTRUCTOR'),
      );
      document.getElementById('user-role-installation-field').classList.toggle(
        'hidden', !user.roles?.includes('RECEPCIONISTA'),
      );
      form.elements.instalacion_id.required = user.roles?.includes('RECEPCIONISTA') || false;
      form.classList.remove('hidden');
      form.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    if (event.target.closest('[data-user-role-cancel]')) {
      const form = document.getElementById('user-role-form');
      form.reset();
      form.classList.add('hidden');
      return;
    }
    if (event.target.closest('[data-admin-cancel]')) {
      const form = document.getElementById('admin-data-form');
      form.reset();
      updateCityOptions(form);
      delete form.dataset.recordId;
      form.classList.add('hidden');
      return;
    }
    if (event.target.closest('[data-admin-create]')) {
      const form = document.getElementById('admin-data-form');
      delete form.dataset.recordId;
      form.reset();
      updateCityOptions(form);
      document.getElementById('admin-data-form-title').textContent = `Nuevo registro · ${state.adminEntityData.label}`;
      form.classList.remove('hidden');
      form.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    const adminEdit = event.target.closest('[data-admin-edit]');
    if (adminEdit) {
      const data = state.adminEntityData;
      const record = data.records.find(item => String(item.record_key ?? item[data.primary_key]) === adminEdit.dataset.adminEdit);
      if (!record) return;
      const form = document.getElementById('admin-data-form');
      form.dataset.recordId = adminEdit.dataset.adminEdit;
      document.getElementById('admin-data-form-title').textContent = `Editar registro · ${data.label}`;
      for (const field of data.fields) {
        const control = form.elements[field.name];
        if (!control) continue;
        const value = record[field.name] ?? '';
        control.value = field.type === 'person_name' && value === '-'
          ? ''
          : field.type === 'phone' && value
          ? phoneDigits(String(value))
          : field.type === 'datetime' && value
          ? (() => {
            const date = new Date(value);
            const pad = number => String(number).padStart(2, '0');
            return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
          })()
          : String(value);
      }
      updateCityOptions(form, record.ciudad || '');
      form.classList.remove('hidden');
      form.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    const installationEdit = event.target.closest('[data-installation-edit]');
    if (installationEdit) {
      const installation = (state.data.installations || []).find(
        item => String(item.instalacion_id) === installationEdit.dataset.installationEdit,
      );
      const form = document.getElementById('installation-form');
      if (!installation || !form) return;
      form.dataset.installationId = installation.instalacion_id;
      for (const field of [
        'nombre', 'direccion', 'region', 'aforo_maximo', 'horario_lunes_viernes',
        'horario_sabados_dom_festivos', 'caracteristicas', 'mapa_url', 'imagen_url',
      ]) {
        form.elements[field].value = installation[field] ?? '';
      }
      setScheduleRange(form, 'horario_lunes_viernes', installation.horario_lunes_viernes);
      setScheduleRange(form, 'horario_sabados_dom_festivos', installation.horario_sabados_dom_festivos);
      updateCityOptions(form, installation.ciudad || '');
      form.elements.tiene_lockers.checked = installation.tiene_lockers;
      form.elements.cantidad_lockers.value = installation.cantidad_lockers;
      setInstallationCapacityVisibility('installation-locker-count', installation.tiene_lockers);
      form.elements.tiene_estacionamiento.checked = installation.tiene_estacionamiento;
      form.elements.cupos_estacionamiento.value = installation.cupos_estacionamiento;
      setInstallationCapacityVisibility('installation-parking-capacity', installation.tiene_estacionamiento);
      form.elements.tiene_vestidores.checked = installation.tiene_vestidores;
      form.elements.cantidad_vestidores.value = installation.cantidad_vestidores;
      setInstallationCapacityVisibility('installation-dressing-room-capacity', installation.tiene_vestidores);
      form.elements.tiene_duchas.checked = installation.tiene_duchas;
      form.elements.cantidad_duchas.value = installation.cantidad_duchas;
      setInstallationCapacityVisibility('installation-shower-capacity', installation.tiene_duchas);
      const selectedPlans = new Set((installation.plan_ids || []).map(String));
      form.querySelectorAll('input[name="planes_ids"]').forEach(input => {
        input.checked = selectedPlans.has(input.value);
      });
      form.querySelector('h3').textContent = `Editar sede · ${installation.nombre}`;
      form.querySelector('button[type="submit"]').textContent = 'Guardar cambios';
      form.classList.remove('hidden');
      form.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    const adminDelete = event.target.closest('[data-admin-delete]');
    if (adminDelete) {
      adminDelete.disabled = true;
      try {
        const result = await api(`/api/admin/data/${encodeURIComponent(state.adminEntityKey)}/${encodeURIComponent(adminDelete.dataset.adminDelete)}`, { method: 'DELETE' });
        await refresh('users');
        toast(result.message || 'Registro actualizado.');
      } catch (error) {
        toast(error.message, true);
        adminDelete.disabled = false;
      }
      return;
    }
    const route = event.target.closest('[data-route]');
    if (route) {
      stopScanner();
      closeMenu();
      if (route.dataset.route === 'credential') {
        await showCredential();
        return;
      }
      state.attendanceSessionId = null;
      if (route.dataset.route === 'gym-detail') {
        state.selectedInstallationId = route.dataset.installationId;
      }
      if (route.dataset.route === 'installation-detail') {
        state.selectedAdminInstallationId = route.dataset.installationId;
      }
      try { await refresh(route.dataset.route); } catch (error) { toast(error.message, true); }
      return;
    }
    const manageInstallation = event.target.closest('[data-installation-manage]');
    if (manageInstallation) {
      state.selectedAdminInstallationId = manageInstallation.dataset.installationManage;
      await refresh('installation-detail');
      return;
    }
    const gymDay = event.target.closest('[data-gym-day]');
    if (gymDay) {
      state.selectedGymWeekday = Number(gymDay.dataset.gymDay);
      view();
      return;
    }
    const quickAction = event.target.closest('[data-quick-action]');
    if (quickAction) {
      const targetRoute = quickAction.dataset.actionRoute || 'classes';
      closeMenu();
      try {
        if (quickAction.dataset.actionAdmin === 'true') {
          await refresh('classes');
          const form = document.getElementById('class-form');
          form?.classList.remove('hidden');
          form?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        } else {
          await refresh(targetRoute);
        }
      } catch (error) { toast(error.message, true); }
      return;
    }
    if (event.target.closest('[data-credential]')) {
      await showCredential();
      return;
    }
    const attendanceSession = event.target.closest('[data-attendance-session]');
    if (attendanceSession) {
      state.attendanceSessionId = attendanceSession.dataset.attendanceSession;
      await refresh('attendance');
      return;
    }
    const classImage = event.target.closest('[data-class-image]');
    if (classImage) {
      const modal = document.getElementById('class-image-modal');
      document.getElementById('class-image-title').textContent = classImage.dataset.classTitle;
      const image = document.getElementById('class-image-full');
      image.src = classImage.dataset.classImage;
      image.alt = `Imagen de ${classImage.dataset.classTitle}`;
      state.classImageTrigger = classImage;
      modal.classList.remove('hidden');
      modal.querySelector('[data-close-class-image]').focus();
      return;
    }
    const closeClassImage = event.target.closest('[data-close-class-image]');
    if (closeClassImage || event.target.id === 'class-image-modal') {
      const modal = document.getElementById('class-image-modal');
      modal.classList.add('hidden');
      document.getElementById('class-image-full').removeAttribute('src');
      state.classImageTrigger?.focus();
      state.classImageTrigger = null;
      return;
    }
    if (event.target.id === 'trial-confirmation') {
      event.target.close('cancel');
      return;
    }
    if (event.target.closest('[data-attendance-back]')) {
      state.attendanceSessionId = null;
      await refresh('attendance');
      return;
    }
    const redeemTrial = event.target.closest('[data-redeem-trial]');
    if (redeemTrial) {
      if (!await confirmTrialRedemption(redeemTrial)) return;
      redeemTrial.disabled = true;
      try {
        const result = await api('/api/memberships/trial', {
          method: 'POST',
          body: JSON.stringify({
            plan_id: Number(redeemTrial.dataset.redeemTrial),
            instalacion_id: Number(redeemTrial.dataset.redeemInstallation),
          }),
        });
        await refresh('plans');
        toast(result.message || 'Tu prueba gratuita fue activada.');
      } catch (error) {
        toast(error.message, true);
        redeemTrial.disabled = false;
      }
      return;
    }
    const purchasePlan = event.target.closest('[data-purchase-plan]');
    if (purchasePlan) {
      purchasePlan.disabled = true;
      try {
        const result = await api('/api/memberships/purchase', {
          method: 'POST',
          body: JSON.stringify({
            plan_id: Number(purchasePlan.dataset.purchasePlan),
            instalacion_id: Number(purchasePlan.dataset.purchaseInstallation),
            metodo_pago: 'WEBPAY',
          }),
        });
        if (result.gratis) {
          await refresh('membership');
          toast(result.message);
          return;
        }
        const paymentUrl = new URL(result.url);
        if (
          paymentUrl.protocol !== 'https:'
          || !['webpay3g.transbank.cl', 'webpay3gint.transbank.cl'].includes(paymentUrl.hostname)
        ) {
          throw new Error('Transbank devolvió una dirección de pago no válida.');
        }
        const paymentForm = document.createElement('form');
        paymentForm.method = 'POST';
        paymentForm.action = paymentUrl.href;
        const tokenField = document.createElement('input');
        tokenField.type = 'hidden';
        tokenField.name = 'token_ws';
        tokenField.value = result.token;
        paymentForm.append(tokenField);
        document.body.append(paymentForm);
        paymentForm.submit();
      } catch (error) {
        toast(error.message, true);
        purchasePlan.disabled = false;
      }
      return;
    }
    const reserve = event.target.closest('[data-reserve]');
    if (reserve) {
      reserve.disabled = true;
      try {
        const result = await api(`/api/sessions/${reserve.dataset.reserve}/reserve`, {
          method: 'POST', body: JSON.stringify({ metodo_pago: 'OTRO' }),
        });
        await refresh('classes');
        toast(result.message + (result.pago_pendiente ? ' El pago queda pendiente en recepción.' : ''));
      } catch (error) { toast(error.message, true); reserve.disabled = false; }
      return;
    }
    const cancel = event.target.closest('[data-cancel]');
    if (cancel) {
      try {
        const result = await api(`/api/reservations/${cancel.dataset.cancel}/cancel`, { method: 'POST' });
        await refresh('reservations');
        toast(`Reserva cancelada. ${result.personas_promovidas || 0} persona(s) promovida(s) de la lista de espera.`);
      } catch (error) { toast(error.message, true); }
      return;
    }
    const attendance = event.target.closest('[data-attendance]');
    if (attendance) {
      attendance.disabled = true;
      try {
        await api(`/api/sessions/${attendance.dataset.session}/attendance`, {
          method: 'POST',
          body: JSON.stringify({
            reserva_id: attendance.dataset.attendance,
            asistio: attendance.dataset.attended === 'true',
          }),
        });
        await refresh('attendance');
        toast('Asistencia registrada.');
      } catch (error) {
        toast(error.message, true);
        attendance.disabled = false;
      }
      return;
    }
    const toggle = event.target.closest('[data-toggle-form]');
    if (toggle) {
      const form = document.getElementById(toggle.dataset.toggleForm);
      if (form?.id === 'installation-form' && form.classList.contains('hidden')) {
        form.reset();
        updateCityOptions(form);
        delete form.dataset.installationId;
        setInstallationCapacityVisibility('installation-locker-count', false);
        setInstallationCapacityVisibility('installation-parking-capacity', false);
        form.querySelector('h3').textContent = 'Agregar sede';
        form.querySelector('button[type="submit"]').textContent = 'Guardar sede';
      }
      form?.classList.toggle('hidden');
      return;
    }
    const user = event.target.closest('[data-user]');
    if (user) {
      try {
        await api(`/api/users/${encodeURIComponent(user.dataset.user)}`, {
          method: 'PATCH', body: JSON.stringify({ activo: user.dataset.active === 'true' }),
        });
        await refresh('users');
        toast('Cuenta actualizada.');
      } catch (error) { toast(error.message, true); }
      return;
    }
    const accessPoint = event.target.closest('[data-access-point]');
    if (accessPoint) {
      accessPoint.disabled = true;
      try {
        await api(`/api/access-points/${accessPoint.dataset.accessPoint}`, {
          method: 'PATCH',
          body: JSON.stringify({ activo: accessPoint.dataset.active === 'true' }),
        });
        await refresh('installation-detail');
        toast(`Punto de acceso ${accessPoint.dataset.active === 'true' ? 'activado' : 'desactivado'}.`);
      } catch (error) {
        toast(error.message, true);
        accessPoint.disabled = false;
      }
      return;
    }
    const sessionStatus = event.target.closest('[data-session-status]');
    if (sessionStatus) {
      try {
        await api(`/api/sessions/${sessionStatus.dataset.sessionStatus}/status`, {
          method: 'PATCH', body: JSON.stringify({ estado: sessionStatus.dataset.nextStatus }),
        });
        await refresh(state.route);
        toast('Estado de la clase actualizado.');
      } catch (error) { toast(error.message, true); }
      return;
    }
    const sessionEdit = event.target.closest('[data-session-edit]');
    if (sessionEdit) {
      const session = [...(state.data.admin_sessions || []), ...(state.data.sessions || [])]
        .find(item => item.sesion_id === Number(sessionEdit.dataset.sessionEdit));
      const form = document.getElementById('class-form');
      if (!session || !form) return;
      form.dataset.editId = session.sesion_id;
      form.classList.remove('hidden');
      form.querySelector('h3').textContent = 'Editar clase';
      const submit = form.querySelector('button[type="submit"]');
      submit.textContent = 'Guardar cambios';
      form.elements.instalacion_id.value = session.instalacion_id ?? '';
      updateClassResources(form, session.sala_id, session.instructor_id);
      const datetime = value => {
        const date = new Date(value);
        const pad = number => String(number).padStart(2, '0');
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
      };
      for (const [field, value] of Object.entries({
        actividad: session.actividad,
        nombre: session.nombre,
        instructor_id: session.instructor_id,
        sala_id: session.sala_id,
        inicio: datetime(session.inicio),
        fin: datetime(session.fin),
        cupos_totales: session.cupos_totales,
        precio: session.precio,
      })) {
        form.elements[field].value = value ?? '';
      }
      const imagePreview = document.getElementById('class-image-preview');
      if (session.imagen_url) {
        document.getElementById('class-image-preview-img').src = session.imagen_url;
        document.getElementById('class-image-preview-label').textContent = 'Imagen actual. Selecciona otra para reemplazarla.';
        imagePreview.classList.remove('hidden');
      } else {
        imagePreview.classList.add('hidden');
      }
      form.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    const profile = event.target.closest('#profile-button, #topbar-user, [data-logout]');
    if (profile) {
      sessionStorage.removeItem('fitlife-token');
      sessionStorage.removeItem('fitlife-credential');
      location.assign('/');
      return;
    }
    if (event.target.closest('#notifications-button')) {
      const routeName = state.data.roles.includes('ADMINISTRADOR') ? 'alerts' : 'reservations';
      await refresh(routeName);
      return;
    }
    if (event.target.closest('[data-export]')) {
      const rows = state.data.recent_access || [];
      const columns = ['socio', 'instalacion', 'tipo', 'registrado_en', 'resultado'];
      const quote = value => `"${String(value ?? '').replaceAll('"', '""')}"`;
      const csv = [columns.join(','), ...rows.map(row => columns.map(column => quote(row[column])).join(','))].join('\r\n');
      const link = document.createElement('a');
      link.href = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }));
      link.download = 'fitlife-accesos-recientes.csv';
      link.click();
      URL.revokeObjectURL(link.href);
      return;
    }
    if (event.target.closest('#scan-camera')) {
      startScanner().catch(error => toast(error.message, true));
    }
  });
}
