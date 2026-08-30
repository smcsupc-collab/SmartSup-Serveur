/* ── State ── */
let incidentType       = 'debut';
let serviceData        = null;
let allServices        = [];
let observation        = 'Service Indisponible';
let previewTimer       = null;
let mailManuallyEdited     = false;
let smsManuallyEdited      = false;
let notifManuallyEdited    = false;
let whatsappManuallyEdited = false;
let _lastMailHtml         = '';
let _lastSubjectText      = '';
let _lastSmsText          = '';
let _lastNotifMailHtml    = '';
let _lastNotifSubjectText = '';
let _lastWhatsappText     = '';
let hdTouched          = false;
let hfTouched          = false;

/* Section state */
let currentSection  = 'services';
let ranType         = 'debut';
let ranSubType      = 'ran';
let ranIncidentKind = 'coupure';
let nbnIncidentKind = 'coupure';

/* ── Listes RAN / NBN causes et actions ── */
const RAN_CAUSES_DEBUT = [
  'Investigations en cours côté GNOC',
  'Investigations en cours côté IPT',
];
const RAN_CAUSES_FIN = [
  'En attente du retour de GNOC',
  'En attente du retour de IPT',
];
const RAN_ACTIONS = [
  'En attente du retour de GNOC',
  'En attente du retour de IPT',
];
const NBN_CAUSES_DEBUT = [
  'Investigations en cours côté SOGEB',
  'Investigations en cours côté GNOC',
];
const NBN_CAUSES_FIN = [
  'En attente du retour de SOGEB',
  'En attente du retour de GNOC',
];
const NBN_ACTIONS = [
  'En attente du retour de SOGEB',
  'En attente du retour de GNOC',
];

function _getRanCauseList() {
  const isFin = (ranType === 'fin' || ranType === 'avancement');
  if (ranSubType === 'nbn') return isFin ? NBN_CAUSES_FIN : NBN_CAUSES_DEBUT;
  return isFin ? RAN_CAUSES_FIN : RAN_CAUSES_DEBUT;
}
function _getRanActionList() {
  return ranSubType === 'nbn' ? NBN_ACTIONS : RAN_ACTIONS;
}

function filterRanCauses(query) {
  const dd = document.getElementById('r-cause-dropdown');
  if (!dd) return;
  const q = query.toLowerCase().trim();
  const items = q ? _getRanCauseList().filter(c => c.toLowerCase().includes(q)) : _getRanCauseList();
  if (!items.length) { dd.classList.remove('open'); return; }
  dd.innerHTML = '';
  items.forEach(c => {
    const div = document.createElement('div');
    div.className = 'autocomplete-item';
    div.innerHTML = highlight(escHtml(c), escHtml(q));
    div.dataset.value = c;
    div.addEventListener('mousedown', e => { e.preventDefault(); pickRanCause(c); });
    dd.appendChild(div);
  });
  dd.classList.toggle('open', items.length > 0);
}
function showRanCauseDropdown() { filterRanCauses(document.getElementById('r-cause').value); }
function pickRanCause(val) {
  document.getElementById('r-cause').value = val;
  document.getElementById('r-cause-dropdown').classList.remove('open');
  schedulePreview();
}

function filterRanActions(query) {
  const dd = document.getElementById('r-action-dropdown');
  if (!dd) return;
  const q = query.toLowerCase().trim();
  const items = q ? _getRanActionList().filter(a => a.toLowerCase().includes(q)) : _getRanActionList();
  if (!items.length) { dd.classList.remove('open'); return; }
  dd.innerHTML = '';
  items.forEach(a => {
    const div = document.createElement('div');
    div.className = 'autocomplete-item';
    div.innerHTML = highlight(escHtml(a), escHtml(q));
    div.dataset.value = a;
    div.addEventListener('mousedown', e => { e.preventDefault(); pickRanAction(a); });
    dd.appendChild(div);
  });
  dd.classList.toggle('open', items.length > 0);
}
function showRanActionDropdown() { filterRanActions(document.getElementById('r-action').value); }
function pickRanAction(val) {
  document.getElementById('r-action').value = val;
  document.getElementById('r-action-dropdown').classList.remove('open');
  schedulePreview();
}

/* ── Listes standards causes / actions ── */
const ENTITIES = [
  'partenaire', 'DSI', 'GNOC', 'GOS',
  'SOGEB', 'SSPO', 'Brastorne', '6D',
  'Digitral', 'NGSER', 'Blackngreen',
];

const STD_CAUSES_DEBUT = ENTITIES.map(e => `Investigations en cours côté ${e}`);

const STD_CAUSES_FIN = ENTITIES.map(e =>
  e === 'partenaire' ? `En attente du retour du ${e}`
  : e === 'DSI'      ? `En attente du retour de la ${e}`
  :                    `En attente du retour de ${e}`
);

const STD_ACTIONS = [
  'Rétablissement de la connexion',
  'Rétablissement de la connexion avec le partenaire',
  'Redémarrage du serveur',
  'Redémarrage du Tomcat',
  'Reconnexion du compte',
  'RollBack',
  'Purge de la queue',
  'Soudure de la fibre',
  'Fin ATP',
  'Restauration du proxy',
  'En attente du rapport d\'incident',
  'Aucune action — incident non avéré',
  ...ENTITIES.map(e =>
    e === 'partenaire' ? `En attente du retour du ${e}`
    : e === 'DSI'      ? `En attente du retour de la ${e}`
    :                    `En attente du retour de ${e}`
  ),
];

function _getCausesForType() {
  if (incidentType === 'fin') return STD_CAUSES_FIN;
  return STD_CAUSES_DEBUT;
}

function _mergedCauses() {
  const std = _getCausesForType();
  const hist = serviceData?.causes || [];
  // Historiques en premier (plus pertinents), puis standards sans doublon
  const seen = new Set(hist.map(c => c.toLowerCase()));
  const extra = std.filter(c => !seen.has(c.toLowerCase()));
  return [...hist, ...extra];
}

function _mergedActions() {
  const hist = serviceData?.actions || [];
  const seen = new Set(hist.map(a => a.toLowerCase()));
  const extra = STD_ACTIONS.filter(a => !seen.has(a.toLowerCase()));
  return [...hist, ...extra];
}

/* ── Init ── */
document.addEventListener('DOMContentLoaded', async () => {
  // Pré-remplir HD à l'heure actuelle
  setNow('hd');
  setNow('r-hd');

  // Charger la liste des services
  const res = await fetch('/api/services');
  const { services } = await res.json();
  allServices = services;

  // Fermer les dropdowns au clic ailleurs
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.autocomplete-wrap')) closeAllDropdowns();
  });

  // Détecter modification manuelle des dates
  document.getElementById('hd').addEventListener('change', () => {
    hdTouched = true;
    _setFieldError('hd', false);
    const w = document.getElementById('hd-warning');
    if (w) w.style.display = 'none';
    schedulePreview();
  });

  // RAN/NBN : idem pour r-hd
  document.getElementById('r-hd').addEventListener('change', () => {
    hdTouched = true;
    schedulePreview();
  });
  document.getElementById('hf').addEventListener('change', () => {
    hfTouched = true;
    _setFieldError('hf', false);
    _updateDurationBadge();
    schedulePreview();
  });

  document.getElementById('hd').addEventListener('change', _updateDurationBadge);

  // Validation ticket en temps réel
  document.getElementById('ticket').addEventListener('input', function() {
    const ok = !this.value || TICKET_RE.test(this.value);
    _setFieldError('ticket', !ok && this.value.length > 0);
    schedulePreview();
  });

  // Navigation clavier sur les autocompletes
  document.getElementById('service-input').addEventListener('keydown', e =>
    _ddKeyNav(e, 'service-dropdown', selectService, 'service-input'));
  document.getElementById('cause').addEventListener('keydown', e =>
    _ddKeyNav(e, 'cause-dropdown', pickCause, 'cause'));
  document.getElementById('action').addEventListener('keydown', e =>
    _ddKeyNav(e, 'action-dropdown', pickAction, 'action'));
  document.getElementById('r-cause').addEventListener('keydown', e =>
    _ddKeyNav(e, 'r-cause-dropdown', pickRanCause, 'r-cause'));
  document.getElementById('r-action').addEventListener('keydown', e =>
    _ddKeyNav(e, 'r-action-dropdown', pickRanAction, 'r-action'));

  // Restaurer le brouillon de la session précédente
  _restoreDraft();
});

