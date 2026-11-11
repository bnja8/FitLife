export function bindDashboardScanner(context) {
  const { state, stopScanner, toast } = context;

  document.getElementById('mobile-menu').addEventListener('click', () => {
    if (document.getElementById('sidebar').classList.contains('sidebar-open')) closeMenu();
    else openMenu();
  });
  document.getElementById('sidebar-scrim').addEventListener('click', () => {
    closeMenu();
  });
  document.getElementById('drawer-close').addEventListener('click', closeMenu);
  function openMenu() {
    document.getElementById('sidebar').classList.add('sidebar-open');
    document.getElementById('sidebar-scrim').classList.add('sidebar-scrim-open');
    document.getElementById('sidebar').setAttribute('aria-hidden', 'false');
    document.getElementById('sidebar').removeAttribute('inert');
    document.getElementById('mobile-menu').setAttribute('aria-expanded', 'true');
  }
  function closeMenu() {
    document.getElementById('sidebar').classList.remove('sidebar-open');
    document.getElementById('sidebar-scrim').classList.remove('sidebar-scrim-open');
    document.getElementById('sidebar').setAttribute('aria-hidden', 'true');
    document.getElementById('sidebar').setAttribute('inert', '');
    document.getElementById('mobile-menu').setAttribute('aria-expanded', 'false');
  }
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeMenu();
  });
  async function startScanner() {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('No hay acceso a cámara disponible. Abre FitLife en un navegador compatible mediante HTTPS o localhost.');
    }
    if (state.cameraStream) {
      stopScanner();
      return;
    }
    if (state.scanStarting) return;
    if (typeof window.jsQR !== 'function') {
      throw new Error('No se pudo cargar el lector QR. Recarga la página e inténtalo nuevamente.');
    }
    const video = document.getElementById('scanner-video');
    const button = document.getElementById('scan-camera');
    if (!video || !button) {
      throw new Error('No se encontró el área de cámara. Abre nuevamente Control de acceso.');
    }
    state.scanStarting = true;
    button.disabled = true;
    button.textContent = 'Solicitando acceso a la cámara…';
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) {
      state.scanStarting = false;
      button.disabled = false;
      button.textContent = 'Activar cámara QR';
      throw new Error('No fue posible iniciar el lector QR en este navegador.');
    }
    try {
      state.cameraStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: 'environment' } },
      });
      video.srcObject = state.cameraStream;
      await video.play();
    } catch (error) {
      stopScanner();
      if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
        throw new Error('Permite el acceso a la cámara en tu navegador para leer códigos QR.');
      }
      if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
        throw new Error('No se encontró una cámara disponible en este dispositivo.');
      }
      if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
        throw new Error('La cámara no está disponible. Comprueba que otra aplicación no la esté usando.');
      }
      throw error;
    } finally {
      state.scanStarting = false;
    }
    button.textContent = 'Detener cámara';
    state.scanTimer = setInterval(async () => {
      if (state.scanInProgress || !video.isConnected || video.readyState < 2 || !video.videoWidth) return;
      state.scanInProgress = true;
      try {
        const width = Math.min(video.videoWidth, 640);
        const height = Math.round(video.videoHeight * width / video.videoWidth);
        canvas.width = width;
        canvas.height = height;
        context.drawImage(video, 0, 0, width, height);
        const image = context.getImageData(0, 0, width, height);
        const code = window.jsQR(image.data, width, height, { inversionAttempts: 'dontInvert' });
        if (code?.data) {
          document.getElementById('access-token').value = code.data;
          stopScanner();
          document.getElementById('access-form').requestSubmit();
        }
      } catch {
        stopScanner();
        toast('No se pudo leer el código QR. Intenta de nuevo o ingresa el token manualmente.', true);
      } finally {
        state.scanInProgress = false;
      }
    }, 350);
  }

  return { closeMenu, startScanner };
}
