/**
 * "Submit test lead" simulator — exercises the public intake endpoint live.
 */

import { api, syncBodyLock, toast } from './core.js';
import { closeDetail } from './detail.js';

const SAMPLES = {
  urgent: {
    name: 'Maya Chen',
    email: 'maya.chen@acmesystems.example',
    phone: '+1 (415) 555-0102',
    company: 'Acme Systems',
    budget: '18000',
    project_description:
      "URGENT: our customer portal is down after last night's deploy and the support team cannot access accounts. We are losing orders every hour. The app returns a 502 error; it runs on React and FastAPI behind AWS. Need someone to jump in immediately, diagnose the outage, and restore service today. I can provide logs and cloud access right away.",
  },
  implementation: {
    name: 'Jordan Lee',
    email: 'jordan@nimbushealth.example',
    phone: '+1 (617) 555-0194',
    company: 'Nimbus Health',
    budget: '$12,000',
    project_description:
      'We need a new patient scheduling portal built for our three clinics. Scope includes calendar sync, SMS reminders, Stripe copay collection, and role-based access for 40 staff. We currently use spreadsheets and want to migrate about 2,000 existing appointments. Target launch is next quarter and the budget is approved.',
  },
  inquiry: {
    name: 'Alex Rivera',
    email: 'alex@riveracreative.example',
    phone: '',
    company: 'Rivera Creative',
    budget: '',
    project_description:
      "Hi — we're exploring options for a website redesign later this year and would like to learn more about pricing and availability. We are still gathering requirements, so just looking for a rough estimate and a conversation.",
  },
};

let onCreated = async () => {};
let form = null;
let modal = null;
let backdrop = null;
let submitButton = null;
let submitButtonText = null;
let errorBox = null;
let lastFocused = null;

export function initSimulator({ onCreated: handler } = {}) {
  onCreated = handler || (async () => {});
  modal = document.getElementById('test-modal');
  backdrop = document.getElementById('test-backdrop');
  form = document.getElementById('test-lead-form');
  submitButton = document.getElementById('submit-lead-btn');
  errorBox = document.getElementById('form-error');
  if (!modal || !form || !submitButton) return;

  submitButtonText = submitButton.querySelector('span');

  document.getElementById('open-test-lead')?.addEventListener('click', openTestModal);
  backdrop?.addEventListener('click', closeTestModal);

  modal.querySelectorAll('[data-close-test]').forEach((button) => {
    button.addEventListener('click', closeTestModal);
  });

  document.getElementById('reset-test-form')?.addEventListener('click', () => {
    form.reset();
    updateDescriptionCount();
    clearFormError();
    form.querySelector('[name="name"]')?.focus();
  });

  document.getElementById('sample-buttons')?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-sample]');
    if (!button) return;
    fillSample(button.dataset.sample);
  });

  const description = form.querySelector('[name="project_description"]');
  description?.addEventListener('input', updateDescriptionCount);

  form.addEventListener('submit', handleSubmit);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !modal.classList.contains('hidden')) {
      closeTestModal();
    }
  });
}

export function openTestModal() {
  if (!modal) return;
  const detailOverlay = document.getElementById('detail-overlay');
  if (detailOverlay && !detailOverlay.classList.contains('hidden')) {
    closeDetail();
  }

  lastFocused = document.activeElement;
  clearFormError();
  modal.classList.remove('hidden');
  modal.classList.add('flex');
  syncBodyLock();

  window.setTimeout(() => {
    form.querySelector('[name="name"]')?.focus();
  }, 80);
}

export function closeTestModal() {
  if (!modal || modal.classList.contains('hidden')) return;
  modal.classList.add('hidden');
  modal.classList.remove('flex');
  clearFormError();
  syncBodyLock();

  if (lastFocused instanceof HTMLElement && lastFocused.isConnected) {
    lastFocused.focus({ preventScroll: true });
  }
  lastFocused = null;
}

async function handleSubmit(event) {
  event.preventDefault();
  clearFormError();

  if (!form.reportValidity()) return;

  const data = new FormData(form);
  const payload = {
    name: String(data.get('name') || '').trim(),
    email: String(data.get('email') || '').trim(),
    phone: String(data.get('phone') || '').trim() || null,
    company: String(data.get('company') || '').trim() || null,
    budget: String(data.get('budget') || '').trim() || null,
    project_description: String(data.get('project_description') || '').trim(),
    source: String(data.get('source') || 'dashboard').trim() || 'dashboard',
  };

  setSubmitting(true);
  try {
    const lead = await api('/api/leads', {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    closeTestModal();
    form.reset();
    updateDescriptionCount();

    toast(`Lead #${lead.id} triaged: ${lead.urgency} · ${lead.category}`, {
      tone: 'success',
      detail: lead.qualified ? 'Auto-qualified and added to the pipeline.' : 'Needs review — added to the pipeline.',
    });

    await onCreated(lead);
  } catch (error) {
    showFormError(error.message);
    toast(error.message, { tone: 'error', detail: 'The lead was not saved.' });
  } finally {
    setSubmitting(false);
  }
}

function setSubmitting(submitting) {
  if (!submitButton) return;
  submitButton.disabled = submitting;
  submitButton.classList.toggle('opacity-60', submitting);
  submitButton.classList.toggle('cursor-wait', submitting);
  if (submitButtonText) {
    submitButtonText.textContent = submitting ? 'Triaging…' : 'Run triage';
  }
}

function fillSample(key) {
  const sample = SAMPLES[key];
  if (!sample) return;
  Object.entries(sample).forEach(([field, value]) => {
    const input = form.querySelector(`[name="${field}"]`);
    if (input) input.value = value;
  });
  updateDescriptionCount();
  clearFormError();
  form.querySelector('[name="project_description"]')?.focus();
}

function updateDescriptionCount() {
  const description = form.querySelector('[name="project_description"]');
  const counter = document.getElementById('desc-count');
  if (description && counter) {
    counter.textContent = description.value.length.toLocaleString();
  }
}

function clearFormError() {
  if (!errorBox) return;
  errorBox.classList.add('hidden');
  errorBox.textContent = '';
}

function showFormError(message) {
  if (!errorBox) return;
  errorBox.textContent = message;
  errorBox.classList.remove('hidden');
  errorBox.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}