/* ── Helpers date ── */
function toLocalISO(date) {
  const pad = n => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function setNow(fieldId) {
  document.getElementById(fieldId).value = toLocalISO(new Date());
}

function formatDatetime(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  const pad = n => String(n).padStart(2, '0');
  return `${pad(d.getDate())}/${pad(d.getMonth()+1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/* ── TMC → label et formule cause ── */

// Retourne le label TMC à utiliser dans la cause (IT xxx → "partenaire")
function tmcLabel(tmc) {
  if (!tmc) return "l'équipe technique";
  if (tmc.trim().toUpperCase().startsWith('IT ') || tmc.trim().toUpperCase() === 'IT') {
    return 'partenaire';
  }
  return tmc;
}

// Cause par défaut pour Début / Avancement
function causeDebut(tmc) {
  return `Investigations en cours côté ${tmcLabel(tmc)}`;
}

// Cause par défaut pour Fin — "En attente du retour de [TMC]"
// avec accord français pour les cas connus
function causeFin(tmc) {
  if (!tmc) return "En attente du retour de l'équipe technique";
  const up = tmc.trim().toUpperCase();
  if (up.startsWith('IT ') || up === 'IT') {
    return "En attente du retour du partenaire";
  }
  // Cas particulier : DSI → "de la DSI"
  if (up === 'DSI') return "En attente du retour de la DSI";
  // Tous les autres : "de [TMC]"
  return `En attente du retour de ${tmc}`;
}

/* ── Type toggle ── */
function setType(type) {
  incidentType = type;
  document.getElementById('btn-debut').classList.toggle('active',       type === 'debut');
  document.getElementById('btn-avancement').classList.toggle('active',  type === 'avancement');
  document.getElementById('btn-fin').classList.toggle('active',         type === 'fin');
  document.getElementById('btn-non_avere').classList.toggle('active',   type === 'non_avere');

  // Champs fin-only (HF, Action)
  const finEls = document.querySelectorAll('.fin-only');
  finEls.forEach(el => el.style.display = (type === 'fin') ? '' : 'none');

  // Observation : boutons standard ou texte libre
  const obsButtons = document.getElementById('obs-buttons');
  const obsLibre   = document.getElementById('obs-libre');

  if (type === 'avancement') {
    obsButtons.style.display = 'none';
    obsLibre.style.display   = '';
    const def = 'Service disponible / Nous continuons à observer';
    document.getElementById('obs-text').value = def;
    observation = def;
  } else {
    obsButtons.style.display = '';
    obsLibre.style.display   = 'none';
    if (type === 'debut') {
      setObsById('obs-indispo');
    } else if (type === 'non_avere') {
      setObsById('obs-dispo');
    } else {
      setObsById('obs-dispo');
      setNow('hf');
    }
  }

  // Cause par défaut selon le type
  if (serviceData) {
    if (type === 'debut' || type === 'avancement' || type === 'non_avere') {
      document.getElementById('cause').value = causeDebut(serviceData.tmc);
    } else if (type === 'fin') {
      document.getElementById('cause').value = causeFin(serviceData.tmc);
    }
  }

  schedulePreview();
}

/* ── Observation ── */
function setObs(btn) {
  document.querySelectorAll('.obs-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  observation = btn.dataset.val;
  document.getElementById('obs-text').value = observation;
  schedulePreview();
}

function setObsById(id) {
  const btn = document.getElementById(id);
  if (btn) setObs(btn);
}

/* ── Service autocomplete ── */
function filterServices(query) {
  const dd = document.getElementById('service-dropdown');
  const q  = query.toLowerCase().trim();
  const matches = q
    ? allServices.filter(s => s.toLowerCase().includes(q)).slice(0, 40)
    : allServices.slice(0, 40);

  if (matches.length === 0) { dd.classList.remove('open'); return; }

  dd.innerHTML = '';
  matches.forEach(s => {
    const div = document.createElement('div');
    div.className = 'autocomplete-item';
    div.innerHTML = highlight(escHtml(s), escHtml(q));
    div.dataset.value = s;
    div.addEventListener('mousedown', e => { e.preventDefault(); selectService(s); });
    dd.appendChild(div);
  });
  dd.classList.toggle('open', matches.length > 0);
}

async function selectService(name) {
  document.getElementById('service-input').value = name;
  closeAllDropdowns();

  const res = await fetch(`/api/service/${encodeURIComponent(name)}`);
  if (!res.ok) return;
  serviceData = await res.json();

  // Auto-remplissage
  document.getElementById('description').value = serviceData.description || '';

  // Priorité
  const priSel = document.getElementById('priority');
  if (serviceData.priority) priSel.value = serviceData.priority;

  // Cause par défaut selon le type
  if (incidentType === 'debut' || incidentType === 'avancement') {
    document.getElementById('cause').value = causeDebut(serviceData.tmc);
  } else if (incidentType === 'fin') {
    document.getElementById('cause').value = causeFin(serviceData.tmc);
  }

  // Action : on laisse vide pour que l'utilisateur saisisse l'action réelle
  // (les suggestions historiques restent disponibles via le dropdown)
  document.getElementById('action').value = '';

  // Badges TMC / Priorité
  const meta = document.getElementById('service-meta');
  document.getElementById('meta-tmc').textContent      = serviceData.tmc      || '—';
  document.getElementById('meta-priority').textContent = serviceData.priority || '—';
  meta.style.display = 'flex';

  schedulePreview();
}

/* ── Cause autocomplete ── */
function filterCauses(query) {
  const dd = document.getElementById('cause-dropdown');
  const q  = query.toLowerCase().trim();
  const all = _mergedCauses();
  const items = q ? all.filter(c => c.toLowerCase().includes(q)) : all;
  if (items.length === 0) { dd.classList.remove('open'); return; }
  dd.innerHTML = '';
  items.forEach(c => {
    const div = document.createElement('div');
    div.className = 'autocomplete-item';
    div.innerHTML = highlight(escHtml(c), escHtml(q));
    div.dataset.value = c;
    div.addEventListener('mousedown', e => { e.preventDefault(); pickCause(c); });
    dd.appendChild(div);
  });
  dd.classList.toggle('open', items.length > 0);
}

function showCauseDropdown() {
  filterCauses(document.getElementById('cause').value);
}

function pickCause(val) {
  document.getElementById('cause').value = val;
  document.getElementById('cause-dropdown').classList.remove('open');
  schedulePreview();
}

/* ── Action autocomplete ── */
function filterActions(query) {
  const dd = document.getElementById('action-dropdown');
  const q  = query.toLowerCase().trim();
  const all = _mergedActions();
  const items = q ? all.filter(a => a.toLowerCase().includes(q)) : all;
  if (items.length === 0) { dd.classList.remove('open'); return; }
  dd.innerHTML = '';
  items.forEach(a => {
    const div = document.createElement('div');
    div.className = 'autocomplete-item';
    div.innerHTML = highlight(escHtml(a), escHtml(q));
    div.dataset.value = a;
    div.addEventListener('mousedown', e => { e.preventDefault(); pickAction(a); });
    dd.appendChild(div);
  });
  dd.classList.toggle('open', items.length > 0);
}

function showActionDropdown() {
  filterActions(document.getElementById('action').value);
}

function pickAction(val) {
  document.getElementById('action').value = val;
  document.getElementById('action-dropdown').classList.remove('open');
  schedulePreview();
}

function closeAllDropdowns() {
  document.querySelectorAll('.autocomplete-dropdown').forEach(d => d.classList.remove('open'));
}

/* ── Build payload ── */
function buildPayloadServices() {
  const obs = document.getElementById('obs-text').value.trim()
    || observation
    || 'Service Indisponible';

  const payload = {
    mode:             'services',
    type:             incidentType,
    service:          document.getElementById('service-input').value.trim(),
    ticket:           document.getElementById('ticket').value.trim(),
    priority:         document.getElementById('priority').value,
    description:      document.getElementById('description').value.trim(),
    tmc:              serviceData ? (serviceData.tmc || '') : '',
    hd:               formatDatetime(document.getElementById('hd').value),
    hf:               formatDatetime(document.getElementById('hf').value),
    cause:            document.getElementById('cause').value.trim(),
    action:           document.getElementById('action').value.trim(),
    observation:      obs,
    // Fix #5 : champs spécifiques à la notification Services
    notif_zone:        (document.getElementById('notif-zone')?.value || '').trim(),
    notif_observation: (document.getElementById('notif-observation')?.value || '').trim(),
  };

  if (mailManuallyEdited) {
    payload.custom_html_body = document.getElementById('mail-html-preview').innerHTML;
    payload.custom_subject   = document.getElementById('subject-text').textContent.trim();
  }
  if (notifManuallyEdited) {
    payload.custom_notif_html_body = document.getElementById('notif-mail-preview').innerHTML;
    payload.custom_notif_subject   = document.getElementById('notif-subject-text').textContent.trim();
  }

  return payload;
}


function buildPayloadRan() {
  const lien = ranSubType === 'ran'
    ? document.getElementById('ran-sites-text').value.trim()
    : document.getElementById('nbn-lien').value.trim();
  const checks = [];
  if (document.getElementById('chk-voix').checked) checks.push('Voix');
  if (document.getElementById('chk-sms').checked)  checks.push('SMS');
  if (document.getElementById('chk-data').checked) checks.push('Data');
  if (document.getElementById('chk-ussd').checked) checks.push('USSD');
  const payload = {
    mode:          'ran_nbn',
    sub_type:      ranSubType,
    incident_kind: ranIncidentKind,
    type:          ranType,
    ticket:        document.getElementById('r-ticket').value.trim(),
    priority:      document.getElementById('r-priority').value,
    description:   document.getElementById('r-description').value.trim(),
    hd:            formatDatetime(document.getElementById('r-hd').value),
    hf:            formatDatetime(document.getElementById('r-hf').value),
    cause:         document.getElementById('r-cause').value.trim(),
    action:        document.getElementById('r-action').value.trim(),
    lien_impacte:  lien,
    services:      checks.join(' / '),
    nbn_kind:      nbnIncidentKind,
    observation:   document.getElementById('r-obs-text').value.trim(),
    zone_impactee: document.getElementById('r-zone').value.trim(),
  };
  if (mailManuallyEdited) {
    payload.custom_html_body = document.getElementById('mail-html-preview').innerHTML;
    payload.custom_subject   = document.getElementById('subject-text').textContent.trim();
  }
  if (notifManuallyEdited) {
    payload.custom_notif_html_body = document.getElementById('notif-mail-preview').innerHTML;
    payload.custom_notif_subject   = document.getElementById('notif-subject-text').textContent.trim();
  }
  if (whatsappManuallyEdited) {
    payload.custom_whatsapp_text = document.getElementById('whatsapp-text-preview').textContent.trim();
  }
  return payload;
}

function buildPayload() {
  if (currentSection === 'ran_nbn') return buildPayloadRan();
  return buildPayloadServices();
}

/* ── Live preview ── */
function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => { refreshPreview(); _saveDraft(); }, 350);
}

async function refreshPreview() {
  const payload = buildPayload();
  if (currentSection === 'services' && (!payload.service || !payload.ticket)) return;
  if (currentSection === 'ran_nbn' && !payload.description) return;

  try {
    const res  = await fetch('/api/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.error) return;

    _lastMailHtml    = data.html_body;
    _lastSubjectText = data.subject;
    _lastSmsText     = data.sms_text;

    if (!mailManuallyEdited) {
      document.getElementById('subject-text').textContent      = data.subject;
      document.getElementById('mail-html-preview').innerHTML   = data.html_body;
    }
    if (!smsManuallyEdited) document.getElementById('sms-text-preview').textContent = data.sms_text;

    // Fix #5 : Notification disponible pour services ET ran_nbn
    if (data.notif_html_body) {
      _lastNotifMailHtml    = data.notif_html_body;
      _lastNotifSubjectText = data.notif_subject;
      if (!notifManuallyEdited) {
        document.getElementById('notif-subject-text').textContent = data.notif_subject;
        document.getElementById('notif-mail-preview').innerHTML   = data.notif_html_body;
      }
    }

    // XXL #2 : WhatsApp disponible en Services ET RAN/NBN
    if (data.whatsapp_text !== undefined) {
      const tabWa = document.getElementById('tab-whatsapp');
      const available = Boolean(data.whatsapp_text);
      if (tabWa) tabWa.style.display = available ? '' : 'none';

      if (available) {
        _lastWhatsappText = data.whatsapp_text;
        if (!whatsappManuallyEdited) document.getElementById('whatsapp-text-preview').textContent = data.whatsapp_text;
      } else if (!whatsappManuallyEdited) {
        document.getElementById('whatsapp-text-preview').textContent = '';
      }
    }

    // XXL #3 : Stocker les données pour le panneau multi-groupe
    _lastPreviewData = data;
    _lastPayload     = payload;

    // Si le panneau multi-groupe est ouvert, le rafraîchir en direct
    const mgPane = document.getElementById('pane-multigroupe');
    if (mgPane && !mgPane.classList.contains('hidden')) _refreshMultigroupe();

  } catch (_) { /* network error — ignore */ }
}

function resetMailPreview() {
  mailManuallyEdited = false;
  if (_lastMailHtml) document.getElementById('mail-html-preview').innerHTML = _lastMailHtml;
}

function resetSmsPreview() {
  smsManuallyEdited = false;
  if (_lastSmsText) document.getElementById('sms-text-preview').textContent = _lastSmsText;
}

function resetNotifPreview() {
  notifManuallyEdited = false;
  if (_lastNotifMailHtml) document.getElementById('notif-mail-preview').innerHTML = _lastNotifMailHtml;
}

function resetWhatsappPreview() {
  whatsappManuallyEdited = false;
  if (_lastWhatsappText) document.getElementById('whatsapp-text-preview').textContent = _lastWhatsappText;
}

/* ── Détection d'édition manuelle ──
   Les contenteditable peuvent déclencher un événement 'input' parasite (ex: clic dans
   une zone vide que le navigateur normalise) sans véritable modification du texte.
   On ne verrouille le rafraîchissement auto que si le contenu a réellement changé. */
function _onMailInput() {
  if (document.getElementById('mail-html-preview').innerHTML !== _lastMailHtml) mailManuallyEdited = true;
}
function _onSubjectInput() {
  if (document.getElementById('subject-text').textContent !== _lastSubjectText) mailManuallyEdited = true;
}
function _onSmsInput() {
  if (document.getElementById('sms-text-preview').textContent !== _lastSmsText) smsManuallyEdited = true;
}
function _onNotifMailInput() {
  if (document.getElementById('notif-mail-preview').innerHTML !== _lastNotifMailHtml) notifManuallyEdited = true;
}
function _onNotifSubjectInput() {
  if (document.getElementById('notif-subject-text').textContent !== _lastNotifSubjectText) notifManuallyEdited = true;
}
function _onWhatsappInput() {
  if (document.getElementById('whatsapp-text-preview').textContent !== _lastWhatsappText) whatsappManuallyEdited = true;
}

async function copyWhatsapp() {
  const payload = buildPayloadRan();
  if (!payload.description) {
    showToast('Renseignez d\'abord les champs RAN/NBN.', 'error'); return;
  }
  try {
    const res  = await fetch('/api/copy-whatsapp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    showToast(data.copied ? 'Texte WhatsApp copié !' : 'Copie impossible', data.copied ? 'success' : 'error');
  } catch (_) {
    showToast('Erreur réseau', 'error');
  }
}

/* ── Tabs ── */
function switchTab(tab) {
  ['mail', 'sms', 'notif', 'whatsapp', 'multigroupe'].forEach(t => {
    const tabEl  = document.getElementById(`tab-${t}`);
    const paneEl = document.getElementById(`pane-${t}`);
    if (tabEl)  tabEl.classList.toggle('active', t === tab);
    if (paneEl) paneEl.classList.toggle('hidden', t !== tab);
  });
  // Rafraîchir le panneau multi-groupe à chaque ouverture
  if (tab === 'multigroupe') _refreshMultigroupe();
}

/* ── Validation locale ── */
const TICKET_RE = /^[A-Za-z0-9]{10}$/;

function _setFieldError(id, hasError) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle('field-error', hasError);
  if (hasError) el.classList.remove('field-warn');
}

function _setFieldWarn(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.add('field-warn');
  el.classList.remove('field-error');
}

function _clearAllErrors() {
  document.querySelectorAll('.field-error').forEach(el => el.classList.remove('field-error'));
  document.querySelectorAll('.field-warn').forEach(el => el.classList.remove('field-warn'));
}

function validateForm() {
  _clearAllErrors();
  const p = buildPayload();
  const errors = [];

  if (currentSection === 'services') {
    if (!p.service) {
      _setFieldError('service-input', true);
      errors.push('Service impacté manquant');
    }
    if (!p.ticket) {
      _setFieldError('ticket', true);
      errors.push('Numéro de ticket manquant');
    } else if (!TICKET_RE.test(p.ticket)) {
      _setFieldWarn('ticket');
      setTimeout(() => showToast('⚠️ Ticket incorrect ou invalide — vérifiez le format (ex: 2606Q77458)', 'error'), 100);
    }
    if (!p.description) {
      _setFieldError('description', true);
      errors.push('Description manquante');
    }
    if (!p.cause) {
      _setFieldError('cause', true);
      errors.push('Cause manquante');
    }
    if (!hdTouched) {
      _setFieldError('hd', true);
      errors.push('⚠️ Date de début non modifiée — vérifiez l\'heure de début');
    }
    if (incidentType === 'fin' && !p.hf) {
      _setFieldError('hf', true);
      errors.push('Heure de fin manquante');
    }
    if (incidentType === 'fin' && !p.action) {
      _setFieldError('action', true);
      errors.push('Action corrective manquante');
    }

  } else if (currentSection === 'ran_nbn') {
    if (!p.description) {
      _setFieldError('r-description', true);
      errors.push('Description manquante');
    }
    if (!p.cause) {
      _setFieldError('r-cause', true);
      errors.push('Cause manquante');
    }
    if (!p.ticket) {
      _setFieldError('r-ticket', true);
      errors.push('Numéro de ticket manquant');
    }
    if (!p.lien_impacte) {
      errors.push(ranSubType === 'nbn' ? 'Lien impacté manquant' : 'Sites impactés manquants');
    }
    if (ranType === 'fin' && !p.hf) {
      _setFieldError('r-hf', true);
      errors.push('Heure de fin manquante');
    }
  }

  if (errors.length > 0) {
    showToast('⚠️ ' + errors[0], 'error');
    if (errors.length > 1) {
      setTimeout(() => showToast(`+ ${errors.length - 1} autre(s) champ(s) à vérifier`, 'error'), 2500);
    }
    return null;
  }
  return p;
}

/* ── Ouvrir dans Outlook (compose window) ── */
async function openInOutlook() {
  const payload = validateForm();
  if (!payload) return;

  try {
    const res  = await fetch('/api/open-in-outlook', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok) {
      const msg = data.method === 'eml'
        ? 'Fichier .eml ouvert dans votre client mail — vérifiez et envoyez.'
        : 'Email ouvert dans Outlook — vérifiez et cliquez Envoyer.';
      showToast(msg, 'success');
    } else {
      showToast('Erreur : ' + (data.error || 'inconnue'), 'error');
    }
  } catch (e) {
    showToast('Erreur réseau : ' + e.message, 'error');
  }
}

/* ── Envoyer directement ── */
async function sendMail() {
  const payload = validateForm();
  if (!payload) return;

  // Confirmation avant envoi direct — action irrécupérable
  const service = payload.service || payload.lien_impacte || '(non précisé)';
  const ticket  = payload.ticket  || '(non précisé)';
  const typeLabels = { debut: 'Début d\'incident', fin: 'Fin d\'incident',
    avancement: 'Point d\'avancement', non_avere: 'Incident non avéré' };
  const typeLabel = typeLabels[payload.type] || payload.type;

  showConfirm(
    `Envoyer ce mail directement ?`,
    `${typeLabel}\n${service}\nTicket : ${ticket}`,
    async () => {
      try {
        const res  = await fetch('/api/send-mail', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (res.ok) {
          const msg = data.method === 'eml'
            ? 'Fichier .eml créé et ouvert — vérifiez puis envoyez depuis votre client mail.'
            : 'Mail envoyé directement via Outlook !';
          showToast(msg, 'success');
        } else {
          showToast('Erreur : ' + (data.error || 'inconnue'), 'error');
        }
      } catch (e) {
        showToast('Erreur réseau : ' + e.message, 'error');
      }
    }
  );
}

/* ── Modal de confirmation générique ── */
function showConfirm(title, detail, onConfirm) {
  document.getElementById('confirm-title').textContent  = title;
  document.getElementById('confirm-detail').textContent = detail;
  document.getElementById('modal-confirm').classList.add('open');
  // Stocker le callback
  window._confirmCallback = onConfirm;
}

function closeConfirm() {
  document.getElementById('modal-confirm').classList.remove('open');
  window._confirmCallback = null;
}

function doConfirm() {
  closeConfirm();
  if (typeof window._confirmCallback === 'function') window._confirmCallback();
}

/* ── Copy SMS ── */
async function copySms() {
  const payload = buildPayload();
  // Pour les sections non-services, on permet de copier sans service
  if (currentSection === 'services' && !payload.service) {
    showToast('Sélectionnez un service avant de copier.', 'error'); return;
  }

  try {
    const res  = await fetch('/api/copy-sms', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.copied) {
      showToast('SMS copié dans le presse-papiers !', 'success');
    } else {
      // Fallback navigateur
      await navigator.clipboard.writeText(data.text || '');
      showToast('SMS copié (via navigateur).', 'info');
    }
  } catch (_) {
    showToast('Impossible de copier.', 'error');
  }
}

/* ── Toast ── */
function showToast(msg, type = 'info') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast show ${type}`;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 4000);
}

