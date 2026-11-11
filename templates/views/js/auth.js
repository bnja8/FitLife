(() => {
  const form = document.getElementById('auth-form');
  const modeButtons = [...document.querySelectorAll('[data-auth-mode]')];
  const registerFields = [...document.querySelectorAll('.register-field')];
  const errorBox = document.getElementById('auth-error');
  const rutInput = document.getElementById('auth-documento');
  const rutError = document.getElementById('rut-error');
  const phoneInput = document.getElementById('auth-telefono');
  const personNameInputs = [...form.querySelectorAll('[data-person-name]')];
  const modeFromUrl = new URLSearchParams(location.search).get('crear') === '1' ? 'register' : 'login';
  const continueToClasses = new URLSearchParams(location.search).get('continuar') === 'clases';
  const continueToPlans = new URLSearchParams(location.search).get('continuar') === 'planes';
  let mode = modeFromUrl;

  function normalizeRut(value) {
    const raw = value.trim();
    if (!raw) return '';
    if (!/^[0-9.\s-]*[0-9Kk]$/.test(raw)) return null;
    const normalized = raw.replace(/[.\s-]/g, '').toUpperCase();
    const body = normalized.slice(0, -1);
    if (!/^\d{1,8}$/.test(body)) return null;
    const total = [...body].reverse().reduce(
      (sum, digit, index) => sum + Number(digit) * (index % 6 + 2), 0,
    );
    const remainder = 11 - total % 11;
    const expected = remainder === 11 ? '0' : remainder === 10 ? 'K' : String(remainder);
    return normalized.endsWith(expected) ? normalized : null;
  }

  function formatRut(value) {
    const body = value.slice(0, -1).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return `${body}-${value.slice(-1)}`;
  }

  function showRutValidation() {
    if (mode !== 'register' || !rutInput.value.trim()) {
      rutError.textContent = '';
      rutError.classList.add('hidden');
      rutInput.removeAttribute('aria-invalid');
      return true;
    }
    const valid = normalizeRut(rutInput.value) !== null;
    rutError.textContent = valid
    ? ''
    : 'Revisa el número y el dígito verificador. Puedes escribir 1.000.005-K con o sin separadores.';
    rutError.classList.toggle('hidden', valid);
    rutError.classList.toggle('rut-valid', valid);
    rutInput.setAttribute('aria-invalid', String(!valid));
    return valid;
  }

  function phoneDigits(value) {
    let digits = value.replace(/\D/g, '');
    if (digits.length === 11 && digits.startsWith('56')) digits = digits.slice(2);
    return digits.slice(0, 9);
  }

  function validatePhone(showEmpty = false) {
    const digits = phoneDigits(phoneInput.value);
    const invalid = digits.length > 0 && digits.length !== 9;
    const error = document.getElementById('auth-telefono-error');
    phoneInput.setAttribute('aria-invalid', String(invalid));
    phoneInput.closest('[data-phone-field]').classList.toggle('phone-invalid', invalid);
    error.classList.toggle('hidden', !(invalid || (showEmpty && !digits)));
    return !invalid && !(showEmpty && !digits);
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
    const invalid = (required && !value) || (value && letters < 3);
    const error = document.getElementById(`${input.id}-error`);
    input.setAttribute('aria-invalid', String(Boolean(invalid)));
    error.textContent = !value && required && showEmpty
      ? 'Este campo es obligatorio.'
      : value && letters < 3 ? 'Ingresa al menos 3 letras.' : '';
    error.classList.toggle('hidden', !error.textContent);
    return !invalid;
  }

  function setMode(nextMode) {
    mode = nextMode;
    const registering = mode === 'register';
    modeButtons.forEach(button => button.classList.toggle('active', button.dataset.authMode === mode));
    registerFields.forEach(field => field.classList.toggle('hidden', !registering));
    registerFields.forEach(field => {
      const input = field.querySelector('input');
      input.required = registering && !input.name.includes('materno') &&
        !input.name.includes('documento') && input.name !== 'telefono';
      if (input.hasAttribute('data-person-name')) {
        input.minLength = registering ? 3 : 0;
      }
    });
    document.getElementById('auth-title').textContent = registering ? 'Crea tu cuenta' : 'Inicia sesión';
    document.getElementById('auth-subtitle').textContent = registering
      ? 'Únete a FitLife y empieza a entrenar a tu manera.'
      : 'Continúa con tu cuenta para ver tu actividad.';
    document.getElementById('auth-submit').textContent = registering ? 'Crear cuenta' : 'Iniciar sesión';
    document.getElementById('password-hint').classList.toggle('hidden', !registering);
    const passwordInput = document.getElementById('auth-contrasena');
    passwordInput.autocomplete = registering ? 'new-password' : 'current-password';
    passwordInput.minLength = registering ? 12 : 0;
    passwordInput.maxLength = 256;
    const identifierInput = document.getElementById('auth-correo');
    document.getElementById('auth-identifier-label').textContent = registering
      ? 'Correo electrónico'
      : 'Correo electrónico o RUT';
    identifierInput.type = registering ? 'email' : 'text';
    identifierInput.autocomplete = registering ? 'email' : 'username';
    identifierInput.placeholder = registering ? '' : 'correo@ejemplo.cl o 12.345.678-5';
    rutInput.setAttribute('aria-invalid', 'false');
    rutError.textContent = '';
    rutError.classList.add('hidden');
    phoneInput.setAttribute('aria-invalid', 'false');
    document.getElementById('auth-telefono-error').classList.add('hidden');
    personNameInputs.forEach(input => {
      input.setAttribute('aria-invalid', 'false');
      document.getElementById(`${input.id}-error`).classList.add('hidden');
    });
    errorBox.classList.add('hidden');
  }

  modeButtons.forEach(button => button.addEventListener('click', () => setMode(button.dataset.authMode)));
  rutInput.addEventListener('input', showRutValidation);
  rutInput.addEventListener('blur', () => {
    const normalized = normalizeRut(rutInput.value);
    if (normalized) rutInput.value = formatRut(normalized);
    showRutValidation();
  });
  phoneInput.addEventListener('input', () => {
    phoneInput.value = phoneDigits(phoneInput.value);
    validatePhone();
  });
  phoneInput.addEventListener('blur', () => validatePhone());
  personNameInputs.forEach(input => {
    input.addEventListener('beforeinput', blockInvalidPersonNameInput);
    input.addEventListener('input', () => {
      cleanPersonName(input);
      validatePersonName(input);
    });
    input.addEventListener('blur', () => validatePersonName(input, true));
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (mode === 'register' && !showRutValidation()) {
      rutInput.focus();
      return;
    }
    if (mode === 'register' && personNameInputs.some(input => !validatePersonName(input, true))) {
      personNameInputs.find(input => input.getAttribute('aria-invalid') === 'true')?.focus();
      return;
    }
    if (mode === 'register' && !validatePhone()) {
      phoneInput.focus();
      return;
    }
    const submit = document.getElementById('auth-submit');
    submit.disabled = true;
    errorBox.classList.add('hidden');
    const payload = Object.fromEntries(new FormData(form));
    if (mode === 'register' && payload.rut) {
      payload.rut = normalizeRut(payload.rut);
      if (payload.telefono) payload.telefono = `+56${phoneDigits(payload.telefono)}`;
    } else if (mode === 'login') {
      payload.identificador = payload.correo;
      delete payload.correo;
    }
    try {
      const response = await fetch(mode === 'register' ? '/api/auth/register' : '/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'No fue posible acceder a tu cuenta.');
      sessionStorage.setItem('fitlife-token', data.token);
      sessionStorage.removeItem('fitlife-credential');
      location.assign(continueToClasses
        ? '/panel/?section=classes'
        : continueToPlans ? '/panel/?section=plans' : '/panel/');
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove('hidden');
    } finally {
      submit.disabled = false;
    }
  });

  setMode(mode);
})();
