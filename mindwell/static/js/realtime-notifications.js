(() => {
  const script = document.currentScript;
  const userType = script?.dataset.userType;
  if (!userType || !window.WebSocket) return;

  const toast = document.createElement('div');
  Object.assign(toast.style, {
    position: 'fixed',
    right: '1rem',
    bottom: '1rem',
    zIndex: '10000',
    display: 'none',
    maxWidth: 'min(28rem, calc(100vw - 2rem))',
    padding: '1rem 1.25rem',
    color: '#fff',
    background: '#111844',
    borderRadius: '0.75rem',
    boxShadow: '0 8px 24px rgba(17, 24, 68, .2)'
  });
  toast.setAttribute('role', 'status');
  toast.setAttribute('aria-live', 'polite');
  document.body.appendChild(toast);

  let reconnectDelay = 1000;
  let reconnectTimer;
  let socket;
  let shuttingDown = false;
  const receivedNotifications = new Set();

  function showToast(message, actionLabel, actionPath) {
    toast.replaceChildren();
    const text = document.createElement('span');
    text.textContent = message;
    toast.appendChild(text);

    if (actionLabel && actionPath) {
      const action = document.createElement('button');
      action.type = 'button';
      action.textContent = actionLabel;
      Object.assign(action.style, {
        display: 'block',
        marginTop: '0.75rem',
        padding: '0.5rem 0.75rem',
        color: '#111844',
        background: '#fff',
        border: '0',
        borderRadius: '0.4rem',
        cursor: 'pointer'
      });
      action.addEventListener('click', () => navigateWithinSite(actionPath));
      toast.appendChild(action);
    }

    toast.style.display = 'block';
    window.clearTimeout(toast.hideTimer);
    toast.hideTimer = window.setTimeout(() => {
      toast.style.display = 'none';
    }, 8000);
  }

  function navigateWithinSite(path) {
    if (typeof path !== 'string' || !path.startsWith('/')) return;
    const target = new URL(path, window.location.origin);
    if (target.origin === window.location.origin) {
      window.location.assign(target.href);
    }
  }

  function connect() {
    if (shuttingDown) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    socket = new WebSocket(`${protocol}//${window.location.host}/ws/notifications/`);

    socket.onopen = () => {
      reconnectDelay = 1000;
    };

    socket.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (error) {
        console.error('Invalid notification WebSocket payload.', error);
        return;
      }

      if (data.notification_id && receivedNotifications.has(data.notification_id)) return;
      if (data.notification_id) receivedNotifications.add(data.notification_id);

      switch (data.type) {
        case 'session_requested':
          if (userType === 'psychologue') {
            showToast(
              `${data.patient_name || 'Un patient'} a demandé une consultation.`,
              'Voir la demande',
              data.action_url
            );
          }
          break;
        case 'session_accepted':
          if (userType === 'patient') {
            showToast('Votre demande de consultation a été acceptée.');
            const destination = data.room_url || data.payment_url;
            if (destination) {
              window.setTimeout(() => navigateWithinSite(destination), 800);
            }
          }
          break;
        case 'session_rejected':
          if (userType === 'patient') {
            showToast(
              'Votre demande de consultation a été refusée.',
              'Voir mes rendez-vous',
              data.action_url
            );
          }
          break;
        case 'clinical_note':
          if (userType === 'patient') {
            showToast(
              data.message || 'Vous avez reçu une nouvelle note de votre psychologue.',
              'Lire la note',
              data.action_url
            );
          }
          break;
        default:
          break;
      }
    };

    socket.onclose = () => {
      if (shuttingDown) return;
      window.clearTimeout(reconnectTimer);
      reconnectTimer = window.setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, 30000);
    };

    socket.onerror = () => socket.close();
  }

  connect();
  window.addEventListener('beforeunload', () => {
    shuttingDown = true;
    window.clearTimeout(reconnectTimer);
    if (socket) socket.close();
  });
})();
