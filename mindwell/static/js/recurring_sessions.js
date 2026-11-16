/* Recurring sessions frontend: CSRF-safe helpers + psychologist create flow.
 *
 * The backend is plain Django JsonResponse (no DRF). Every unsafe request must
 * carry the CSRF token. These helpers centralise that so both the psychologist
 * and patient flows can reuse them.
 */
(function () {
  'use strict';

  function getCookie(name) {
    const cookieValue = document.cookie
      .split('; ')
      .find((row) => row.startsWith(name + '='));
    return cookieValue ? decodeURIComponent(cookieValue.split('=')[1]) : null;
  }

  const SAFE_METHODS = ['get', 'head', 'options', 'trace'];

  function csrfSafeMethod(method) {
    return SAFE_METHODS.indexOf((method || 'get').toLowerCase()) === -1;
  }

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.getAttribute('content')) {
      return meta.getAttribute('content');
    }
    return getCookie('csrftoken');
  }

  async function apiFetch(url, options) {
    const opts = Object.assign({ headers: {} }, options || {});
    const method = (opts.method || 'GET').toUpperCase();
    if (csrfSafeMethod(method)) {
      opts.headers = Object.assign(
        { 'X-CSRFToken': csrfToken() || '' },
        opts.headers
      );
    }
    opts.credentials = 'same-origin';
    const response = await fetch(url, opts);
    let payload = null;
    const contentType = response.headers.get('content-type') || '';
    if (contentType.indexOf('application/json') !== -1) {
      try {
        payload = await response.json();
      } catch (e) {
        payload = null;
      }
    }
    if (!response.ok) {
      const message =
        (payload && (payload.message || payload.error)) ||
        `Erreur ${response.status}`;
      throw new Error(message);
    }
    return payload || {};
  }

  function showToast(container, message, type) {
    if (!container) {
      return;
    }
    const toast = document.createElement('div');
    toast.className = 'rs-toast rs-toast--' + (type || 'info');
    toast.setAttribute('role', 'status');
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.classList.add('rs-toast--hide');
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  function bindRecurringCreateForm(root) {
    const form = root ? root.querySelector('#recurring-create-form') : null;
    if (!form) {
      return;
    }
    const toastBox = root.querySelector('#recurring-toast');
    const submitBtn = form.querySelector('button[type="submit"]');

    const countInput = form.querySelector('[name="occurrence_count"]');
    const endInput = form.querySelector('[name="end_date"]');
    const mode = form.querySelector('[name="length_mode"]');

    function syncMode() {
      const useCount = mode && mode.value === 'count';
      if (countInput) {
        countInput.disabled = !useCount;
        countInput.required = useCount;
      }
      if (endInput) {
        endInput.disabled = useCount;
        endInput.required = !useCount;
      }
    }
    if (mode) {
      mode.addEventListener('change', syncMode);
    }
    syncMode();

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (submitBtn) {
        submitBtn.disabled = true;
      }
      const formData = new FormData(form);
      const payload = {
        patient_id: Number(formData.get('patient_id')),
        weekday: Number(formData.get('weekday')),
        start_time: formData.get('start_time'),
        start_date: formData.get('start_date'),
      };
      if (mode && mode.value === 'count') {
        payload.occurrence_count = Number(formData.get('occurrence_count'));
      } else {
        payload.end_date = formData.get('end_date');
      }

      try {
        const result = await apiFetch(
          '/consultations/api/recurring-sessions/',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          }
        );
        const upcoming = result.session ? result.session.upcoming_occurrences : 0;
        showToast(
          toastBox,
          `Série créée : ${upcoming} séance(s) proposée(s).`,
          'success'
        );
        form.reset();
        syncMode();
        if (typeof window.reloadRecurringSessions === 'function') {
          window.reloadRecurringSessions();
        }
      } catch (error) {
        showToast(toastBox, error.message || 'Impossible de créer la série.', 'error');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
        }
      }
    });
  }

  function bindCancelSeriesButtons(root) {
    if (!root) {
      return;
    }
    const toastBox = root.querySelector('#recurring-toast');
    root.querySelectorAll('[data-cancel-series]').forEach((button) => {
      button.addEventListener('click', async () => {
        const sessionId = button.getAttribute('data-cancel-series');
        if (!window.confirm('Annuler toute la série ? Toutes les séances à venir seront annulées.')) {
          return;
        }
        button.disabled = true;
        try {
          await apiFetch(
            `/consultations/api/recurring-sessions/${sessionId}/cancel/`,
            { method: 'POST' }
          );
          showToast(toastBox, 'Série annulée.', 'success');
          if (typeof window.reloadRecurringSessions === 'function') {
            window.reloadRecurringSessions();
          }
        } catch (error) {
          showToast(toastBox, error.message || 'Annulation impossible.', 'error');
        } finally {
          button.disabled = false;
        }
      });
    });
  }

  async function reloadRecurringSessions() {
    const list = document.querySelector('#recurring-sessions-list');
    if (!list) {
      return;
    }
    try {
      const data = await apiFetch('/consultations/api/recurring-sessions/upcoming/', {
        method: 'GET',
      });
      renderSessionList(list, data.sessions || []);
    } catch (error) {
      /* Rendering failures are non-fatal; leave the server-rendered list. */
    }
  }

  function renderSessionList(list, sessions) {
    list.innerHTML = '';
    if (!sessions.length) {
      list.innerHTML = '<p class="muted">Aucune série récurrente configurée.</p>';
      return;
    }
    sessions.forEach((session) => {
      const card = document.createElement('div');
      card.className = 'card rs-series';
      card.innerHTML = `
        <div class="rs-series__head">
          <strong>${session.patient_name}</strong>
          <span class="rs-badge rs-badge--${session.status}">${session.status}</span>
        </div>
        <p class="muted">
          ${session.weekday_label} ${session.start_time} ·
          ${session.upcoming_occurrences} séance(s) à venir ·
          jusqu'au ${session.end_date}
        </p>
        <div class="rs-series__actions"></div>
      `;
      const actions = card.querySelector('.rs-series__actions');
      if (session.status === 'proposed') {
        actions.innerHTML =
          '<button class="btn btn-sm" data-cancel-series="' +
          session.id +
          '">Annuler la série</button>';
      }
      list.appendChild(card);
    });
    bindCancelSeriesButtons(list);
  }

  document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('recurring-block');
    if (root) {
      bindRecurringCreateForm(root);
      bindCancelSeriesButtons(root);
      window.reloadRecurringSessions = reloadRecurringSessions;
    }
    // Patient dashboard: auto-initialise when the section exists.
    const patientRoot = document.getElementById('patient-recurring-sessions');
    if (patientRoot) {
      loadPatientRecurringSessions(patientRoot);
    }
  });

  /* =========================================================
   * PATIENT DASHBOARD
   * ========================================================= */

  function loadPatientRecurringSessions(root) {
    if (!root) {
      return;
    }
    apiFetch('/consultations/api/replacements/upcoming/', {
      method: 'GET',
    })
      .then((data) => {
        renderPatientReplacements(root, data.replacements || []);
      })
      .catch((error) => {
        root.innerHTML =
          '<div class="rs-patient-error">' +
          'Impossible de charger vos séances de rattrapage. ' +
          'Veuillez réessayer.' +
          '</div>';
        if (error && error.message) {
          showToast(root.querySelector('#recurring-toast'), error.message, 'error');
        }
      });
  }

  function renderPatientReplacements(root, replacements) {
    const list = root.querySelector('#patient-series-list');
    if (!list) {
      return;
    }
    list.innerHTML = '';
    if (!replacements.length) {
      list.innerHTML =
        '<p class="muted">Aucune séance de rattrapage disponible.</p>';
      return;
    }

    replacements.forEach((item) => {
      const card = document.createElement('div');
      card.className = 'rs-patient-card';
      card.setAttribute('data-consultation-id', item.id);

      card.innerHTML = `
        <div class="rs-series__head">
          <strong>${item.psychologue_name}</strong>
          <span class="rs-badge rs-badge--proposed">À RATTRAPER</span>
        </div>
        <p class="muted">
          Séance annulée du ${item.date} à ${item.start_time} ·
          ${item.duration_minutes} min
        </p>
        <div class="rs-series__actions"></div>
      `;

      const actions = card.querySelector('.rs-series__actions');

      // Primary action: plan the free replacement through the normal booking
      // flow (no charge, no auto-created consultation).
      const planLink = document.createElement('a');
      planLink.className = 'btn btn-sm rs-btn-accept';
      planLink.href = item.book_url;
      planLink.textContent = 'Planifier le rattrapage';
      actions.appendChild(planLink);

      // Secondary action: decline the owed replacement (persisted server-side).
      const declineBtn = document.createElement('button');
      declineBtn.className = 'btn btn-sm rs-btn-decline';
      declineBtn.type = 'button';
      declineBtn.textContent = 'Refuser';
      declineBtn.addEventListener('click', () =>
        handleDeclineReplacement(item.id, declineBtn)
      );
      actions.appendChild(declineBtn);

      // Change-of-schedule request: kept as a sibling BELOW the action row so
      // the message form sits under the buttons with a clear separator.
      const noteWrap = document.createElement('div');
      noteWrap.className = 'rs-request';
      noteWrap.innerHTML = `
        <textarea class="rs-request__note" rows="2"
          placeholder="Message / Demande de changement d'horaire"></textarea>
        <button class="btn btn-sm rs-request__send" type="button">Envoyer une demande</button>
      `;
      const textarea = noteWrap.querySelector('.rs-request__note');
      const sendBtn = noteWrap.querySelector('.rs-request__send');
      sendBtn.addEventListener('click', () =>
        handleReplacementChangeRequest(item.id, textarea, sendBtn)
      );
      card.appendChild(noteWrap);

      list.appendChild(card);
    });
  }

  async function handleReplacementChangeRequest(consultationId, textarea, button) {
    const message = textarea ? textarea.value.trim() : '';
    if (!message) {
      showToast(
        document.querySelector('#recurring-toast'),
        'Veuillez saisir un message.',
        'error'
      );
      if (textarea) {
        textarea.focus();
      }
      return;
    }
    const original = button.textContent;
    button.disabled = true;
    button.textContent = 'Envoi…';
    try {
      await apiFetch(
        `/consultations/api/replacements/${consultationId}/change-request/`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message }),
        }
      );
      showToast(
        document.querySelector('#recurring-toast'),
        'Demande envoyée au psychologue.',
        'success'
      );
      if (textarea) {
        textarea.value = '';
        textarea.disabled = true;
      }
      button.textContent = 'Demande envoyée';
    } catch (error) {
      showToast(
        document.querySelector('#recurring-toast'),
        error.message || 'Envoi impossible.',
        'error'
      );
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function handleDeclineReplacement(consultationId, button) {
    if (!button) {
      return;
    }
    if (!window.confirm('Refuser cette séance de rattrapage ?')) {
      return;
    }
    const original = button.textContent;
    button.disabled = true;
    button.textContent = 'Refus…';
    try {
      await apiFetch(
        `/consultations/api/replacements/${consultationId}/decline/`,
        { method: 'POST' }
      );
      showToast(
        document.querySelector('#recurring-toast'),
        'Séance de rattrapage refusée.',
        'success'
      );
      reloadPatientRecurringSessions();
    } catch (error) {
      showToast(
        document.querySelector('#recurring-toast'),
        error.message || 'Refus impossible.',
        'error'
      );
    } finally {
      if (button.isConnected) {
        button.disabled = false;
        button.textContent = original;
      }
    }
  }

  async function handleAccept(sessionId, button) {
    if (!button) {
      return;
    }
    const occurrenceId = button.getAttribute('data-accept-occurrence');
    if (!occurrenceId) {
      return;
    }
    const original = button.textContent;
    button.disabled = true;
    button.textContent = 'Acceptation…';
    try {
      await apiFetch(
        `/consultations/api/recurring-occurrences/${occurrenceId}/accept/`,
        { method: 'POST' }
      );
      // Optimistic pre-reload visual: flip the badge and drop the accept
      // button immediately so the user sees feedback without waiting.
      const card = button.closest('.rs-patient-card');
      if (card) {
        const badge = card.querySelector('.rs-badge');
        if (badge) {
          badge.textContent = 'active';
          badge.className = 'rs-badge rs-badge--active';
        }
        button.remove();
      }
      showToast(
        document.querySelector('#recurring-toast'),
        'Série acceptée et activée. La première séance est confirmée.',
        'success'
      );
      // Server is the single source of truth: re-fetch and re-render so the new
      // next_occurrence (and the next skip button) appears without a reload.
      reloadPatientRecurringSessions();
    } catch (error) {
      showToast(
        document.querySelector('#recurring-toast'),
        error.message || 'Acceptation impossible.',
        'error'
      );
    } finally {
      if (button.isConnected) {
        button.disabled = false;
        button.textContent = original;
      }
    }
  }

  async function handleDecline(sessionId, button) {
    if (!button) {
      return;
    }
    if (!window.confirm('Refuser cette série ? Toutes les séances proposées seront annulées.')) {
      return;
    }
    const original = button.textContent;
    button.disabled = true;
    button.textContent = 'Refus…';
    try {
      await apiFetch(
        `/consultations/api/recurring-sessions/${sessionId}/decline/`,
        { method: 'POST' }
      );
      showToast(
        document.querySelector('#recurring-toast'),
        'Série refusée. Aucune séance ne sera réservée.',
        'success'
      );
      reloadPatientRecurringSessions();
    } catch (error) {
      showToast(
        document.querySelector('#recurring-toast'),
        error.message || 'Refus impossible.',
        'error'
      );
    } finally {
      if (button.isConnected) {
        button.disabled = false;
        button.textContent = original;
      }
    }
  }

  async function handleSkip(sessionId, button, occurrenceDate) {
    if (!button) {
      return;
    }
    const occurrenceId = button.getAttribute('data-skip-occurrence');
    if (!occurrenceId) {
      return;
    }
    const original = button.textContent;
    button.disabled = true;
    button.textContent = 'Annulation…';
    try {
      await apiFetch(
        `/consultations/api/recurring-occurrences/${occurrenceId}/skip/`,
        { method: 'POST' }
      );
      showToast(
        document.querySelector('#recurring-toast'),
        `Séance du ${occurrenceDate} annulée.`,
        'success'
      );
      // Server is the single source of truth: re-fetch and re-render so the
      // cancelled occurrence is dropped and the NEXT occurrence's skip button
      // appears without a full page reload. An in-place decrement alone leaves
      // the card stale (no next skip button).
      reloadPatientRecurringSessions();
    } catch (error) {
      showToast(
        document.querySelector('#recurring-toast'),
        error.message || 'Annulation impossible.',
        'error'
      );
    }
  }

  function reloadPatientRecurringSessions() {
    const root = document.getElementById('patient-recurring-sessions');
    if (root) {
      loadPatientRecurringSessions(root);
    }
  }

  window.MindWellRecurring = {
    getCookie,
    csrfSafeMethod,
    csrfToken,
    apiFetch,
    showToast,
    loadPatientRecurringSessions,
    renderPatientReplacements,
    handleDeclineReplacement,
    handleReplacementChangeRequest,
    handleAccept,
    handleDecline,
    handleSkip,
    reloadPatientRecurringSessions,
  };
})();