/* ── Paramètres ── */
async function openSettings() {
  const res = await fetch('/api/config');
  const cfg = await res.json();

  document.getElementById('sig-nom').value      = cfg.signature?.nom       || '';
  document.getElementById('sig-tel').value      = cfg.signature?.telephone || '';
  document.getElementById('sig-fonction').value = cfg.signature?.fonction  || '';
  document.getElementById('sig-entite').value   = cfg.signature?.entite    || '';
  document.getElementById('cfg-to').value       = (cfg.recipients_to || []).join('\n');
  document.getElementById('cfg-cc').value       = (cfg.recipients_cc || []).join('\n');
  const nTo = document.getElementById('settings-notif-to');
  const nCc = document.getElementById('settings-notif-cc');
  if (nTo) nTo.value = (cfg.recipients_notif    || []).join('\n');
  if (nCc) nCc.value = (cfg.recipients_notif_cc || []).join('\n');

  document.getElementById('modal-settings').classList.add('open');
}

function closeSettings() {
  document.getElementById('modal-settings').classList.remove('open');
}

function closeSettingsOutside(e) {
  if (e.target === document.getElementById('modal-settings')) closeSettings();
}

async function saveSettings() {
  const toLines = v => v.split('\n').map(l => l.trim()).filter(Boolean);
  const payload = {
    signature: {
      nom:       document.getElementById('sig-nom').value.trim(),
      telephone: document.getElementById('sig-tel').value.trim(),
      fonction:  document.getElementById('sig-fonction').value.trim(),
      entite:    document.getElementById('sig-entite').value.trim(),
    },
    recipients_to: toLines(document.getElementById('cfg-to').value),
    recipients_cc: toLines(document.getElementById('cfg-cc').value),
    recipients_notif: toLines((document.getElementById('settings-notif-to')?.value) || ''),
    recipients_notif_cc: toLines((document.getElementById('settings-notif-cc')?.value) || ''),
  };

  const res = await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (res.ok) {
    closeSettings();
    showToast('Paramètres sauvegardés.', 'success');
    schedulePreview();
  } else {
    showToast('Erreur : ' + (data.error || 'inconnue'), 'error');
  }
}

/* ── Parse sujet mail ── */
async function parseSubject(raw) {
  const s = raw.trim();
  if (!s) { document.getElementById('parse-badges').style.display = 'none'; return; }

  // Extraire le service COMPLET entre [ ] → valeur exacte pour "Service impacté"
  const svcMatch = s.match(/\[([^\]]+)\]/);
  const fullService = svcMatch ? svcMatch[1].trim() : null;

  // Extraire le ticket après ||
  const tkMatch = s.match(/\|\|\s*(.+)$/);
  const ticket = tkMatch ? tkMatch[1].trim() : null;

  if (!fullService && !ticket) return;

  // Mettre le texte complet entre crochets dans le champ service (email)
  if (fullService) {
    document.getElementById('service-input').value = fullService;
    document.getElementById('service-meta').style.display = 'none';
  }

  // Mettre le ticket
  if (ticket) document.getElementById('ticket').value = ticket;

  // Recherche DB : utilise les segments pour trouver description/cause/priorité
  if (fullService) await _lookupServiceDB(fullService);

  schedulePreview();

  const badges = document.getElementById('parse-badges');
  badges.innerHTML = [
    fullService ? `<span class="pbadge pbadge-service">${escHtml(fullService)}</span>` : '',
    ticket      ? `<span class="pbadge pbadge-ticket">${escHtml(ticket)}</span>` : '',
    `<span class="pbadge" style="color:var(--text-3);border-color:var(--border)">← choisir le type</span>`,
  ].join('');
  badges.style.display = 'flex';
}

async function _lookupServiceDB(fullService) {
  // Segmenter : "Orange Money add-on / Bank to Wallet / Vista Bank"
  const parts = fullService.split('/').map(p => p.trim()).filter(p => p.length > 2);

  // Ordre de recherche : dernier segment (plus spécifique) → avant-dernier → premier → texte complet
  const candidates = [...parts].reverse();
  candidates.push(fullService);

  let dbMatch = null;
  for (const cand of candidates) {
    const cLow = cand.toLowerCase();
    dbMatch = allServices.find(n => n.toLowerCase() === cLow)
           || allServices.find(n => n.toLowerCase().includes(cLow) && cLow.length > 4)
           || allServices.find(n => cLow.includes(n.toLowerCase()) && n.length > 5);
    if (dbMatch) break;
  }

  if (!dbMatch) return;

  const res = await fetch(`/api/service/${encodeURIComponent(dbMatch)}`);
  if (!res.ok) return;
  serviceData = await res.json();

  // Remplir les champs depuis la DB (sauf service-input qui garde le texte original)
  document.getElementById('description').value = serviceData.description || '';
  if (serviceData.priority) document.getElementById('priority').value = serviceData.priority;

  if (incidentType === 'debut' || incidentType === 'avancement' || incidentType === 'non_avere') {
    document.getElementById('cause').value = causeDebut(serviceData.tmc);
  } else if (incidentType === 'fin') {
    document.getElementById('cause').value = causeFin(serviceData.tmc);
  }

  document.getElementById('meta-tmc').textContent      = serviceData.tmc      || '—';
  document.getElementById('meta-priority').textContent = serviceData.priority || '—';
  document.getElementById('service-meta').style.display = 'flex';
}

function clearPaste() {
  document.getElementById('subject-paste').value = '';
  document.getElementById('parse-badges').style.display = 'none';
}

/* ── Sécurité : construction dropdown sans handlers inline ── */
function _buildDropdownItems(items, query, pickFn, ddEl) {
  ddEl.innerHTML = '';
  items.forEach(val => {
    const div = document.createElement('div');
    div.className = 'autocomplete-item';
    div.innerHTML = highlight(escHtml(val), escHtml(query));
    div.dataset.value = val;
    div.addEventListener('mousedown', e => { e.preventDefault(); pickFn(val); });
    ddEl.appendChild(div);
  });
  ddEl.classList.toggle('open', items.length > 0);
}

/* ── Navigation clavier dans les autocompletes ── */
let _ddActiveIndex = -1;

function _ddKeyNav(e, ddId, pickFn) {
  const dd = document.getElementById(ddId);
  if (!dd || !dd.classList.contains('open')) return;
  const items = dd.querySelectorAll('.autocomplete-item');
  if (!items.length) return;
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    _ddActiveIndex = Math.min(_ddActiveIndex + 1, items.length - 1);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    _ddActiveIndex = Math.max(_ddActiveIndex - 1, 0);
  } else if (e.key === 'Enter' && _ddActiveIndex >= 0) {
    e.preventDefault();
    const val = items[_ddActiveIndex].dataset.value;
    if (val) pickFn(val);
    _ddActiveIndex = -1;
    return;
  } else if (e.key === 'Escape') {
    dd.classList.remove('open');
    _ddActiveIndex = -1;
    return;
  } else { return; }
  items.forEach((el, i) => el.classList.toggle('dd-active', i === _ddActiveIndex));
}

/* ── Calcul durée HD → HF ── */
function _computeDuration(hdVal, hfVal) {
  if (!hdVal || !hfVal) return null;
  const d1 = new Date(hdVal), d2 = new Date(hfVal);
  if (isNaN(d1) || isNaN(d2) || d2 <= d1) return null;
  const diff = Math.floor((d2 - d1) / 1000);
  const h = Math.floor(diff / 3600);
  const m = Math.floor((diff % 3600) / 60);
  return h > 0 ? `${h}h ${String(m).padStart(2,'0')}min` : `${m}min`;
}

function _updateDurationBadge() {
  const hd = document.getElementById('hd')?.value;
  const hf = document.getElementById('hf')?.value;
  let badge = document.getElementById('duration-badge');
  if (!badge) {
    badge = document.createElement('span');
    badge.id = 'duration-badge';
    badge.style.cssText = 'font-size:.78rem;color:var(--text-3);margin-left:.5rem;font-weight:500;';
    const hfLabel = document.querySelector('#hf-group .field-label');
    if (hfLabel) hfLabel.appendChild(badge);
  }
  const dur = _computeDuration(hd, hf);
  badge.textContent = dur ? `— Durée : ${dur}` : '';
}

/* ── Persistance brouillon (sessionStorage) ── */
const _SS_KEY = 'smartsup_draft';

function _saveDraft() {
  try {
    const p = buildPayload();
    sessionStorage.setItem(_SS_KEY, JSON.stringify({ section: currentSection, payload: p }));
  } catch (_) {}
}

function _restoreDraft() {
  try {
    const raw = sessionStorage.getItem(_SS_KEY);
    if (!raw) return;
    const { section, payload } = JSON.parse(raw);
    if (!payload) return;
    if (section === 'services' && (payload.ticket || payload.description)) {
      if (payload.type) setType(payload.type);
      const ti = document.getElementById('ticket');
      if (ti && payload.ticket) ti.value = payload.ticket;
      const desc = document.getElementById('description');
      if (desc && payload.description) desc.value = payload.description;
      const cause = document.getElementById('cause');
      if (cause && payload.cause) cause.value = payload.cause;
      showToast('↩ Brouillon restauré depuis la session précédente.', 'info');
    }
  } catch (_) {}
}

/* ── Debounce boutons envoi ── */
function _debounceBtn(btnEl, ms = 3000) {
  if (!btnEl || btnEl._debouncing) return false;
  btnEl._debouncing = true;
  btnEl.disabled = true;
  const orig = btnEl.innerHTML;
  btnEl.innerHTML = orig.replace(/<svg[^>]*>.*?<\/svg>/s, '') + ' En cours…';
  setTimeout(() => { btnEl.disabled = false; btnEl.innerHTML = orig; btnEl._debouncing = false; }, ms);
  return true;
}

