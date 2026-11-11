export function createDashboardForms(context) {
  const { state, esc, professionalLabels, api } = context;

  function locationFieldsHTML(locationOptions = {}) {
    const regions = Object.keys(locationOptions);
    return `<label>Región<select name="region" data-region-select required><option value="">Selecciona una región</option>${regions.map(region => `<option value="${esc(region)}">${esc(region)}</option>`).join('')}</select></label>
      <label>Ciudad o comuna<select name="ciudad" data-city-select required disabled><option value="">Primero selecciona una región</option></select><input class="hidden" name="ciudad_otra" data-city-other maxlength="100" placeholder="Indica la ciudad o comuna" aria-label="Otra ciudad o comuna"></label>`;
  }

  function updateCityOther(form) {
    const citySelect = form.elements.ciudad;
    const otherInput = form.elements.ciudad_otra;
    if (!citySelect || !otherInput) return;
    const isOther = citySelect.value === '__other__';
    otherInput.classList.toggle('hidden', !isOther);
    otherInput.required = isOther;
    if (!isOther) otherInput.value = '';
  }

  function updateCityOptions(form, selectedCity = '') {
    const regionSelect = form.elements.region;
    const citySelect = form.elements.ciudad;
    if (!regionSelect || !citySelect) return;
    const locationOptions = form.id === 'admin-data-form'
      ? state.adminEntityData?.location_options || {}
      : state.data.location_options || {};
    const cities = locationOptions[regionSelect.value] || [];
    citySelect.innerHTML = `<option value="">Selecciona una ciudad o comuna</option>${cities.map(city => `<option value="${esc(city)}">${esc(city)}</option>`).join('')}<option value="__other__">Otra ciudad o comuna…</option>`;
    citySelect.disabled = !regionSelect.value;
    const isKnownCity = cities.includes(selectedCity);
    citySelect.value = selectedCity && isKnownCity ? selectedCity : selectedCity ? '__other__' : '';
    if (form.elements.ciudad_otra) {
      form.elements.ciudad_otra.value = selectedCity && !isKnownCity ? selectedCity : '';
      updateCityOther(form);
    }
  }

  function normalizeLocationPayload(form, payload) {
    if (payload.ciudad === '__other__') payload.ciudad = payload.ciudad_otra;
    delete payload.ciudad_otra;
    return payload;
  }

  function parseScheduleRange(schedule) {
    const match = String(schedule || '').match(
      /^\s*(\d{1,2})(?::(\d{2}))?\s*h?\s*-\s*(\d{1,2})(?::(\d{2}))?\s*h?\s*$/i,
    );
    if (!match) return ['', ''];
    const start = `${match[1].padStart(2, '0')}:${match[2] || '00'}`;
    const end = `${match[3].padStart(2, '0')}:${match[4] || '00'}`;
    const validTime = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
    return validTime.test(start) && validTime.test(end) ? [start, end] : ['', ''];
  }

  function setScheduleRange(form, fieldName, schedule) {
    const [start, end] = parseScheduleRange(schedule);
    form.querySelector(`[data-schedule-field="${fieldName}"][data-schedule-part="start"]`).value = start;
    form.querySelector(`[data-schedule-field="${fieldName}"][data-schedule-part="end"]`).value = end;
  }

  function updatePlanScopeFields(form) {
    if (!form || form.id !== 'plan-form') return;
    const isGlobal = form.elements.acceso_todas_sedes.checked;
    const isTrial = form.elements.es_prueba_gratuita.checked;
    const sitesFieldset = form.querySelector('#plan-sites-fieldset');
    sitesFieldset.classList.toggle('hidden', isGlobal);
    if (isGlobal) {
      form.querySelectorAll('input[name="instalaciones_ids"]').forEach(input => { input.checked = false; });
    }
    if (isTrial) {
      form.elements.precio_referencia.value = '0';
    }
    form.elements.precio_referencia.readOnly = isTrial;
    form.querySelector('#plan-sites-help').textContent = isGlobal
      ? 'La membresía se publica automáticamente en todas las sedes activas.'
      : isTrial
        ? 'Selecciona exactamente una sede donde ofrecer la prueba gratuita.'
        : 'Selecciona una o más sedes donde los clientes podrán contratar este plan.';
  }

  function filterPlanSites(form) {
    const fieldset = form?.querySelector('#plan-sites-fieldset');
    if (!fieldset) return;
    const search = fieldset.querySelector('[data-plan-site-search]').value.trim().toLocaleLowerCase('es-CL');
    const region = fieldset.querySelector('[data-plan-site-region]').value;
    const city = fieldset.querySelector('[data-plan-site-city]').value;
    const options = [...fieldset.querySelectorAll('[data-plan-site-option]')];
    let visibleCount = 0;
    options.forEach(option => {
        const matches = (!search || option.dataset.search.toLocaleLowerCase('es-CL').includes(search))
          && (!region || option.dataset.region === region)
          && (!city || option.dataset.city === city);
        option.classList.toggle('hidden', !matches);
        if (matches) visibleCount += 1;
    });
    const count = fieldset.querySelector('[data-plan-site-count]');
    if (count) count.textContent = `${visibleCount} de ${options.length} ${options.length === 1 ? 'sede' : 'sedes'}`;
  }

  function updatePlanSiteCityFilter(form) {
    const fieldset = form?.querySelector('#plan-sites-fieldset');
    if (!fieldset) return;
    const region = fieldset.querySelector('[data-plan-site-region]').value;
    const citySelect = fieldset.querySelector('[data-plan-site-city]');
    const selectedCity = citySelect.value;
    const cities = [...new Set((state.data.installations || [])
        .filter(installation => !region || installation.region === region)
        .map(installation => installation.ciudad)
        .filter(Boolean))]
        .sort((a, b) => a.localeCompare(b, 'es-CL'));
    citySelect.innerHTML = `<option value="">Todas las comunas</option>${cities.map(city => `<option value="${esc(city)}">${esc(city)}</option>`).join('')}`;
    citySelect.value = cities.includes(selectedCity) ? selectedCity : '';
    filterPlanSites(form);
  }

  function updateClassResources(form, selectedRoom = '', selectedInstructor = '') {
    if (!form) return;
    const installationId = form.elements.instalacion_id.value;
    const instructors = (state.data.instructors || []).filter(item =>
      (item.instalacion_ids || []).map(String).includes(String(installationId)),
    );
    const rooms = (state.data.rooms || []).filter(item =>
      String(item.instalacion_id) === String(installationId),
    );
    const instructorSelect = form.elements.instructor_id;
    const roomSelect = form.elements.sala_id;
    if (instructorSelect?.tagName === 'SELECT') {
      instructorSelect.innerHTML = `<option value="">${instructors.length ? 'Selecciona un instructor' : 'No hay profesionales asignados a esta sede'}</option>${instructors.map(item => `<option value="${item.instructor_id}">${esc(item.nombre)} · ${esc(professionalLabels[item.tipo] || item.tipo)}${item.especialidad ? ` · ${esc(item.especialidad)}` : ''}</option>`).join('')}`;
      instructorSelect.disabled = !installationId || !instructors.length;
      instructorSelect.value = selectedInstructor ? String(selectedInstructor) : '';
    }
    roomSelect.innerHTML = `<option value="">${rooms.length ? 'Selecciona una sala' : 'No hay salas en esta sede'}</option>${rooms.map(item => `<option value="${item.sala_id}">${esc(item.nombre)} · ${item.capacidad} cupos</option>`).join('')}`;
    roomSelect.disabled = !installationId || !rooms.length;
    roomSelect.value = selectedRoom ? String(selectedRoom) : '';
  }

  function renderAdminField(field) {
    const required = field.required ? ' required' : '';
    let control;
    if (field.type === 'person_name') {
      const errorId = `name-error-${field.name}`;
      control = `<input name="${esc(field.name)}" type="text" minlength="3" maxlength="100" autocomplete="off" data-person-name data-name-required="${field.required}" aria-describedby="${errorId}"${required}><small class="field-validation-error hidden" id="${errorId}" aria-live="polite"></small>`;
    } else if (field.type === 'phone') {
      const errorId = `phone-error-${field.name}`;
      control = `<div class="phone-input" data-phone-field><span class="phone-prefix" aria-hidden="true">+56</span><input name="${esc(field.name)}" type="tel" inputmode="numeric" pattern="[0-9]{9}" autocomplete="tel-national" placeholder="Ingresar 9 dígitos" maxlength="9" aria-describedby="${errorId}" data-chilean-phone></div><small class="phone-error hidden" id="${errorId}" aria-live="polite">Ingresa tu número de teléfono</small>`;
    } else if (field.type === 'region') {
      control = `<select name="${esc(field.name)}" data-region-select${required}><option value="">Selecciona una región</option>${field.choices.map(value => `<option value="${esc(value)}">${esc(value)}</option>`).join('')}</select>`;
    } else if (field.type === 'city') {
      control = `<select name="${esc(field.name)}" data-city-select required disabled><option value="">Primero selecciona una región</option></select><input class="hidden" name="ciudad_otra" data-city-other maxlength="100" placeholder="Indica la ciudad o comuna" aria-label="Otra ciudad o comuna">`;
    } else if (field.type === 'textarea') {
      control = `<textarea name="${esc(field.name)}"${required}></textarea>`;
    } else if (field.type === 'bool') {
      control = `<select name="${esc(field.name)}"${required}><option value="true">Sí</option><option value="false">No</option></select>`;
    } else if (field.type === 'choice' || field.type === 'fk') {
      const options = field.type === 'choice'
        ? field.choices.map(value => {
          const label = field.name === 'tipo' && value === 'PLAN' ? 'Plan'
            : field.name === 'tipo' && value === 'MEMBRESIA' ? 'Membresía'
              : String(value).replaceAll('_', ' ');
          return `<option value="${esc(value)}">${esc(label)}</option>`;
        }).join('')
        : field.options.map(option => `<option value="${esc(option.id)}">${esc(option.label)} · #${esc(option.id)}</option>`).join('');
      control = `<select name="${esc(field.name)}"${required}><option value="">Selecciona una opción</option>${options}</select>`;
    } else {
      const inputType = field.type === 'google_maps_url' ? 'url'
        : field.type === 'password' ? 'password'
        : field.type === 'datetime' ? 'datetime-local'
          : ['int', 'decimal', 'latitude', 'longitude'].includes(field.type) ? 'number' : field.type;
      const passwordLimits = field.type === 'password'
        ? ' minlength="12" maxlength="256" autocomplete="new-password"'
        : '';
      const step = ['latitude', 'longitude'].includes(field.type)
        ? ` step="${field.step}"`
        : field.type === 'decimal' ? ' step="0.01"' : '';
      const min = ['latitude', 'longitude'].includes(field.type)
        ? ` min="${field.min}"`
        : ['int', 'decimal'].includes(field.type) ? ' min="0"' : '';
      const max = ['latitude', 'longitude'].includes(field.type) ? ` max="${field.max}"` : '';
      control = `<input name="${esc(field.name)}" type="${esc(inputType)}"${passwordLimits}${step}${min}${max}${required}>`;
      if (field.type === 'google_maps_url') {
        control += '<small class="form-hint">Pega el enlace de Google Maps compartido para la ubicación exacta de la sede.</small>';
      }
    }
    return `<label>${esc(field.label)}${control}</label>`;
  }

  async function loadAdminRecords(entity = state.adminEntityKey) {
    const selector = document.getElementById('admin-data-entity');
    const recordsTarget = document.getElementById('admin-data-records');
    const fieldsTarget = document.getElementById('admin-data-fields');
    if (!selector || !recordsTarget || !fieldsTarget) return;
    state.adminEntityKey = entity;
    selector.value = entity;
    document.getElementById('admin-data-form')?.classList.add('hidden');
    recordsTarget.innerHTML = '<div class="empty"><span class="spinner"></span> Cargando registros…</div>';
    state.adminEntityData = await api(`/api/admin/data/${encodeURIComponent(entity)}`);
    const data = state.adminEntityData;
    document.querySelector('[data-admin-create]').hidden = data.special === 'membership';
    fieldsTarget.innerHTML = data.fields.map(renderAdminField).join('');
    document.getElementById('admin-data-form-title').textContent = `Nuevo registro · ${data.label}`;
    const form = document.getElementById('admin-data-form');
    delete form.dataset.recordId;
    form.reset();
    updateCityOptions(form);
    form.classList.add('hidden');
    const records = data.records || [];
    if (!records.length) {
      recordsTarget.innerHTML = '<div class="empty">No hay registros para mostrar.</div>';
      return;
    }
    const columns = Object.keys(records[0]).filter(key => key !== 'record_key');
    const hasActions = data.special !== 'membership';
    const actionButtons = record => {
      const key = record.record_key ?? record[data.primary_key];
      const canEdit = !['credential', 'reservation', 'role-assignment', 'professional-assignment', 'membership'].includes(data.special);
      return hasActions
        ? `<td class="admin-record-actions">${canEdit ? `<button class="link" type="button" data-admin-edit="${esc(key)}">Editar</button>` : ''}<button class="link link-danger" type="button" data-admin-delete="${esc(key)}">${esc(data.delete_label)}</button></td>`
        : '';
    };
    recordsTarget.innerHTML = `<div class="table-wrap"><table><thead><tr>${columns.map(column => `<th>${esc(data.column_labels?.[column] || column.replaceAll('_', ' '))}</th>`).join('')}${hasActions ? '<th>Acciones</th>' : ''}</tr></thead><tbody>${records.map(record => `<tr data-admin-record="${esc(record.record_key ?? record[data.primary_key])}">${columns.map(column => `<td>${esc(record[column] ?? '—')}</td>`).join('')}${actionButtons(record)}</tr>`).join('')}</tbody></table></div>`;
  }

  return { locationFieldsHTML, updateCityOther, updateCityOptions, normalizeLocationPayload, parseScheduleRange, setScheduleRange, updatePlanScopeFields, filterPlanSites, updatePlanSiteCityFilter, updateClassResources, renderAdminField, loadAdminRecords };
}
