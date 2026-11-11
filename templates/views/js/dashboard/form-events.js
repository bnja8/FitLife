export function bindDashboardFormEvents(context) {
  const {
    state, api, toast, refresh, setInstallationCapacityVisibility, stopScanner, phoneDigits,
    validatePhoneField, cleanPersonName, blockInvalidPersonNameInput, validatePersonName,
    updateCityOther, updateCityOptions, updatePlanScopeFields, filterPlanSites,
    updatePlanSiteCityFilter, updateClassResources, loadAdminRecords, view, sessionsTable,
    submitForm,
  } = context;

  document.addEventListener('submit', event => {
    if (event.target.id === 'membership-site-form') {
      event.preventDefault();
      return;
    }
    if (!event.target.matches('.data-form')) return;
    event.preventDefault();
    const nameInputs = [...event.target.querySelectorAll('[data-person-name]')];
    if (nameInputs.some(input => !validatePersonName(input, true))) {
      nameInputs.find(input => input.getAttribute('aria-invalid') === 'true')?.focus();
      return;
    }
    const phoneInputs = [...event.target.querySelectorAll('[data-chilean-phone]')];
    if (phoneInputs.some(input => !validatePhoneField(input))) {
      phoneInputs.find(input => input.getAttribute('aria-invalid') === 'true')?.focus();
      return;
    }
    if (event.target.id === 'access-form') stopScanner();
    if (event.target.matches('[data-professional-form]')) {
      const submit = event.target.querySelector('button[type="submit"]');
      if (submit) submit.disabled = true;
      submitForm(event.target).catch(error => toast(error.message, true))
        .finally(() => { if (submit?.isConnected) submit.disabled = false; });
      return;
    }
    const submit = event.target.querySelector('button[type="submit"]');
    if (submit) submit.disabled = true;
    submitForm(event.target).catch(error => toast(error.message, true))
      .finally(() => { if (submit?.isConnected) submit.disabled = false; });
  });

  document.addEventListener('input', event => {
    const planSiteSearch = event.target.closest('[data-plan-site-search]');
    if (planSiteSearch) {
      filterPlanSites(planSiteSearch.form);
      return;
    }
    const nameInput = event.target.closest('[data-person-name]');
    if (nameInput) {
      cleanPersonName(nameInput);
      validatePersonName(nameInput);
      return;
    }
    const input = event.target.closest('[data-chilean-phone]');
    if (!input) return;
    input.value = phoneDigits(input.value);
    validatePhoneField(input);
  });

  document.addEventListener('beforeinput', event => {
    if (event.target.closest('[data-person-name]')) blockInvalidPersonNameInput(event);
  });

  document.addEventListener('blur', event => {
    const nameInput = event.target.closest('[data-person-name]');
    if (nameInput) {
      validatePersonName(nameInput, true);
      return;
    }
    const input = event.target.closest('[data-chilean-phone]');
    if (input) validatePhoneField(input);
  }, true);

  document.addEventListener('change', async event => {
    if (event.target.matches('[data-plan-site-region]')) {
      updatePlanSiteCityFilter(event.target.form);
      return;
    }
    if (event.target.matches('[data-plan-site-city]')) {
      filterPlanSites(event.target.form);
      return;
    }
    if (event.target.id === 'membership-installation') {
      state.membershipInstallationId = event.target.value;
      view();
      document.getElementById('membership-installation')?.focus();
      return;
    }
    if (event.target.matches('[data-class-installation]')) {
      updateClassResources(event.target.form);
      return;
    }
    if (event.target.matches('[data-region-select]')) {
      updateCityOptions(event.target.form);
      return;
    }
    if (event.target.matches('[data-city-select]')) {
      updateCityOther(event.target.form);
      return;
    }
    const capacityToggle = event.target.closest('[data-capacity-target]');
    if (capacityToggle) {
      setInstallationCapacityVisibility(capacityToggle.dataset.capacityTarget, capacityToggle.checked);
      return;
    }
    if (event.target.id === 'installation-has-lockers') {
      setInstallationCapacityVisibility('installation-locker-count', event.target.checked);
      return;
    }
    if (event.target.id === 'installation-has-parking') {
      setInstallationCapacityVisibility('installation-parking-capacity', event.target.checked);
      return;
    }
    if (event.target.id === 'installation-has-dressing-rooms') {
      setInstallationCapacityVisibility('installation-dressing-room-capacity', event.target.checked);
      return;
    }
    if (event.target.id === 'installation-has-showers') {
      setInstallationCapacityVisibility('installation-shower-capacity', event.target.checked);
      return;
    }
    if (event.target.id === 'admin-data-entity') {
      try {
        document.getElementById('admin-data-feedback')?.classList.add('hidden');
        await loadAdminRecords(event.target.value);
      } catch (error) { toast(error.message, true); }
      return;
    }
    if (event.target.id === 'staff-role') {
      const instructorFields = event.target.value === 'INSTRUCTOR';
      document.getElementById('professional-type-field')?.classList.toggle('hidden', !instructorFields);
      document.getElementById('specialization-field')?.classList.toggle('hidden', !instructorFields);
      const installationField = document.getElementById('staff-installation-field');
      installationField?.classList.toggle('hidden', instructorFields);
      if (installationField) installationField.querySelector('select').required = !instructorFields;
      return;
    }
    if (event.target.name === 'roles' && event.target.form?.id === 'user-role-form') {
      const isInstructor = [...event.target.form.querySelectorAll('input[name="roles"]:checked')]
        .some(input => input.value === 'INSTRUCTOR');
      const isReceptionist = [...event.target.form.querySelectorAll('input[name="roles"]:checked')]
        .some(input => input.value === 'RECEPCIONISTA');
      document.getElementById('user-role-professional-field')?.classList.toggle('hidden', !isInstructor);
      document.getElementById('user-role-installation-field')?.classList.toggle('hidden', !isReceptionist);
      event.target.form.elements.instalacion_id.required = isReceptionist;
      return;
    }
    if (event.target.id === 'plan-free-trial' || event.target.id === 'plan-global-access') {
      const form = event.target.form;
      if (event.target.id === 'plan-free-trial' && event.target.checked) {
        form.elements.acceso_todas_sedes.checked = false;
      } else if (event.target.id === 'plan-global-access' && event.target.checked) {
        form.elements.es_prueba_gratuita.checked = false;
        form.elements.tipo.value = 'MEMBRESIA';
      }
      updatePlanScopeFields(form);
      return;
    }
    if (event.target.matches('#plan-form select[name="tipo"]')
        && event.target.value !== 'MEMBRESIA') {
      event.target.form.elements.acceso_todas_sedes.checked = false;
      updatePlanScopeFields(event.target.form);
      return;
    }
    if (event.target.id === 'class-image') {
      const file = event.target.files?.[0];
      const preview = document.getElementById('class-image-preview');
      if (!file) {
        preview.classList.add('hidden');
        return;
      }
      document.getElementById('class-image-preview-img').src = URL.createObjectURL(file);
      document.getElementById('class-image-preview-label').textContent = file.name;
      preview.classList.remove('hidden');
      return;
    }
    if (event.target.id === 'activity-filter') {
      const date = document.getElementById('date-filter')?.value || '';
      const params = new URLSearchParams();
      if (event.target.value) params.set('actividad', event.target.value);
      if (date) params.set('fecha', date);
      const query = params.size ? `?${params}` : '';
      try {
        const result = await api(`/api/sessions${query}`);
        document.getElementById('class-list').innerHTML = sessionsTable(result.sessions, false);
      } catch (error) { toast(error.message, true); }
      return;
    }
    if (event.target.id === 'date-filter') {
      const activity = document.getElementById('activity-filter')?.value || '';
      const params = new URLSearchParams();
      if (activity) params.set('actividad', activity);
      if (event.target.value) params.set('fecha', event.target.value);
      try {
        const result = await api(`/api/sessions${params.size ? `?${params}` : ''}`);
        document.getElementById('class-list').innerHTML = sessionsTable(result.sessions, false);
      } catch (error) { toast(error.message, true); }
      return;
    }
    const machineRoom = event.target.closest('[data-machine-room]');
    if (machineRoom) {
      if (!machineRoom.value) {
        machineRoom.value = machineRoom.dataset.currentSala || '';
        return;
      }
      try {
        await api(`/api/machines/${machineRoom.dataset.machineRoom}`, {
          method: 'PATCH',
          body: JSON.stringify({ sala_id: Number(machineRoom.value) }),
        });
        await refresh(state.route);
        toast('Sala asignada a la máquina.');
      } catch (error) {
        machineRoom.value = machineRoom.dataset.currentSala || '';
        toast(error.message, true);
      }
      return;
    }
    const machine = event.target.closest('[data-machine]');
    if (machine) {
      try {
        await api(`/api/machines/${machine.dataset.machine}`, {
          method: 'PATCH', body: JSON.stringify({ estado: machine.value }),
        });
        await refresh(state.route);
        toast('Estado de máquina actualizado.');
      } catch (error) { toast(error.message, true); }
    }
  });
}