/* ── Utils ── */
function escHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function escAttr(s) {
  return String(s)
    .replace(/&/g,'&amp;')
    .replace(/"/g,'&quot;')
    .replace(/'/g,'&#39;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/\n/g,' ');
}

function highlight(text, query) {
  if (!query) return text;
  const re = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')})`, 'gi');
  return text.replace(re, '<mark style="background:rgba(255,85,0,0.3);color:inherit;border-radius:2px">$1</mark>');
}

/* ── Section switching ── */
function switchSection(section) {
  currentSection = section;
  ['services', 'ran_nbn', 'stats'].forEach(s => {
    const tab = document.getElementById(`stab-${s}`);
    if (tab) tab.classList.toggle('active', s === section);
    const el = document.getElementById(`section-${s}`);
    if (el) el.style.display = s === section ? '' : 'none';
  });

  // Charger le dashboard au premier accès
  if (section === 'stats') { loadStats(); return; }

  // Fix #5 : onglet WhatsApp uniquement en RAN/NBN ; onglet Notification toujours visible
  const showRanTabs = section === 'ran_nbn';
  document.querySelectorAll('.ran-only-tab').forEach(el => {
    el.style.display = showRanTabs ? '' : 'none';
  });

  // Champs Zone/Observation Notif : visibles seulement en mode Services
  const notifServicesFields = document.getElementById('notif-services-fields');
  if (notifServicesFields) notifServicesFields.style.display = section === 'services' ? '' : 'none';

  // Si on quitte RAN/NBN et qu'on était sur WhatsApp, revenir à Mail
  if (!showRanTabs && document.getElementById('tab-whatsapp')?.classList.contains('active')) {
    switchTab('mail');
  }

  // Reset preview on section change
  mailManuallyEdited     = false;
  smsManuallyEdited      = false;
  notifManuallyEdited    = false;
  whatsappManuallyEdited = false;
  _lastMailHtml = '';
  _lastSmsText  = '';
  _lastNotifMailHtml = '';
  _lastWhatsappText  = '';
  document.getElementById('subject-text').textContent = '—';
  document.getElementById('mail-html-preview').innerHTML =
    '<div class="preview-empty"><svg viewBox="0 0 24 24"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg><p>Renseignez les champs pour voir l\'aperçu</p></div>';
  document.getElementById('sms-text-preview').textContent = '';
  document.getElementById('notif-mail-preview').innerHTML =
    '<div class="preview-empty"><svg viewBox="0 0 24 24"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg><p>La notification apparaîtra ici</p></div>';
  document.getElementById('notif-subject-text').textContent = '—';
  document.getElementById('whatsapp-text-preview').textContent = '';
}

/* ── RAN/NBN type toggle ── */
function setTypeRan(type) {
  ranType = type;
  ['debut', 'avancement', 'fin', 'non_avere'].forEach(t => {
    document.getElementById(`r-btn-${t}`).classList.toggle('active', t === type);
  });
  document.querySelectorAll('.r-fin-only').forEach(el => {
    el.style.display = type === 'fin' ? '' : 'none';
  });
  if (type === 'fin') setNow('r-hf');
  // Mise à jour observation selon type (RAN)
  if (ranSubType === 'ran') _applyRanObsDefault(type);
  schedulePreview();
}

/* ── RAN incident kind (Coupure / Instabilité) ── */
function setRanKind(kind) {
  ranIncidentKind = kind;
  document.getElementById('rkind-coupure').classList.toggle('active',     kind === 'coupure');
  document.getElementById('rkind-instabilite').classList.toggle('active', kind === 'instabilite');
  // Changer le label du champ
  const lbl = document.getElementById('ran-field-label');
  if (lbl) lbl.textContent = kind === 'instabilite' ? 'Site instable' : 'Site coupé';
  // Refaire la description si déjà remplie
  ranSiteChanged();
}

/* ── Auto-fill quand on colle le nom du site RAN ── */
function ranSiteChanged() {
  const raw      = document.getElementById('ran-sites-text').value.trim();
  const descEl   = document.getElementById('r-description');
  const obsEl    = document.getElementById('r-obs-text');
  if (!raw) { schedulePreview(); return; }

  // Description auto
  const prefix = ranIncidentKind === 'instabilite' ? 'Instabilité sur le site' : 'Coupure du site';
  descEl.value = `${prefix} ${raw}`;

  // Observation par défaut selon le type
  _applyRanObsDefault(ranType);

  schedulePreview();
}

function _applyRanObsDefault(type) {
  if (ranSubType !== 'ran') return;
  const obsEl = document.getElementById('r-obs-text');
  if (!obsEl) return;
  if (ranIncidentKind === 'instabilite') {
    if (type === 'fin' || type === 'non_avere') {
      setRanObsById('r-obs-up', 'Site Stable');
    } else {
      setRanObsById('r-obs-instable', 'Site Instable');
    }
  } else {
    if (type === 'fin' || type === 'non_avere') {
      setRanObsById('r-obs-up', 'Site UP');
    } else {
      setRanObsById('r-obs-down', 'Site DOWN');
    }
  }
}

function setRanObs(btn) {
  document.querySelectorAll('#r-obs-buttons .obs-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('r-obs-text').value = btn.dataset.val;
  schedulePreview();
}

function setRanObsById(id, val) {
  document.querySelectorAll('#r-obs-buttons .obs-btn').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById(id);
  if (btn) {
    btn.classList.add('active');
    // Update label for instabilité case
    if (id === 'r-obs-up' && ranIncidentKind === 'instabilite') btn.dataset.val = 'Site Stable';
    else if (id === 'r-obs-up') btn.dataset.val = 'Site UP';
  }
  document.getElementById('r-obs-text').value = val;
}

/* ── Notification type toggle ── */
/* ── RAN/NBN sub-type ── */
function setSubType(sub) {
  ranSubType = sub;
  document.getElementById('rbtn-ran').classList.toggle('active', sub === 'ran');
  document.getElementById('rbtn-nbn').classList.toggle('active', sub === 'nbn');
  document.getElementById('ran-field').style.display    = sub === 'ran' ? '' : 'none';
  document.getElementById('nbn-field').style.display    = sub === 'nbn' ? '' : 'none';
  const ranKindCard = document.getElementById('ran-kind-card');
  if (ranKindCard) ranKindCard.style.display = sub === 'ran' ? '' : 'none';
  const nbnKindCard = document.getElementById('nbn-kind-card');
  if (nbnKindCard) nbnKindCard.style.display = sub === 'nbn' ? '' : 'none';
  const obsBtns = document.getElementById('r-obs-buttons');
  if (obsBtns) obsBtns.style.display = sub === 'ran' ? '' : 'none';

  // Vider tous les champs spécifiques au sous-type précédent
  ['r-description','r-cause','r-action','r-obs-text'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  document.getElementById('ran-sites-text').value = '';
  document.getElementById('nbn-lien').value        = '';
  document.getElementById('r-zone').value          = '';
  document.getElementById('r-ticket').value        = '';
  document.getElementById('r-hf').value            = '';
  setNow('r-hd');
  // Réinitialiser les checkboxes RAN
  ['chk-voix','chk-sms','chk-data','chk-ussd'].forEach(id => {
    document.getElementById(id).checked = true;
  });
  // Réinitialiser le type d'avis à début
  setTypeRan('debut');
  schedulePreview();
}

/* ── Ouvrir notification dans Outlook ── */
async function openNotifInOutlook() {
  // Fix #5 : dispatch selon la section active
  const isServices = (currentSection === 'services');
  const payload    = isServices ? buildPayloadServices() : buildPayloadRan();
  const endpoint   = isServices ? '/api/open-services-notif-outlook' : '/api/open-notif-outlook';

  if (!payload.description) {
    showToast('Renseignez d\'abord la description.', 'error'); return;
  }
  try {
    const res  = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok) {
      const msg = data.method === 'eml'
        ? 'Notification .eml ouverte dans votre client mail.'
        : 'Notification ouverte dans Outlook.';
      showToast(msg, 'success');
    } else {
      showToast('Erreur : ' + (data.error || 'inconnue'), 'error');
    }
  } catch (e) {
    showToast('Erreur réseau : ' + e.message, 'error');
  }
}

/* ── Copier SMS notification ── */
async function copyNotifSms() {
  // Fix #5 : dispatch selon la section active
  const isServices = (currentSection === 'services');
  const payload    = isServices ? buildPayloadServices() : buildPayloadRan();
  const endpoint   = isServices ? '/api/copy-services-notif-sms' : '/api/copy-notif-sms';

  if (!payload.description) {
    showToast('Renseignez d\'abord la description.', 'error'); return;
  }
  try {
    const res  = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.copied) {
      showToast('SMS notification copié !', 'success');
    } else {
      await navigator.clipboard.writeText(data.text || '');
      showToast('SMS notification copié (via navigateur).', 'info');
    }
  } catch (_) {
    showToast('Impossible de copier.', 'error');
  }
}

/* ── Fix #7 : Rechargement du catalogue ── */
async function reloadCatalog() {
  const btn = document.getElementById('btn-reload-catalog');
  if (btn) { btn.disabled = true; btn.textContent = 'Rechargement…'; }
  try {
    const res  = await fetch('/api/reload-catalog', { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      // Rafraîchir la liste locale pour l'autocomplétion
      const svcRes = await fetch('/api/services');
      const { services } = await svcRes.json();
      allServices = services;
      showToast(`Catalogue rechargé — ${data.services_count} services.`, 'success');
    } else {
      showToast('Erreur rechargement : ' + (data.error || 'inconnue'), 'error');
    }
  } catch (e) {
    showToast('Erreur réseau : ' + e.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<svg viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg> Recharger le catalogue';
    }
  }
}

/* ── NBN incident kind ── */
function setNbnKind(kind) {
  nbnIncidentKind = kind;
  document.getElementById('nkind-coupure').classList.toggle('active', kind === 'coupure');
  document.getElementById('nkind-baisse').classList.toggle('active',  kind === 'baisse_debit');
  nbnLienChanged();
}

/* ── Auto-fill NBN description dès que le lien est saisi ── */
function nbnLienChanged() {
  const lien  = document.getElementById('nbn-lien').value.trim();
  const descEl = document.getElementById('r-description');
  const obsEl  = document.getElementById('r-obs-text');
  if (!lien) { schedulePreview(); return; }

  const liens    = lien.split(',').map(l => l.trim()).filter(Boolean);
  const lienWord = liens.length > 1 ? 'liens' : 'lien';
  const prep     = liens.length > 1 ? 'des' : 'du';

  if (nbnIncidentKind === 'baisse_debit') {
    descEl.value = `Baisse de débit ${prep} ${lienWord} NBN`;
  } else {
    descEl.value = `Indisponibilité ${prep} ${lienWord} NBN`;
  }

  // Observation par défaut
  const isFin = (ranType === 'fin' || ranType === 'non_avere');
  if (nbnIncidentKind === 'baisse_debit') {
    obsEl.value = isFin ? 'Lien Normal' : 'Lien Dégradé';
  } else {
    obsEl.value = isFin ? 'Lien Up' : 'Lien Down';
  }
  schedulePreview();
}


/* ═══════════════════════════════════════════════════════════════════════
   XXL #6 — CHRONOMÈTRE D'INCIDENT
   Persist via sessionStorage (survit à F5, efface à fermeture navigateur)
   ═══════════════════════════════════════════════════════════════════════ */
const _TIMER_KEY = 'smartsup_timer_start';
let _timerInterval = null;

function startTimer() {
  // Si un timer est déjà en cours, ne rien faire
  if (sessionStorage.getItem(_TIMER_KEY)) {
    _resumeTimer();
    return;
  }
  const now = Date.now();
  sessionStorage.setItem(_TIMER_KEY, String(now));
  _resumeTimer();
  showToast('Chrono démarré — incident en cours.', 'info');

  // Cacher les boutons de démarrage, afficher le widget
  ['timer-start-row-svc', 'timer-start-row-ran'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
}

function _resumeTimer() {
  const timerEl = document.getElementById('incident-timer');
  if (timerEl) timerEl.style.display = 'flex';
  if (_timerInterval) clearInterval(_timerInterval);
  _timerInterval = setInterval(_tickTimer, 1000);
  _tickTimer();
}

function _tickTimer() {
  const start = parseInt(sessionStorage.getItem(_TIMER_KEY) || '0', 10);
  if (!start) return;
  const elapsed = Math.floor((Date.now() - start) / 1000);
  const h = Math.floor(elapsed / 3600);
  const m = Math.floor((elapsed % 3600) / 60);
  const s = elapsed % 60;
  const display = h > 0
    ? `${h}h ${String(m).padStart(2,'0')}m ${String(s).padStart(2,'0')}s`
    : `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  const el = document.getElementById('timer-display');
  if (el) el.textContent = display;
}

function stopTimer() {
  // Calculer la durée et pré-remplir HF
  const start = parseInt(sessionStorage.getItem(_TIMER_KEY) || '0', 10);
  if (start) {
    const nowISO = new Date().toISOString().slice(0, 16); // format datetime-local
    // Pré-remplir HF dans les deux modes si le champ existe
    const hfSvc = document.getElementById('hf');
    const hfRan = document.getElementById('r-hf');
    if (hfSvc && !hfSvc.value) { hfSvc.value = nowISO; hfTouched = true; }
    if (hfRan && !hfRan.value) { hfRan.value = nowISO; }
    _updateDurationBadge();
    schedulePreview();
  }

  // Nettoyer
  clearInterval(_timerInterval);
  _timerInterval = null;
  sessionStorage.removeItem(_TIMER_KEY);

  // Cacher le widget, réafficher les boutons de démarrage
  const timerEl = document.getElementById('incident-timer');
  if (timerEl) timerEl.style.display = 'none';
  ['timer-start-row-svc', 'timer-start-row-ran'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = '';
  });
  showToast('Incident clos — HF renseignée automatiquement.', 'success');
}

// Au chargement : reprendre le chrono si une session était en cours
(function _initTimer() {
  if (sessionStorage.getItem(_TIMER_KEY)) {
    _resumeTimer();
    ['timer-start-row-svc', 'timer-start-row-ran'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = 'none';
    });
  }
})();


/* ═══════════════════════════════════════════════════════════════════════
   XXL #1 — HISTORIQUE DES INCIDENTS ENVOYÉS
   ═══════════════════════════════════════════════════════════════════════ */
async function openHistory() {
  document.getElementById('modal-history').classList.add('open');
  document.getElementById('history-loading').style.display = '';
  document.getElementById('history-table').style.display   = 'none';
  document.getElementById('history-empty').style.display   = 'none';

  try {
    const res  = await fetch('/api/sent-log?limit=100');
    const data = await res.json();
    const entries = data.entries || [];

    document.getElementById('history-loading').style.display = 'none';

    if (!entries.length) {
      document.getElementById('history-empty').style.display = '';
      return;
    }

    const _MODE_LABELS = { services: 'Services', ran_nbn: 'RAN/NBN', notification: 'Notif' };
    const _TYPE_LABELS = {
      debut: 'Début', fin: 'Fin', avancement: 'Avancement', non_avere: 'Non avéré'
    };
    const _TYPE_CLASSES = {
      debut: 'hist-type-debut', fin: 'hist-type-fin',
      avancement: 'hist-type-avancement', non_avere: 'hist-type-nonavere'
    };
    const _METHOD_ICONS = {
      outlook: '<svg viewBox="0 0 24 24" width="13" height="13"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg> Outlook',
      eml:     '<svg viewBox="0 0 24 24" width="13" height="13"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg> EML',
    };

    const tbody = document.getElementById('history-tbody');
    tbody.innerHTML = entries.map(e => {
      const ts      = e.ts ? e.ts.replace('T', ' ') : '—';
      const typeLabel  = _TYPE_LABELS[e.type]  || e.type  || '—';
      const typeCls    = _TYPE_CLASSES[e.type] || '';
      const modeLabel  = _MODE_LABELS[e.mode]  || e.mode  || '—';
      const methodHtml = _METHOD_ICONS[e.method] || e.method || '—';
      const subject    = (e.subject || '—').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      const service    = (e.service || '—').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      const ticket     = (e.ticket  || '—').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      return `<tr>
        <td class="hist-ts">${ts}</td>
        <td><span class="hist-type-badge ${typeCls}">${typeLabel}</span></td>
        <td class="hist-mode">${modeLabel}</td>
        <td class="hist-service" title="${service}">${service}</td>
        <td class="hist-ticket">${ticket}</td>
        <td class="hist-subject" title="${subject}">${subject}</td>
        <td class="hist-method">${methodHtml}</td>
      </tr>`;
    }).join('');

    document.getElementById('history-table').style.display = '';
  } catch (e) {
    document.getElementById('history-loading').textContent = 'Erreur chargement : ' + e.message;
  }
}

function closeHistory() {
  document.getElementById('modal-history').classList.remove('open');
}


/* ═══════════════════════════════════════════════════════════════════════
   XXL #3 — ENVOI MULTI-GROUPE RÉGLEMENTAIRE
   Filtre ARPT : supprime détails techniques (OTDR, km, fibre, distances)
   ═══════════════════════════════════════════════════════════════════════ */

// État interne
let _lastPreviewData = null;
let _lastPayload     = null;

// Groupes de destinataires (chargés depuis config ou localStorage)
let _groupesConfig = JSON.parse(localStorage.getItem('smartsup_groupes') || 'null') || {
  grp1: [], // Com Incident & TP OGN
  grp2: [], // ARPT
  grp3: [], // Remontées QoS terrain
};

/* Filtre ARPT : retire toute mention technique sensible du sujet et corps */
function _filterArpt(subject, htmlBody, smsText) {
  // Neutraliser les références techniques dans le sujet
  let filteredSubject = subject
    .replace(/\[\s*[\d.,]+\s*(?:km|m|ml)\s*[^\]]*\]/gi, '')
    .replace(/OTDR[^,;]+/gi, '')
    .trim();

  // Patterns techniques sensibles a filtrer
  const _TECH_PATTERNS = [
    /otdr/i,
    /\bkm\b/i,
    /fibre/i,
    /distance\s*:/i,
    /rep.re\s*:/i,
    /jalonnement/i,
    /coordonn.es\s*gps/i,
    /latitude|longitude/i,
    /fourreau/i,
    /manchon/i,
    /PK\s*[\d.]+/i,
  ];

  // Supprimer les lignes SMS contenant des donnees techniques
  const filteredSms = smsText
    .split('\n')
    .filter(line => !_TECH_PATTERNS.some(rx => rx.test(line)))
    .join('\n');

  // Dans le HTML : remplacer les cellules avec donnees techniques
  let filteredHtml = htmlBody.replace(
    /(<td[^>]*>)([^<]*(otdr|[\d.,]+\s*km|fourreau|manchon|PK\s*[\d.]+)[^<]*)(<\/td>)/gi,
    '$1[Détail technique non communiqué au régulateur]$4'
  );

  return { subject: filteredSubject, htmlBody: filteredHtml, smsText: filteredSms };
}

/* Générer les 3 variantes de messages */
function _buildGroupeVariants() {
  if (!_lastPreviewData) return null;
  const d = _lastPreviewData;

  const full = {
    subject:  d.subject  || '',
    htmlBody: d.html_body || '',
    smsText:  d.sms_text  || '',
  };

  const arpt = _filterArpt(full.subject, full.htmlBody, full.smsText);

  return { grp1: full, grp2: arpt, grp3: full };
}

/* Rafraîchir l'affichage du panneau multi-groupe */
function _refreshMultigroupe() {
  const variants = _buildGroupeVariants();
  if (!variants) return;

  [1, 2, 3].forEach(n => {
    const key     = `grp${n}`;
    const variant = variants[key];
    const previewEl = document.getElementById(`mg-preview-${n}`);
    if (previewEl) {
      previewEl.textContent = variant.subject || '(aperçu non disponible)';
    }
  });
}

/* Ouvrir Outlook pour un groupe donné */
async function sendMultigroupe(groupNum) {
  const variants = _buildGroupeVariants();
  if (!variants) { showToast('Générez d\'abord un aperçu.', 'error'); return; }

  const key     = `grp${groupNum}`;
  const variant = variants[key];
  const payload = Object.assign({}, _lastPayload || {}, {
    custom_subject:  variant.subject,
    custom_html_body: variant.htmlBody,
  });

  const btn = document.querySelector(`#mg-card-${groupNum} .btn-mg-send`);
  if (!_debounceBtn(btn, 4000)) return;

  try {
    const res  = await fetch('/api/open-in-outlook', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok) {
      const labels = ['', 'Com Incident & TP OGN', 'ARPT', 'Remontées QoS'];
      showToast(`✓ Outlook ouvert — ${labels[groupNum]}`, 'success');
    } else {
      showToast('Erreur : ' + (data.error || 'inconnue'), 'error');
    }
  } catch (e) {
    showToast('Erreur réseau : ' + e.message, 'error');
  }
}

/* Copier le SMS d'un groupe */
async function copyMultigroupeSms(groupNum) {
  const variants = _buildGroupeVariants();
  if (!variants) { showToast('Générez d\'abord un aperçu.', 'error'); return; }
  const text = variants[`grp${groupNum}`].smsText;
  try {
    await navigator.clipboard.writeText(text);
    const labels = ['', 'Groupe 1', 'ARPT (filtré)', 'Terrain'];
    showToast(`SMS ${labels[groupNum]} copié !`, 'success');
  } catch (_) {
    showToast('Impossible de copier.', 'error');
  }
}

/* Envoyer les 3 groupes en séquence avec délai */
async function sendAllGroupes() {
  const variants = _buildGroupeVariants();
  if (!variants) { showToast('Générez d\'abord un aperçu.', 'error'); return; }

  const btn = document.querySelector('#pane-multigroupe .btn-primary');
  if (!_debounceBtn(btn, 12000)) return;

  const labels = ['Com Incident & TP OGN', 'ARPT (filtré)', 'Remontées QoS'];
  let sent = 0;

  for (let i = 1; i <= 3; i++) {
    const key     = `grp${i}`;
    const variant = variants[key];
    const payload = Object.assign({}, _lastPayload || {}, {
      custom_subject:   variant.subject,
      custom_html_body: variant.htmlBody,
    });
    try {
      const res = await fetch('/api/open-in-outlook', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        sent++;
        showToast(`✓ ${labels[i-1]} ouvert (${i}/3)`, 'success');
      } else {
        showToast(`✗ Erreur groupe ${i}`, 'error');
      }
    } catch (e) {
      showToast(`✗ Réseau groupe ${i} : ${e.message}`, 'error');
    }
    // Délai entre chaque ouverture Outlook pour éviter les conflits COM
    if (i < 3) await new Promise(r => setTimeout(r, 1200));
  }
  if (sent === 3) showToast('3 groupes ouverts dans Outlook — vérifiez avant d\'envoyer.', 'success');
}

/* Config groupes */
function openGroupesConfig() {
  document.getElementById('grp1-to').value = _groupesConfig.grp1.join('\n');
  document.getElementById('grp2-to').value = _groupesConfig.grp2.join('\n');
  document.getElementById('grp3-to').value = _groupesConfig.grp3.join('\n');
  document.getElementById('modal-groupes').classList.add('open');
}

function closeGroupesConfig() {
  document.getElementById('modal-groupes').classList.remove('open');
}

function saveGroupesConfig() {
  _groupesConfig = {
    grp1: document.getElementById('grp1-to').value.split('\n').map(s => s.trim()).filter(Boolean),
    grp2: document.getElementById('grp2-to').value.split('\n').map(s => s.trim()).filter(Boolean),
    grp3: document.getElementById('grp3-to').value.split('\n').map(s => s.trim()).filter(Boolean),
  };
  localStorage.setItem('smartsup_groupes', JSON.stringify(_groupesConfig));
  closeGroupesConfig();
  showToast('Configuration groupes sauvegardée.', 'success');
}


/* ═══════════════════════════════════════════════════════════════════════
   XXL #2 — WhatsApp SERVICES (copie)
   ═══════════════════════════════════════════════════════════════════════ */
async function copyWhatsappServices() {
  const payload = buildPayload();
  try {
    const res  = await fetch('/api/copy-whatsapp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.copied) {
      showToast('WhatsApp copié !', 'success');
    } else {
      await navigator.clipboard.writeText(data.text || '');
      showToast('WhatsApp copié (via navigateur).', 'info');
    }
  } catch (_) { showToast('Impossible de copier.', 'error'); }
}


/* ═══════════════════════════════════════════════════════════════════════
   XXL #5 — TEMPLATES SAUVEGARDABLES
   ═══════════════════════════════════════════════════════════════════════ */
let _templates = [];

async function loadTemplates() {
  try {
    const res  = await fetch('/api/templates');
    const data = await res.json();
    _templates = data.templates || [];
    _renderTemplates();
  } catch (_) { _templates = []; }
}

function _renderTemplates() {
  const container = document.getElementById('templates-list');
  if (!container) return;

  if (!_templates.length) {
    container.innerHTML = '<div class="tpl-empty">Aucun modèle sauvegardé.</div>';
    return;
  }

  const _MODE_LABELS = { services: 'Services', ran_nbn: 'RAN/NBN', notification: 'Notif' };
  container.innerHTML = _templates.map(t => `
    <div class="tpl-card" data-id="${t.id}">
      <div class="tpl-card-body">
        <div class="tpl-name">${escHtml(t.name)}</div>
        <div class="tpl-meta">
          <span class="tpl-badge">${_MODE_LABELS[t.mode] || t.mode}</span>
          <span class="tpl-date">${(t.updated || t.created || '').slice(0,16).replace('T',' ')}</span>
        </div>
      </div>
      <div class="tpl-actions">
        <button class="btn-tpl-load" onclick="applyTemplate('${t.id}')">Charger</button>
        <button class="btn-tpl-del"  onclick="deleteTemplate('${t.id}')">✕</button>
      </div>
    </div>
  `).join('');
}

async function saveCurrentAsTemplate() {
  const name = prompt('Nom du modèle :');
  if (!name || !name.trim()) return;
  const payload = buildPayload();
  try {
    const res = await fetch('/api/templates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim(), mode: currentSection, payload }),
    });
    if (res.ok) {
      await loadTemplates();
      showToast(`Modèle "${name.trim()}" sauvegardé.`, 'success');
    }
  } catch (_) { showToast('Erreur sauvegarde modèle.', 'error'); }
}

function applyTemplate(id) {
  const tpl = _templates.find(t => t.id === id);
  if (!tpl) return;
  const p = tpl.payload;
  if (!p) return;

  // Changer de section si besoin
  if (tpl.mode && tpl.mode !== currentSection) switchSection(tpl.mode);

  // Remplir les champs selon le mode
  if (tpl.mode === 'services' || tpl.mode === 'ran_nbn') {
    ['ticket','description','cause','action','hd','hf','observation'].forEach(id => {
      const el = document.getElementById(id) || document.getElementById('r-' + id);
      if (el && p[id.replace('r-','')] !== undefined) el.value = p[id.replace('r-','')] || '';
    });
    if (p.type) setType(p.type);
    if (p.service) {
      document.getElementById('service-input').value = p.service;
      // Déclencher la sélection du service
      selectService(p.service);
    }
  }
  closeTemplates();
  schedulePreview();
  showToast(`Modèle "${tpl.name}" chargé.`, 'success');
}

async function deleteTemplate(id) {
  const tpl = _templates.find(t => t.id === id);
  if (!tpl || !confirm(`Supprimer le modèle "${tpl.name}" ?`)) return;
  try {
    await fetch(`/api/templates/${id}`, { method: 'DELETE' });
    await loadTemplates();
    showToast('Modèle supprimé.', 'info');
  } catch (_) { showToast('Erreur suppression.', 'error'); }
}

function openTemplates() {
  loadTemplates();
  document.getElementById('modal-templates').classList.add('open');
}

function closeTemplates() {
  document.getElementById('modal-templates').classList.remove('open');
}


/* ═══════════════════════════════════════════════════════════════════════
   BOUCLE MAIL NOTIFICATION SÉPARÉE
   ═══════════════════════════════════════════════════════════════════════ */
async function sendNotifMailDirect(display = true) {
  const payload = buildPayload();
  if (!payload.description && !payload.service && !payload.lien_impacte) {
    showToast('Renseignez d\'abord les champs de l\'incident.', 'error');
    return;
  }
  try {
    const res  = await fetch('/api/send-notification-mail', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...payload, display }),
    });
    const data = await res.json();
    if (res.ok) {
      showToast(display ? 'Mail notification ouvert dans Outlook.' : 'Mail notification envoyé.', 'success');
    } else {
      showToast('Erreur : ' + (data.error || 'inconnue'), 'error');
    }
  } catch (e) {
    showToast('Erreur réseau : ' + e.message, 'error');
  }
}


