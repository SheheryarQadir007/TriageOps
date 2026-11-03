/**
 * Lead inspection drawer and status workflow.
 */

import { api, bootstrap, state, syncBodyLock, toast } from './core.js';
import {
  avatarTone,
  categoryStyle,
  engineLabel,
  escapeHtml,
  formatCurrency,
  fullDate,
  initials,
  signalTone,
  statusHint,
  statusStyle,
  timeAgo,
  titleCase,
  urgencyStyle,
} from './format.js';

let overlay = null;
let panel = null;
let backdrop = null;
let content = null;
let footer = null;
let lastFocused = null;
let closeTimer = null;
let onStatusChanged = async () => {};

export function initDetail({ onStatusChanged: handler } = {}) {
  onStatusChanged = handler || (async () => {});
  overlay = document.getElementById('detail-overlay');
  panel = document.getElementById('detail-panel');
  backdrop = document.getElementById('detail-backdrop');
  content = document.getElementById('detail-content');
  footer = document.getElementById('detail-footer');
  if (!overlay || !panel || !backdrop || !content || !footer) return;

  backdrop.addEventListener('click', closeDetail);

  panel.addEventListener('click', (event) => {
    if (event.target.closest('[data-close-detail]')) {
      closeDetail();
      return;
    }
    if (event.target.closest('[data-copy-json]')) {
      void copyLeadJson();
      return;
    }
    const statusButton = event.target.closest('[data-status-action]');
    if (statusButton) {
      void updateStatus(statusButton.dataset.statusAction);
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (overlay.classList.contains('hidden')) return;
    const testModal = document.getElementById('test-modal');
    if (testModal && !testModal.classList.contains('hidden')) return;
    closeDetail();
  });

  document.addEventListener('triageops:refreshed', syncAfterRefresh);
}

export function openDetail(leadOrId, trigger = null) {
  if (!overlay) return;

  const lead =
    typeof leadOrId === 'object' && leadOrId !== null
      ? leadOrId
      : state.leads.find((item) => item.id === Number(leadOrId));

  if (!lead) return;

  window.clearTimeout(closeTimer);
  const wasHidden = overlay.classList.contains('hidden');

  state.selectedId = lead.id;
  state.selectedLead = lead;
  if (wasHidden) lastFocused = trigger || document.activeElement;

  renderDetail(lead);
  renderFooter(lead);

  overlay.classList.remove('hidden');
  syncBodyLock();
  const scroll = document.getElementById('detail-content');
  if (scroll) scroll.scrollTop = 0;

  requestAnimationFrame(() => {
    backdrop.classList.add('opacity-100');
    panel.classList.remove('translate-x-full');
  });

  if (wasHidden) {
    window.setTimeout(() => {
      panel.querySelector('[data-close-detail]')?.focus({ preventScroll: true });
    }, 210);
  }
}

export function closeDetail() {
  if (!overlay || overlay.classList.contains('hidden')) return;

  backdrop.classList.remove('opacity-100');
  panel.classList.add('translate-x-full');

  window.clearTimeout(closeTimer);
  closeTimer = window.setTimeout(() => {
    overlay.classList.add('hidden');
    state.selectedId = null;
    state.selectedLead = null;
    if (content) content.innerHTML = '';
    if (footer) footer.innerHTML = '';
    syncBodyLock();
  }, 250);

  if (lastFocused instanceof HTMLElement && lastFocused.isConnected) {
    lastFocused.focus({ preventScroll: true });
  }
  lastFocused = null;
}

function renderDetail(lead) {
  if (!content) return;

  const urgency = urgencyStyle(lead.urgency);
  const category = categoryStyle(lead.category);
  const tone = avatarTone(lead.id);
  const score = clampScore(lead.triage_score);
  const urgencyScore = clampScore(lead.urgency_score);
  const quality = clampScore(lead.completeness_score);
  const qualityBar = quality >= 60 ? 'bg-emerald-500' : 'bg-amber-500';

  const qualifiedChip = lead.qualified
    ? `<span class="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-600/15">
         <svg class="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6L9 17l-5-5" /></svg>
         Qualified
       </span>`
    : `<span class="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600 ring-1 ring-inset ring-slate-500/15">
         <svg class="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 8v4M12 16h.01" /></svg>
         Needs review
       </span>`;

  const email = lead.email
    ? `<a href="mailto:${escapeHtml(lead.email)}" class="break-all font-medium text-indigo-600 transition hover:text-indigo-700 hover:underline">${escapeHtml(lead.email)}</a>`
    : '<span class="text-slate-400">—</span>';

  const phone = lead.phone
    ? `<a href="tel:${escapeHtml(String(lead.phone).replace(/[^\d+]/g, ''))}" class="font-medium text-slate-700 transition hover:text-indigo-600">${escapeHtml(lead.phone)}</a>`
    : '<span class="text-slate-400">Not provided</span>';

  const reasons = Array.isArray(lead.triage_reasons) && lead.triage_reasons.length
    ? lead.triage_reasons
    : ['No rationale was recorded for this lead.'];
  const reasonsHtml = reasons
    .map(
      (reason) => `
        <li class="flex gap-2.5 text-[12px] leading-relaxed text-slate-600">
          <span class="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-indigo-400"></span>
          <span>${escapeHtml(reason)}</span>
        </li>`,
    )
    .join('');

  const signals = Array.isArray(lead.matched_signals) ? lead.matched_signals : [];
  const signalsHtml = signals.length
    ? signals
        .map(
          (signal) =>
            `<span class="inline-flex items-center rounded-md px-2 py-1 font-mono text-[10px] font-medium ring-1 ring-inset ${signalTone(signal)}">${escapeHtml(signal)}</span>`,
        )
        .join('')
    : '<span class="text-[11px] text-slate-400">No additional signals</span>';

  content.innerHTML = `
    <div class="sticky top-0 z-10 border-b border-slate-100 bg-white/95 px-5 py-4 backdrop-blur sm:px-6">
      <div class="flex items-start justify-between gap-3">
        <div class="flex min-w-0 items-start gap-3">
          <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-xs font-semibold ring-1 ${tone}">${escapeHtml(initials(lead.name))}</span>
          <div class="min-w-0">
            <p class="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">Lead #${lead.id} <span class="text-slate-300">·</span> ${escapeHtml(titleCase(lead.source))}</p>
            <h2 id="detail-title" class="mt-0.5 truncate text-lg font-semibold tracking-tight text-slate-950">${escapeHtml(lead.name)}</h2>
            <p class="mt-0.5 truncate text-[11px] text-slate-500">${escapeHtml(lead.company || 'No company')} <span class="text-slate-300">·</span> received ${timeAgo(lead.created_at)}</p>
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-0.5">
          <button type="button" data-copy-json class="rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus-visible:ring-4 focus-visible:ring-indigo-500/15" title="Copy lead JSON" aria-label="Copy lead JSON">
            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15H4a1 1 0 01-1-1V4a1 1 0 011-1h10a1 1 0 011 1v1" /></svg>
          </button>
          <button type="button" data-close-detail class="rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus-visible:ring-4 focus-visible:ring-indigo-500/15" aria-label="Close lead details">
            <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
      </div>
    </div>

    <div class="space-y-6 px-5 py-5 sm:px-6">
      <div class="flex flex-wrap items-center gap-1.5">
        <span class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ring-inset ${urgency.badge}">
          <span class="h-1.5 w-1.5 rounded-full ${urgency.dot}"></span>${escapeHtml(lead.urgency)} urgency
        </span>
        <span class="inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ring-inset ${category}">${escapeHtml(lead.category)}</span>
        ${qualifiedChip}
      </div>

      <div class="grid grid-cols-3 gap-2.5">
        ${scoreCard('Priority', score, 'bg-indigo-500')}
        ${scoreCard('Urgency', urgencyScore, urgency.bar)}
        ${scoreCard('Brief quality', quality, qualityBar)}
      </div>

      <section aria-labelledby="contact-heading">
        <h3 id="contact-heading" class="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">Contact &amp; deal</h3>
        <div class="mt-2.5 grid grid-cols-1 gap-x-5 gap-y-3.5 rounded-xl border border-slate-200/80 bg-white p-4 sm:grid-cols-2">
          ${fact('Email', email)}
          ${fact('Phone', phone)}
          ${fact('Company', lead.company ? escapeHtml(lead.company) : '<span class="text-slate-400">Not provided</span>')}
          ${fact('Budget', `<span class="font-semibold text-slate-900">${formatCurrency(lead.budget)}</span>`)}
          ${fact('Source', escapeHtml(titleCase(lead.source)))}
          ${fact('Received', `<span title="${escapeHtml(fullDate(lead.created_at))}">${escapeHtml(fullDate(lead.created_at))}</span>`)}
        </div>
      </section>

      <section aria-labelledby="brief-heading">
        <div class="flex items-center justify-between gap-3">
          <h3 id="brief-heading" class="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">Project brief</h3>
          <span class="text-[10px] text-slate-400">${lead.project_description.length.toLocaleString()} chars</span>
        </div>
        <div class="mt-2.5 whitespace-pre-line rounded-xl border border-slate-200/80 bg-slate-50/70 p-4 text-[12.5px] leading-relaxed text-slate-700">${escapeHtml(lead.project_description)}</div>
      </section>

      <section aria-labelledby="triage-heading">
        <div class="flex items-center justify-between gap-3">
          <h3 id="triage-heading" class="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">Triage rationale</h3>
          <span class="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.1em] text-slate-500" title="Classifier used for this lead">
            <span class="h-1 w-1 rounded-full bg-emerald-500"></span>${escapeHtml(engineLabel(lead.triage_engine))}
          </span>
        </div>
        <ul class="mt-3 space-y-2">${reasonsHtml}</ul>
      </section>

      <section aria-labelledby="signals-heading">
        <h3 id="signals-heading" class="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">Matched signals</h3>
        <div class="mt-2.5 flex flex-wrap gap-1.5">${signalsHtml}</div>
      </section>

      <div class="rounded-xl border border-slate-200/80 bg-slate-50/60 px-3.5 py-3">
        <p class="text-[10px] font-semibold uppercase tracking-[0.13em] text-slate-400">Auto-qualification policy</p>
        <p class="mt-1 text-[11px] leading-relaxed text-slate-500">
          Requires a budget of at least <span class="font-semibold text-slate-700">${formatCurrency(bootstrap.budgetThreshold)}</span>
          and a brief quality score of 60/100. Qualification score:
          <span class="font-semibold text-slate-700">${clampScore(lead.qualification_score)}/100</span>.
        </p>
      </div>
    </div>
  `;
}

function scoreCard(label, value, barClass) {
  const width = Math.max(4, value);
  return `
    <div class="rounded-xl border border-slate-200/80 bg-white p-3">
      <p class="text-[9px] font-semibold uppercase tracking-[0.13em] text-slate-400">${label}</p>
      <p class="mt-1.5 text-xl font-semibold tracking-tight text-slate-950 tabular-nums">${value}<span class="ml-0.5 text-[10px] font-medium text-slate-400">/100</span></p>
      <div class="mt-2 h-1 overflow-hidden rounded-full bg-slate-100">
        <div class="h-full rounded-full ${barClass}" style="width:${width}%"></div>
      </div>
    </div>`;
}

function fact(label, valueHtml) {
  return `
    <div class="min-w-0">
      <p class="text-[9px] font-semibold uppercase tracking-[0.13em] text-slate-400">${label}</p>
      <div class="mt-1 text-[12px] text-slate-700">${valueHtml}</div>
    </div>`;
}

function renderFooter(lead) {
  if (!footer) return;
  const buttons = bootstrap.statuses
    .map((status) => {
      const active = lead.status === status;
      const tone = statusStyle(status);
      return `
        <button type="button" data-status-action="${escapeHtml(status)}" aria-pressed="${active}" ${state.statusSaving ? 'disabled' : ''}
          class="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-semibold transition focus:outline-none focus-visible:ring-4 focus-visible:ring-indigo-500/15 ${
            active
              ? 'bg-white text-slate-950 shadow-sm ring-1 ring-slate-200'
              : 'text-slate-500 hover:text-slate-900'
          } ${state.statusSaving ? 'cursor-wait opacity-60' : ''}">
          <span class="h-1.5 w-1.5 rounded-full ${active ? tone.dot : 'bg-slate-300'}"></span>${escapeHtml(status)}
        </button>`;
    })
    .join('');

  footer.innerHTML = `
    <div class="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
      <div>
        <p class="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">Workflow status</p>
        <p class="mt-0.5 text-[11px] text-slate-500">${escapeHtml(statusHint(lead.status))}</p>
      </div>
      <div class="inline-flex w-fit items-center rounded-lg bg-slate-100 p-1" role="group" aria-label="Update lead status">
        ${buttons}
      </div>
    </div>
  `;
}

async function updateStatus(status) {
  const lead = state.selectedLead;
  if (!lead || !status || state.statusSaving || lead.status === status) return;

  const previous = lead.status;
  state.statusSaving = true;
  renderFooter(lead);

  try {
    const updated = await api(`/api/leads/${lead.id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });

    state.selectedLead = updated;
    state.selectedId = updated.id;
    state.leads = state.leads.map((item) => (item.id === updated.id ? updated : item));
    renderFooter(updated);
    toast(`Lead #${updated.id} moved to ${updated.status}`, {
      tone: 'success',
      detail: statusHint(updated.status),
    });
    await onStatusChanged();
  } catch (error) {
    toast(error.message, { tone: 'error', detail: `Status remains ${previous}.` });
  } finally {
    state.statusSaving = false;
    if (state.selectedLead) renderFooter(state.selectedLead);
  }
}

function syncAfterRefresh() {
  if (!state.selectedId) return;
  const found = state.leads.find((lead) => lead.id === state.selectedId);
  if (!found) return;
  state.selectedLead = found;
  renderFooter(found);
}

async function copyLeadJson() {
  const lead = state.selectedLead;
  if (!lead) return;
  const text = JSON.stringify(lead, null, 2);

  try {
    await navigator.clipboard.writeText(text);
    toast('Lead JSON copied to clipboard', { tone: 'success' });
  } catch {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    const copied = document.execCommand('copy');
    area.remove();
    toast(copied ? 'Lead JSON copied to clipboard' : 'Could not copy to clipboard', {
      tone: copied ? 'success' : 'error',
    });
  }
}

function clampScore(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return Math.max(0, Math.min(100, Math.round(number)));
}