/* ═══════════════════════════════════════════════════════════════════════
   XXL #4 — TABLEAU DE BORD STATISTIQUES
   ═══════════════════════════════════════════════════════════════════════ */

let _statsLoaded = false;

async function loadStats() {
  if (_statsLoaded) {
    await _refreshRecentLog();
    return;
  }
  try {
    const [statsRes, logRes] = await Promise.all([
      fetch('/api/stats'),
      fetch('/api/sent-log?limit=200'),
    ]);
    const stats = await statsRes.json();
    const log   = await logRes.json();

    // KPIs depuis catalogue
    document.getElementById('kpi-total').textContent = stats.services_count || 0;

    // KPIs depuis journal
    const entries = log.entries || [];
    const today   = new Date().toISOString().slice(0, 10);
    const month   = new Date().toISOString().slice(0, 7);

    const todayCount = entries.filter(e => (e.ts || '').startsWith(today)).length;
    const monthCount = entries.filter(e => (e.ts || '').startsWith(month)).length;
    document.getElementById('kpi-sent-today').textContent = todayCount;
    document.getElementById('kpi-sent-month').textContent = monthCount;

    // Mode le plus utilisé
    const modeCount = {};
    entries.forEach(e => { modeCount[e.mode] = (modeCount[e.mode] || 0) + 1; });
    const topMode = Object.entries(modeCount).sort((a, b) => b[1] - a[1])[0];
    const modeLabels = { services: 'Services', ran_nbn: 'RAN/NBN', notification: 'Notif' };
    document.getElementById('kpi-top-mode').textContent =
      topMode ? (modeLabels[topMode[0]] || topMode[0]) : '—';

    // Graphique top services
    _renderBarChart('chart-top-services', stats.top_services_by_history || [],
      d => d.name, d => d.incidents, '#FF6D00', 'incidents');

    // Graphique top causes
    _renderBarChart('chart-top-causes', stats.top_causes || [],
      d => d.cause, d => d.count, '#4A9EFF', 'occurrences');

    // Historique récent
    _renderRecentLog(entries.slice(0, 8));

    _statsLoaded = true;
  } catch (e) {
    console.error('Stats error:', e);
  }
}

async function _refreshRecentLog() {
  try {
    const res  = await fetch('/api/sent-log?limit=200');
    const data = await res.json();
    _renderRecentLog((data.entries || []).slice(0, 8));
  } catch (_) {}
}

function _renderBarChart(containerId, items, labelFn, valueFn, color, unit) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!items.length) {
    container.innerHTML = '<div style="color:var(--text-3);font-size:.78rem;text-align:center;padding:1.5rem">Aucune donnée</div>';
    return;
  }

  const max = Math.max(...items.map(valueFn), 1);

  container.innerHTML = items.map(item => {
    const label = labelFn(item);
    const value = valueFn(item);
    const pct   = Math.round((value / max) * 100);
    const short = label.length > 32 ? label.slice(0, 30) + '…' : label;
    return `
      <div class="chart-bar-row">
        <div class="chart-bar-label" title="${escHtml(label)}">${escHtml(short)}</div>
        <div class="chart-bar-track">
          <div class="chart-bar-fill" style="width:${pct}%;background:${color}"></div>
        </div>
        <div class="chart-bar-val">${value} <span class="chart-bar-unit">${unit}</span></div>
      </div>
    `;
  }).join('');
}

function _renderRecentLog(entries) {
  const container = document.getElementById('stats-recent-log');
  if (!container) return;
  if (!entries.length) {
    container.innerHTML = '<div style="color:var(--text-3);font-size:.78rem;text-align:center;padding:.75rem">Aucun envoi enregistré.</div>';
    return;
  }
  const _TYPE_COLORS = {
    debut: 'var(--red)', fin: 'var(--green)',
    avancement: 'var(--amber)', non_avere: 'var(--text-3)',
  };
  const _TYPE_LABELS = { debut: 'Début', fin: 'Fin', avancement: 'Avanc.', non_avere: 'N/A' };
  container.innerHTML = `
    <table style="width:100%;border-collapse:collapse;font-size:.77rem">
      ${entries.map(e => `
        <tr style="border-bottom:1px solid var(--border-soft)">
          <td style="padding:.4rem .5rem;color:var(--text-3);white-space:nowrap;font-family:var(--mono)">
            ${(e.ts || '').replace('T',' ').slice(0,16)}
          </td>
          <td style="padding:.4rem .5rem">
            <span style="color:${_TYPE_COLORS[e.type] || 'var(--text-2)'};font-weight:600;font-size:.72rem">
              ${_TYPE_LABELS[e.type] || e.type}
            </span>
          </td>
          <td style="padding:.4rem .5rem;color:var(--text-2);max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
              title="${escHtml(e.service || '')}">
            ${escHtml((e.service || '—').slice(0, 28))}
          </td>
          <td style="padding:.4rem .5rem;color:var(--text-3);font-family:var(--mono);font-size:.72rem">
            ${escHtml(e.ticket || '—')}
          </td>
        </tr>
      `).join('')}
    </table>
  `;
}


/* ═══════════════════════════════════════════════════════════════════════
   XXL #7 — EXPORT PDF RAPPORT DE CLÔTURE
   ═══════════════════════════════════════════════════════════════════════ */

async function exportPdf() {
  // Récupérer les champs du formulaire PDF (section stats)
  const service = document.getElementById('pdf-service')?.value.trim();
  const ticket  = document.getElementById('pdf-ticket')?.value.trim();
  const hd      = document.getElementById('pdf-hd')?.value;
  const hf      = document.getElementById('pdf-hf')?.value;
  const cause   = document.getElementById('pdf-cause')?.value.trim();
  const action  = document.getElementById('pdf-action')?.value.trim();

  // Pré-remplir depuis le formulaire actif si les champs PDF sont vides
  const payload = buildPayload();
  const data = {
    service: service || payload.service || payload.lien_impacte || '',
    ticket:  ticket  || payload.ticket  || '',
    hd:      hd      || payload.hd      || '',
    hf:      hf      || payload.hf      || '',
    cause:   cause   || payload.cause   || '',
    action:  action  || payload.action  || '',
    description: payload.description    || '',
    mode:    payload.mode               || 'services',
    type:    payload.type               || 'fin',
    priority: payload.priority          || '',
  };

  if (!data.service && !data.description) {
    showToast('Renseignez au moins le service ou la description.', 'error');
    return;
  }

  const btn = document.querySelector('#section-stats .btn-primary');
  if (!_debounceBtn(btn, 5000)) return;

  try {
    const res = await fetch('/api/export-pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!res.ok) {
      const err = await res.json();
      showToast('Erreur PDF : ' + (err.error || 'inconnue'), 'error');
      return;
    }

    // Télécharger le PDF
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    const ts   = new Date().toISOString().slice(0,16).replace('T','_').replace(':','-');
    a.href     = url;
    a.download = `rapport_incident_${ts}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Rapport PDF téléchargé.', 'success');
  } catch (e) {
    showToast('Erreur réseau : ' + e.message, 'error');
  }
}

/* ═══════════════════════════════════════════════════════════════════════
   SMARTSUP v4 — GESTION DES TICKETS + ADMIN + TMC
   ═══════════════════════════════════════════════════════════════════════ */

// ── État v4 ─────────────────────────────────────────────────────────────────
let _v4Types       = [];
let _v4Equipes     = [];
let _v4Tickets     = [];
let _tmcRouting    = null;
let _currentTicket = null;
let _adminTab      = 'types';

// ── Étendre switchSection ────────────────────────────────────────────────────
const _origSwitchSection = switchSection;
switchSection = function(section) {
  ['saisie','admin'].forEach(s => {
    const tab = document.getElementById(`stab-${s}`);
    if (tab) tab.classList.toggle('active', s === section);
    const el = document.getElementById(`section-${s}`);
    if (el) el.style.display = s === section ? '' : 'none';
  });
  if (section === 'saisie') { srInit(); return; }
  if (section === 'admin')  { admInit(); return; }
  _origSwitchSection(section);
};

// ════════════════════════════════════════════════════════════════════════
// SAISIE RAPIDE — documentation d'incident
// ════════════════════════════════════════════════════════════════════════
//
// Remplace l'ancien module de ticketing (Kanban, statuts, MTTR, escalade),
// retiré conformément au cadrage : le ticket appartient à l'outil du groupe.
//
// Règle d'architecture appliquée ici : ce module NE GÉNÈRE AUCUN CONTENU.
// Il collecte la saisie, la poste au serveur (/api/v5/preview) et affiche le
// HTML retourné dans une iframe isolée. Aperçu et envoi partagent donc le
// même code serveur et ne peuvent pas diverger — et la charte e-mail reste
// hors d'atteinte du thème de l'application.

const SR = {
  ref: null,            // référentiels chargés depuis /api/v5/referentiels
  type: 'debut',
  ticket: '',
  priorite: '',
  service: null,
  valeurs: {},
  incidentId: null,
  dernierApercu: null
};

const SR_LIBELLES_TYPE = {
  debut: "Avis de début",
  avancement: "Point d'avancement",
  fin: "Avis de fin",
  regularisation: "Régularisation",
  notification: "Notification ARPT"
};

// Provenance de chaque champ : « auto » = déduit par le système (modifiable),
// « saisie » = seul le superviseur peut le fournir.
const SR_CHAMPS = {
  description: { type: 'textarea', prov: 'auto' },
  debut:       { type: 'datetime', prov: 'saisie' },
  fin:         { type: 'datetime', prov: 'saisie' },
  ticket:      { type: 'lecture',  prov: 'auto' },
  cause:       { type: 'liste',    prov: 'saisie', src: 'causes' },
  action:      { type: 'liste',    prov: 'saisie', src: 'actions' },
  perimetre:   { type: 'text',     prov: 'auto' },
  zone:        { type: 'select',   prov: 'saisie', src: 'zones' },
  tmc:         { type: 'select',   prov: 'saisie', src: 'tmc' },
  observation: { type: 'liste',    prov: 'auto',   src: 'observations' }
};

// ── Chargement initial ──────────────────────────────────────────────────────
async function srInit() {
  if (SR.ref) return;
  try {
    const res = await fetch('/api/v5/referentiels');
    SR.ref = await res.json();
    srAppliquerDefauts();
    srRendreSegments();
    srRendreFormulaire();
    srRafraichirApercu();
  } catch (e) {
    console.error('Référentiels indisponibles', e);
    showToast('Impossible de charger les référentiels', 'error');
  }
}

// ── Segments (type de message) ──────────────────────────────────────────────
function srAppliquerEtat() {
  const section = document.getElementById('section-saisie');
  if (!section) return;
  const etat = {
    debut: 'debut',
    avancement: 'avancement',
    fin: 'fin',
    regularisation: 'regularisation',
    notification: 'notification'
  }[SR.type] || 'debut';
  section.dataset.etat = etat;
  const texte = document.getElementById('sr-etat-texte');
  if (texte) texte.textContent = SR_LIBELLES_TYPE[SR.type] || "Avis d'incident";
}

function srRendreSegments() {
  const zone = document.getElementById('sr-segments');
  if (!zone || !SR.ref) return;
  srAppliquerEtat();
  zone.innerHTML = Object.keys(SR.ref.structure).map(k =>
    `<div class="sr-segment ${k === SR.type ? 'actif' : ''}" data-t="${k}">${escHtml(SR_LIBELLES_TYPE[k] || k)}</div>`
  ).join('');
  zone.querySelectorAll('.sr-segment').forEach(el => {
    el.onclick = () => {
      SR.type = el.dataset.t;
      srAppliquerDefauts();
      srRendreSegments();
      srRendreFormulaire();
      srRafraichirApercu();
    };
  });
}

// ── Auto-complétion service (catalogue servi par l'API) ─────────────────────
let srResultats = [], srIdxActif = -1, srTimer = null;

function srChercherService(q) {
  clearTimeout(srTimer);
  if (q.trim().length < 2) {
    srResultats = [];
    srRendreSuggestions();
    return;
  }
  srTimer = setTimeout(async () => {
    try {
      const res = await fetch('/api/v5/services?q=' + encodeURIComponent(q));
      const data = await res.json();
      srResultats = (data.services || []).slice(0, 40);
      srIdxActif = -1;
      srRendreSuggestions();
    } catch (e) {
      console.error('Recherche service', e);
    }
  }, 140);
}

function srRendreSuggestions() {
  const box = document.getElementById('sr-suggestions');
  if (!box) return;
  if (!srResultats.length) { box.classList.remove('ouvert'); return; }
  box.innerHTML = srResultats.map((s, i) => `
    <div class="sr-suggestion ${i === srIdxActif ? 'actif' : ''}" data-i="${i}">
      <b>${escHtml(s.nom)}</b>
      <span class="sr-pastille ${s.priorite === 'P1' ? 'p1' : ''}">${escHtml(s.priorite || '—')}</span>
      <span class="sr-meta">${escHtml(s.domaine)}${s.supervise ? '' : ' · non supervisé'}</span>
    </div>`).join('');
  box.classList.add('ouvert');
  box.querySelectorAll('.sr-suggestion').forEach(el => {
    el.onmousedown = e => { e.preventDefault(); srChoisirService(srResultats[+el.dataset.i]); };
  });
}

function srChoisirService(s) {
  SR.service = s;
  const champ = document.getElementById('sr-service');
  if (champ) champ.value = s.nom;
  document.getElementById('sr-puits-service')?.classList.add('ok');
  document.getElementById('sr-suggestions')?.classList.remove('ouvert');
  srResultats = []; srIdxActif = -1;
  if (!SR.priorite) SR.priorite = s.priorite || '';
  srAppliquerDefauts();
  srRendreFormulaire();
  srRafraichirApercu();
}

// ── Pré-remplissage ─────────────────────────────────────────────────────────
function srAppliquerDefauts() {
  if (!SR.ref) return;
  const v = SR.service;

  if (v) {
    if (!SR.valeurs._descTouche) SR.valeurs.description = srDescriptionAuto(v);
    if (!SR.valeurs._perimTouche) SR.valeurs.perimetre = v.domaine + ' / ' + v.nom;
  }
  if (!SR.valeurs._obsTouche) {
    const opts = (SR.ref.suggestions.observations || {})[SR.type] || [];
    SR.valeurs.observation = opts[0] || '';
  }
  if (SR.type === 'notification' && !SR.valeurs._tmcTouche) {
    SR.valeurs.tmc = (SR.ref.suggestions.tmc || [])[0] || '';
  }
}

function srDescriptionAuto(s) {
  const d = (s.domaine || '').toLowerCase();
  if (d.includes('bank to wallet')) return 'Indisponibilité du service ' + s.domaine + ' / ' + s.nom;
  if (d.includes('orange money'))   return "Impossible d'effectuer des opérations " + s.nom;
  if (d.includes('voix'))           return 'Perturbation du service ' + s.nom;
  return 'Indisponibilité du service ' + s.nom;
}

// ── Formulaire ──────────────────────────────────────────────────────────────
function srOptions(src) {
  if (!SR.ref) return [];
  if (src === 'observations') return (SR.ref.suggestions.observations || {})[SR.type] || [];
  return SR.ref.suggestions[src] || [];
}

function srRendreFormulaire() {
  const zone = document.getElementById('sr-formulaire');
  if (!zone || !SR.ref) return;
  const champs = SR.ref.structure[SR.type].champs;

  zone.innerHTML = champs.map(c => {
    const def = SR_CHAMPS[c];
    if (!def) return '';
    const label = SR.ref.libelles[c] || c;
    const val = c === 'ticket' ? srTicketAffiche() : (SR.valeurs[c] || '');
    const aSaisir = def.prov === 'saisie';
    const cls = `sr-champ ${aSaisir ? 'a-saisir' : ''} ${aSaisir && !val ? 'vide' : ''}`;
    const marq = `<span class="sr-marqueur ${def.prov}">${aSaisir ? 'à saisir' : 'auto'}</span>`;
    let ctrl = '';

    if (def.type === 'lecture') {
      ctrl = `<input value="${escAttr(val)}" readonly>`;
    } else if (def.type === 'textarea') {
      ctrl = `<textarea data-c="${c}">${escHtml(val)}</textarea>`;
    } else if (def.type === 'datetime') {
      ctrl = `<div class="sr-duo">
                <input type="datetime-local" data-c="${c}" value="${escAttr(val)}">
                <button class="sr-mini" data-now="${c}">maintenant</button>
              </div>`;
    } else if (def.type === 'select') {
      ctrl = `<select data-c="${c}">${srOptions(def.src).map(o =>
                `<option ${o === val ? 'selected' : ''}>${escHtml(o)}</option>`).join('')}</select>`;
    } else if (def.type === 'liste') {
      const opts = srOptions(def.src);
      ctrl = `<div class="sr-duo">
                <input data-c="${c}" value="${escAttr(val)}" list="sr-l-${c}" placeholder="…">
                <button class="sr-mini" data-cycle="${c}">proposer</button>
              </div>
              <datalist id="sr-l-${c}">${opts.map(o => `<option value="${escAttr(o)}">`).join('')}</datalist>`;
    } else {
      ctrl = `<input data-c="${c}" value="${escAttr(val)}">`;
    }
    return `<div class="${cls}"><div class="sr-etiquette">${escHtml(label)}${marq}</div>${ctrl}</div>`;
  }).join('');

  zone.querySelectorAll('[data-c]').forEach(el => {
    const maj = () => {
      const c = el.dataset.c;
      SR.valeurs[c] = el.value;
      if (c === 'description') SR.valeurs._descTouche = true;
      if (c === 'perimetre')   SR.valeurs._perimTouche = true;
      if (c === 'observation') SR.valeurs._obsTouche = true;
      if (c === 'tmc')         SR.valeurs._tmcTouche = true;
      srMajJauge();
      srMajClasses();
      srRafraichirApercu();
    };
    el.oninput = maj;
    el.onchange = maj;
  });

  zone.querySelectorAll('[data-now]').forEach(b => {
    b.onclick = () => {
      const d = new Date();
      d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
      SR.valeurs[b.dataset.now] = d.toISOString().slice(0, 16);
      srRendreFormulaire(); srRafraichirApercu();
    };
  });

  zone.querySelectorAll('[data-cycle]').forEach(b => {
    b.onclick = () => {
      const c = b.dataset.cycle;
      const opts = srOptions(SR_CHAMPS[c].src);
      if (!opts.length) return;
      SR.valeurs[c] = opts[(opts.indexOf(SR.valeurs[c]) + 1) % opts.length];
      if (c === 'observation') SR.valeurs._obsTouche = true;
      srRendreFormulaire(); srRafraichirApercu();
    };
  });

  srMajJauge();
}

function srMajClasses() {
  document.querySelectorAll('#sr-formulaire .sr-champ.a-saisir').forEach(el => {
    const ctrl = el.querySelector('[data-c]');
    if (ctrl) el.classList.toggle('vide', !ctrl.value);
  });
}

// ── Jauge de complétude ─────────────────────────────────────────────────────
function srManquants() {
  const liste = [];
  if (!SR.ticket) liste.push('n° ticket');
  if (!SR.service) liste.push('service');
  if (!SR.ref) return liste;
  SR.ref.structure[SR.type].champs.forEach(c => {
    const def = SR_CHAMPS[c];
    if (def && def.prov === 'saisie' && !SR.valeurs[c]) {
      liste.push((SR.ref.libelles[c] || c).toLowerCase());
    }
  });
  return liste;
}

function srMajJauge() {
  const txt = document.getElementById('sr-jauge-texte');
  const barre = document.getElementById('sr-jauge-barre');
  if (!txt || !barre || !SR.ref) return;

  const manque = srManquants();
  let total = 2;
  SR.ref.structure[SR.type].champs.forEach(c => {
    if (SR_CHAMPS[c] && SR_CHAMPS[c].prov === 'saisie') total++;
  });
  const fait = total - manque.length;
  const pret = manque.length === 0;

  txt.className = 'sr-jauge-texte' + (pret ? ' pret' : '');
  txt.textContent = pret
    ? `Prêt à envoyer · ${total}/${total}`
    : `${fait}/${total} · reste ${manque.join(', ')}`;
  barre.className = 'sr-jauge-barre' + (pret ? ' pret' : '');
  barre.style.width = Math.round(total ? fait / total * 100 : 0) + '%';
}

// ── Aperçu : rendu SERVEUR affiché dans une iframe isolée ───────────────────
function srTicketAffiche() {
  if (!SR.ticket) return '';
  return SR.ticket + (SR.priorite ? ' / ' + SR.priorite : '');
}

let srTimerApercu = null;

function srRafraichirApercu() {
  clearTimeout(srTimerApercu);
  srTimerApercu = setTimeout(srDemanderApercu, 220);
}

async function srDemanderApercu() {
  const iframe = document.getElementById('sr-apercu');
  if (!iframe) return;

  const charge = {
    type_message: SR.type,
    reference_externe: SR.ticket,
    priorite: SR.priorite,
    perimetre: SR.valeurs.perimetre || '',
    description: SR.valeurs.description || '',
    date_debut: SR.valeurs.debut || '',
    date_fin: SR.valeurs.fin || '',
    cause: SR.valeurs.cause || '',
    action: SR.valeurs.action || '',
    zone: SR.valeurs.zone || '',
    tmc: SR.valeurs.tmc || '',
    observation: SR.valeurs.observation || '',
    superviseur: (SR.ref && SR.ref.superviseurs && SR.ref.superviseurs[0]) || {}
  };

  try {
    const res = await fetch('/api/v5/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(charge)
    });
    const data = await res.json();
    SR.dernierApercu = data;

    // Le HTML du serveur est injecté tel quel dans une iframe : le thème de
    // l'application ne peut pas atteindre la charte e-mail.
    iframe.srcdoc = data.corps_html;

    const env = document.getElementById('sr-enveloppe');
    if (env) {
      env.innerHTML = `
        <div><b>Objet</b> ${escHtml(data.sujet)}</div>
        <div><b>À</b> ${escHtml((data.destinataires_a || []).join('; ') || '—')}</div>
        <div><b>Cc</b> ${escHtml((data.destinataires_cc || []).join('; ') || '—')}</div>`;
    }

    const glose = document.getElementById('sr-glose');
    if (glose) {
      glose.innerHTML = SR.type === 'notification'
        ? `Gabarit <b>notification ARPT</b> : ni dates ni référence de ticket, mais zone impactée et TMC.`
        : `Gabarit interne. Aperçu généré par le serveur — c'est exactement le message qui partira.`;
    }
  } catch (e) {
    console.error('Aperçu indisponible', e);
  }
}

// ── Enregistrement ──────────────────────────────────────────────────────────
async function srEnregistrer() {
  const manque = srManquants();
  if (manque.length) {
    showToast('Il reste à renseigner : ' + manque.join(', '), 'error');
    return;
  }
  const charge = {
    reference_externe: SR.ticket,
    type_incident: SR.type === 'notification' ? 'service' : 'service',
    priorite: SR.priorite,
    description: SR.valeurs.description || '',
    date_debut: (SR.valeurs.debut || '').replace('T', ' '),
    date_fin: (SR.valeurs.fin || '').replace('T', ' ') || null,
    cause: SR.valeurs.cause || null,
    action: SR.valeurs.action || null,
    observation: SR.valeurs.observation || null,
    perimetre_libre: SR.valeurs.perimetre || null,
    statut_documentaire: SR.type === 'regularisation' ? 'regularise'
                        : (SR.valeurs.fin ? 'cloture' : 'signale'),
    services: SR.service ? [SR.service.id] : []
  };
  try {
    const res = await fetch('/api/v5/incidents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(charge)
    });
    const data = await res.json();
    if (!data.ok) { showToast(data.error || 'Échec', 'error'); return; }
    SR.incidentId = data.id;

    // Journalise la communication avec un instantané du contenu envoyé.
    if (SR.dernierApercu) {
      await fetch(`/api/v5/incidents/${data.id}/communications`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          canal: SR.type === 'notification' ? 'notification_arpt' : 'email',
          type_message: SR.type,
          sujet: SR.dernierApercu.sujet,
          corps: SR.dernierApercu.corps_html,
          destinataires_a: SR.dernierApercu.destinataires_a,
          destinataires_cc: SR.dernierApercu.destinataires_cc
        })
      });
    }
    showToast('Incident ' + SR.ticket + ' enregistré', 'success');
  } catch (e) {
    console.error(e);
    showToast('Erreur réseau', 'error');
  }
}

// ── Copie ───────────────────────────────────────────────────────────────────
async function srCopier(brut) {
  if (!SR.dernierApercu) return;
  const texte = SR.dernierApercu.corps_texte || '';
  const html = SR.dernierApercu.corps_html || '';

  const copierTexteSecours = () => new Promise((resolve, reject) => {
    const zone = document.createElement('textarea');
    zone.value = texte;
    zone.setAttribute('readonly', '');
    zone.style.position = 'fixed';
    zone.style.opacity = '0';
    document.body.appendChild(zone);
    zone.select();
    zone.setSelectionRange(0, zone.value.length);
    const ok = document.execCommand('copy');
    zone.remove();
    ok ? resolve() : reject(new Error('Copie indisponible'));
  });

  try {
    if (!navigator.clipboard) {
      await copierTexteSecours();
    } else if (brut || !navigator.clipboard.write) {
      await navigator.clipboard.writeText(texte);
    } else {
      await navigator.clipboard.write([new ClipboardItem({
        'text/html': new Blob([html], { type: 'text/html' }),
        'text/plain': new Blob([texte], { type: 'text/plain' })
      })]);
    }
    showToast('Message copié', 'success');
  } catch (e) {
    try {
      await copierTexteSecours();
      showToast('Copié en texte', 'success');
    } catch (fallbackError) {
      console.error('Copie indisponible', fallbackError);
      showToast('Copie bloquée par le navigateur', 'error');
    }
  }
}

// ── Outlook local / fichier EML ────────────────────────────────────────────
// Le navigateur contacte un agent Windows privé, exposé uniquement dans le
// tailnet Tailscale. Le secret reste dans sessionStorage sur l'appareil de
// l'opérateur et n'est jamais conservé par Render.
function srAgentConfig() {
  let url = sessionStorage.getItem('smartsup.agent.url') || '';
  let token = sessionStorage.getItem('smartsup.agent.token') || '';

  if (!url || !token) {
    url = window.prompt(
      "URL HTTPS de l'agent Outlook local (Tailscale Serve) :",
      url || ''
    ) || '';
    if (!url) return null;
    token = window.prompt("Jeton de l'agent Outlook local :") || '';
    if (!token) return null;
    sessionStorage.setItem('smartsup.agent.url', url.replace(/\/$/, ''));
    sessionStorage.setItem('smartsup.agent.token', token);
  }
  return { url: url.replace(/\/$/, ''), token };
}

async function srOuvrirOutlookLocal() {
  if (!SR.dernierApercu) {
    showToast('Générez d’abord un aperçu.', 'error');
    return;
  }
  const cfg = srAgentConfig();
  if (!cfg) return;

  try {
    const res = await fetch(cfg.url + '/v1/outlook/draft', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-SmartSup-Agent-Token': cfg.token
      },
      body: JSON.stringify({
        to: SR.dernierApercu.destinataires_a || [],
        cc: SR.dernierApercu.destinataires_cc || [],
        subject: SR.dernierApercu.sujet || '',
        html_body: SR.dernierApercu.corps_html || ''
      })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || 'Agent Outlook indisponible');
    }
    showToast('Brouillon ouvert dans Outlook local.', 'success');
  } catch (e) {
    console.error('Agent Outlook', e);
    showToast('Outlook local : ' + e.message, 'error');
  }
}

function srTelechargerEml() {
  if (!SR.dernierApercu) {
    showToast('Générez d’abord un aperçu.', 'error');
    return;
  }
  const p = SR.dernierApercu;
  const b64 = text => btoa(unescape(encodeURIComponent(text)));
  const encodeHeader = text => '=?UTF-8?B?' + b64(text || '') + '?=';
  const addresses = values => (values || []).join('; ');
  const lines = [
    'MIME-Version: 1.0',
    'Content-Type: text/html; charset="utf-8"',
    'Content-Transfer-Encoding: base64',
    'Subject: ' + encodeHeader(p.sujet || ''),
    'To: ' + addresses(p.destinataires_a),
    p.destinataires_cc?.length ? 'Cc: ' + addresses(p.destinataires_cc) : '',
    '',
    b64(p.corps_html || '')
  ].filter(Boolean).join('\r\n');
  const blob = new Blob([lines], { type: 'message/rfc822' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'smartsup_' + (SR.ticket || 'brouillon') + '.eml';
  link.click();
  URL.revokeObjectURL(link.href);
  showToast('Fichier .eml téléchargé : ouvrez-le avec Outlook.', 'success');
}

function srVider() {
  SR.ticket = ''; SR.priorite = ''; SR.service = null;
  SR.valeurs = {}; SR.incidentId = null;
  const t = document.getElementById('sr-ticket');
  const s = document.getElementById('sr-service');
  if (t) t.value = ''; if (s) s.value = '';
  document.getElementById('sr-puits-ticket')?.classList.remove('ok');
  document.getElementById('sr-puits-service')?.classList.remove('ok');
  srAppliquerDefauts(); srRendreFormulaire(); srRafraichirApercu();
}

// ── Branchements ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const champTicket = document.getElementById('sr-ticket');
  if (champTicket) {
    champTicket.addEventListener('input', e => {
      // Tolère un collage brut du type « 2608N90290/ P1 »
      const brut = e.target.value;
      const ref = brut.match(/\d{4}[A-Za-z]\d{5}/);
      const pri = brut.match(/\bP[1-3]\b/i);
      SR.ticket = ref ? ref[0].toUpperCase() : brut.trim();
      if (pri) SR.priorite = pri[0].toUpperCase();
      else if (SR.service) SR.priorite = SR.service.priorite || '';
      document.getElementById('sr-puits-ticket')?.classList.toggle('ok', !!ref);
      srRendreFormulaire(); srRafraichirApercu();
    });
  }

  const champService = document.getElementById('sr-service');
  if (champService) {
    champService.addEventListener('input', e => {
      SR.service = null;
      document.getElementById('sr-puits-service')?.classList.remove('ok');
      srChercherService(e.target.value);
    });
    champService.addEventListener('keydown', e => {
      if (!srResultats.length) return;
      if (e.key === 'ArrowDown') { e.preventDefault(); srIdxActif = Math.min(srIdxActif + 1, srResultats.length - 1); srRendreSuggestions(); }
      if (e.key === 'ArrowUp')   { e.preventDefault(); srIdxActif = Math.max(srIdxActif - 1, 0); srRendreSuggestions(); }
      if (e.key === 'Enter' && srIdxActif >= 0) { e.preventDefault(); srChoisirService(srResultats[srIdxActif]); }
      if (e.key === 'Escape') document.getElementById('sr-suggestions')?.classList.remove('ouvert');
    });
    champService.addEventListener('blur', () => {
      setTimeout(() => document.getElementById('sr-suggestions')?.classList.remove('ouvert'), 120);
    });
  }

  document.getElementById('sr-btn-enregistrer')?.addEventListener('click', srEnregistrer);
  document.getElementById('sr-btn-copier')?.addEventListener('click', () => srCopier(false));
  document.getElementById('sr-btn-texte')?.addEventListener('click', () => srCopier(true));
  document.getElementById('sr-btn-outlook')?.addEventListener('click', srOuvrirOutlookLocal);
  document.getElementById('sr-btn-eml')?.addEventListener('click', srTelechargerEml);
  document.getElementById('sr-btn-vider')?.addEventListener('click', srVider);
});
// ════════════════════════════════════════════════════════════════════════
// ADMINISTRATION — paramétrage complet
// ════════════════════════════════════════════════════════════════════════
//
// Remplace l'ancien module où le bouton « Éditer » se contentait d'afficher
// un message renvoyant l'utilisateur vers l'API brute (point B3 de l'audit).
//
// Cet écran est piloté par les données : il se construit à partir du
// descripteur renvoyé par /api/v5/admin/schema. Rendre une nouvelle table
// administrable ne demande aucune ligne de JavaScript supplémentaire.

const ADM = {
  schema: null,      // descripteur des tables + sources des listes
  onglet: null,      // table courante, ou '_parametres'
  lignes: [],
  parametres: null,
  edition: null      // ligne en cours d'édition, null = création
};

async function admInit() {
  if (!ADM.schema) {
    try {
      const r = await fetch('/api/v5/admin/schema');
      ADM.schema = await r.json();
    } catch (e) {
      showToast("Administration indisponible", 'error');
      return;
    }
  }
  admRendreOnglets();
  if (!ADM.onglet) ADM.onglet = '_parametres';
  admCharger(ADM.onglet);
}

function admRendreOnglets() {
  const zone = document.getElementById('adm-onglets');
  if (!zone || !ADM.schema) return;

  const onglets = [['_parametres', 'Paramètres généraux']].concat(
    Object.entries(ADM.schema.tables).map(([k, v]) => [k, v.libelle])
  );

  zone.innerHTML = onglets.map(([k, lib]) =>
    `<button class="adm-onglet ${k === ADM.onglet ? 'actif' : ''}" data-t="${escAttr(k)}">${escHtml(lib)}</button>`
  ).join('');

  zone.querySelectorAll('.adm-onglet').forEach(b => {
    b.onclick = () => { ADM.onglet = b.dataset.t; admRendreOnglets(); admCharger(b.dataset.t); };
  });
}

async function admCharger(table) {
  const contenu = document.getElementById('adm-contenu');
  const aide = document.getElementById('adm-aide');
  const btnAjout = document.getElementById('adm-btn-ajouter');
  const filtre = document.getElementById('adm-filtre');
  if (!contenu) return;

  contenu.innerHTML = '<div class="adm-vide">Chargement…</div>';

  if (table === '_parametres') {
    if (btnAjout) btnAjout.style.display = 'none';
    if (filtre) filtre.style.display = 'none';
    if (aide) aide.textContent = "Ces réglages s'appliquent immédiatement. La charte des e-mails est volontairement distincte du thème de l'application.";
    try {
      const r = await fetch('/api/v5/admin/parametres/tout');
      ADM.parametres = await r.json();
      admRendreParametres();
    } catch (e) {
      contenu.innerHTML = '<div class="adm-vide">Paramètres indisponibles</div>';
    }
    return;
  }

  if (btnAjout) btnAjout.style.display = '';
  if (filtre) { filtre.style.display = ''; filtre.value = ''; }
  const cfg = ADM.schema.tables[table];
  if (aide) aide.textContent = cfg.aide || '';

  try {
    const r = await fetch('/api/v5/admin/' + table);
    const data = await r.json();
    ADM.lignes = data.lignes || [];
    admRendreTable();
  } catch (e) {
    contenu.innerHTML = '<div class="adm-vide">Chargement impossible</div>';
  }
}

// ── Tableau ─────────────────────────────────────────────────────────────────
function admRendreTable() {
  const contenu = document.getElementById('adm-contenu');
  const cfg = ADM.schema.tables[ADM.onglet];
  if (!contenu || !cfg) return;

  const q = (document.getElementById('adm-filtre')?.value || '').toLowerCase();
  const lignes = q
    ? ADM.lignes.filter(l => Object.values(l).some(v => String(v ?? '').toLowerCase().includes(q)))
    : ADM.lignes;

  if (!lignes.length) {
    contenu.innerHTML = `<div class="adm-vide">${q ? 'Aucun résultat' : 'Aucune entrée — utiliser « + Ajouter »'}</div>`;
    return;
  }

  const cols = cfg.colonnes;
  contenu.innerHTML = `
    <div class="adm-compte">${lignes.length} entrée${lignes.length > 1 ? 's' : ''}</div>
    <table class="adm-table">
      <thead><tr>${cols.map(c =>
        `<th>${escHtml(cfg.champs[c]?.label || c)}</th>`).join('')}<th></th></tr></thead>
      <tbody>${lignes.map(l => `
        <tr data-id="${escAttr(l[cfg.cle || 'id'])}">
          ${cols.map(c => `<td>${admAffichage(cfg, c, l[c])}</td>`).join('')}
          <td class="adm-actions-cell"><button class="adm-lien">Modifier</button></td>
        </tr>`).join('')}
      </tbody>
    </table>`;

  contenu.querySelectorAll('tbody tr').forEach(tr => {
    tr.onclick = () => admOuvrirEdition(tr.dataset.id);
  });
}

function admAffichage(cfg, colonne, valeur) {
  const def = cfg.champs[colonne] || {};
  if (def.type === 'booleen') {
    return valeur
      ? '<span class="adm-etat actif">actif</span>'
      : '<span class="adm-etat">inactif</span>';
  }
  if (valeur === null || valeur === undefined || valeur === '') {
    return `<span class="adm-neant">${escHtml(def.vide || '—')}</span>`;
  }
  if (def.type === 'select_table') {
    const src = (ADM.schema.sources[def.source] || [])
      .find(o => String(o.valeur) === String(valeur));
    return escHtml(src ? src.libelle : valeur);
  }
  const txt = String(valeur);
  return escHtml(txt.length > 70 ? txt.slice(0, 70) + '…' : txt);
}

// ── Formulaire d'édition ────────────────────────────────────────────────────
function admOuvrirEdition(id) {
  const cfg = ADM.schema.tables[ADM.onglet];
  const cle = cfg.cle || 'id';
  ADM.edition = id === null
    ? null
    : ADM.lignes.find(l => String(l[cle]) === String(id)) || null;

  document.getElementById('adm-fenetre-titre').textContent =
    (ADM.edition ? 'Modifier — ' : 'Ajouter — ') + cfg.libelle;
  document.getElementById('adm-btn-supprimer').style.display =
    ADM.edition ? '' : 'none';

  const colonnes = cfg.colonnes.slice();
  if (cfg.cle && !ADM.edition && !colonnes.includes(cfg.cle)) colonnes.unshift(cfg.cle);

  document.getElementById('adm-formulaire').innerHTML = colonnes.map(c => {
    const def = cfg.champs[c] || { label: c, type: 'texte' };
    const val = ADM.edition ? (ADM.edition[c] ?? '') : admDefaut(def);
    const requis = (cfg.obligatoires || []).includes(c);
    const lecture = cfg.cle === c && ADM.edition ? 'readonly' : '';
    let ctrl = '';

    if (def.type === 'booleen') {
      ctrl = `<label class="adm-bascule">
                <input type="checkbox" data-c="${escAttr(c)}" ${val ? 'checked' : ''}>
                <span></span></label>`;
    } else if (def.type === 'long') {
      ctrl = `<textarea data-c="${escAttr(c)}" rows="3">${escHtml(val)}</textarea>`;
    } else if (def.type === 'nombre') {
      ctrl = `<input type="number" data-c="${escAttr(c)}" value="${escAttr(val)}">`;
    } else if (def.type === 'select') {
      ctrl = `<select data-c="${escAttr(c)}">${(def.options || []).map(o =>
                `<option value="${escAttr(o)}" ${String(o) === String(val) ? 'selected' : ''}>${escHtml(o || (def.vide || '—'))}</option>`
              ).join('')}</select>`;
    } else if (def.type === 'select_table') {
      const src = ADM.schema.sources[def.source] || [];
      ctrl = `<select data-c="${escAttr(c)}">
                ${def.vide ? `<option value="">${escHtml(def.vide)}</option>` : ''}
                ${src.map(o => `<option value="${escAttr(o.valeur)}" ${String(o.valeur) === String(val) ? 'selected' : ''}>${escHtml(o.libelle)}</option>`).join('')}
              </select>`;
    } else {
      ctrl = `<input data-c="${escAttr(c)}" value="${escAttr(val)}" ${lecture}>`;
    }

    return `<div class="adm-champ">
              <label>${escHtml(def.label)}${requis ? ' <em>*</em>' : ''}</label>
              ${ctrl}
            </div>`;
  }).join('');

  document.getElementById('adm-voile').style.display = '';
}

function admDefaut(def) {
  if (def.type === 'booleen') return 1;
  if (def.type === 'nombre') return 0;
  if (def.type === 'select') return (def.options || [])[0] || '';
  return '';
}

function admFermer() {
  document.getElementById('adm-voile').style.display = 'none';
  ADM.edition = null;
}

async function admValider() {
  const cfg = ADM.schema.tables[ADM.onglet];
  const cle = cfg.cle || 'id';
  const charge = {};

  document.querySelectorAll('#adm-formulaire [data-c]').forEach(el => {
    charge[el.dataset.c] = el.type === 'checkbox'
      ? (el.checked ? 1 : 0)
      : el.value;
  });

  const creation = !ADM.edition;
  const url = creation
    ? '/api/v5/admin/' + ADM.onglet
    : `/api/v5/admin/${ADM.onglet}/${encodeURIComponent(ADM.edition[cle])}`;

  try {
    const r = await fetch(url, {
      method: creation ? 'POST' : 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(charge)
    });
    const data = await r.json();
    if (!data.ok) { showToast(data.error || 'Échec', 'error'); return; }
    showToast(creation ? 'Ajouté' : 'Modifié', 'success');
    admFermer();
    admCharger(ADM.onglet);
    // Le paramétrage vient de changer : la saisie rapide doit le refléter.
    if (typeof SR !== 'undefined') SR.ref = null;
  } catch (e) {
    showToast('Erreur réseau', 'error');
  }
}

async function admSupprimer() {
  if (!ADM.edition) return;
  const cfg = ADM.schema.tables[ADM.onglet];
  const cle = cfg.cle || 'id';
  if (!confirm('Supprimer définitivement cette entrée ?\n\nSi elle est utilisée ailleurs, préférer la désactiver.')) return;

  try {
    const r = await fetch(`/api/v5/admin/${ADM.onglet}/${encodeURIComponent(ADM.edition[cle])}`,
                          { method: 'DELETE' });
    const data = await r.json();
    if (!data.ok) { showToast(data.error || 'Échec', 'error'); return; }
    showToast('Supprimé', 'success');
    admFermer();
    admCharger(ADM.onglet);
    if (typeof SR !== 'undefined') SR.ref = null;
  } catch (e) {
    showToast('Erreur réseau', 'error');
  }
}

// ── Paramètres généraux ─────────────────────────────────────────────────────
function admRendreParametres() {
  const contenu = document.getElementById('adm-contenu');
  const d = ADM.parametres;
  if (!contenu || !d) return;

  contenu.innerHTML = Object.entries(d.categories).map(([cat, params]) => `
    <div class="adm-groupe">
      <div class="adm-groupe-titre">${escHtml(d.libelles_categories[cat] || cat)}</div>
      <div class="adm-grille">
        ${params.map(p => admChampParametre(p)).join('')}
      </div>
    </div>`).join('') + `
    <div class="adm-barre">
      <button class="btn btn-primary" id="adm-btn-params">Enregistrer les paramètres</button>
      <span class="adm-note">Les modifications s'appliquent immédiatement.</span>
    </div>`;

  document.getElementById('adm-btn-params').onclick = admEnregistrerParametres;
}

function admChampParametre(p) {
  const val = p.valeur;
  const id = 'prm-' + p.cle.replace(/\./g, '-');
  let ctrl = '';

  if (p.type_valeur === 'booleen') {
    ctrl = `<label class="adm-bascule">
              <input type="checkbox" id="${id}" data-p="${escAttr(p.cle)}" ${val === '1' ? 'checked' : ''}>
              <span></span></label>`;
  } else if (p.type_valeur === 'couleur') {
    ctrl = `<div class="adm-couleur">
              <input type="color" id="${id}" data-p="${escAttr(p.cle)}" value="${escAttr(val)}">
              <code>${escHtml(val)}</code>
            </div>`;
  } else if (p.type_valeur === 'nombre') {
    ctrl = `<input type="number" id="${id}" data-p="${escAttr(p.cle)}" value="${escAttr(val)}">`;
  } else if (p.type_valeur === 'liste' && p.options) {
    let opts = [];
    try { opts = JSON.parse(p.options); } catch (e) { opts = []; }
    ctrl = `<select id="${id}" data-p="${escAttr(p.cle)}">${opts.map(o =>
              `<option ${String(o) === String(val) ? 'selected' : ''}>${escHtml(o)}</option>`).join('')}</select>`;
  } else {
    ctrl = `<input id="${id}" data-p="${escAttr(p.cle)}" value="${escAttr(val)}">`;
  }

  return `<div class="adm-param ${p.type_valeur === 'booleen' ? 'inline' : ''}">
            <label for="${id}">${escHtml(p.libelle)}</label>
            ${ctrl}
            ${p.aide ? `<div class="adm-param-aide">${escHtml(p.aide)}</div>` : ''}
          </div>`;
}

async function admEnregistrerParametres() {
  const charge = {};
  document.querySelectorAll('#adm-contenu [data-p]').forEach(el => {
    charge[el.dataset.p] = el.type === 'checkbox' ? (el.checked ? '1' : '0') : el.value;
  });
  try {
    const r = await fetch('/api/v5/admin/parametres', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(charge)
    });
    const data = await r.json();
    showToast(`${data.modifies.length} paramètre(s) enregistré(s)`, 'success');
    if (typeof SR !== 'undefined') SR.ref = null;
    admCharger('_parametres');
  } catch (e) {
    showToast('Erreur réseau', 'error');
  }
}

// ── Branchements ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('adm-btn-ajouter')?.addEventListener('click', () => admOuvrirEdition(null));
  document.getElementById('adm-btn-valider')?.addEventListener('click', admValider);
  document.getElementById('adm-btn-annuler')?.addEventListener('click', admFermer);
  document.getElementById('adm-btn-supprimer')?.addEventListener('click', admSupprimer);
  document.getElementById('adm-filtre')?.addEventListener('input', admRendreTable);
  document.getElementById('adm-voile')?.addEventListener('click', e => {
    if (e.target.id === 'adm-voile') admFermer();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && document.getElementById('adm-voile')?.style.display === '') admFermer();
  });
});