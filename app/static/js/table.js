/**
 * Pipeline table, summary cards, and filter orchestration.
 */

import {
  activeFilterCount,
  api,
  bootstrap,
  buildQuery,
  debounce,
  defaultFilters,
  hasActiveFilters,
  setLastUpdated,
  showLoading,
  state,
  toast,
} from './core.js';
import {
  avatarTone,
  categoryStyle,
  escapeHtml,
  formatCurrency,
  formatNumber,
  fullDate,
  initials,
  statusStyle,
  timeAgo,
  urgencyStyle,
} from './format.js';

const SORT_LABELS = {
  urgency: 'urgency, then recency',
  score: 'priority score',
  newest: 'newest first',
  oldest: 'oldest first',
};

let onOpenLead = () => {};
let searchTimer = null;

export function initTable({ onOpenLead: handler } = {}) {
  onOpenLead = handler || (() => {});
  bindStatusTabs();
  bindFilterControls();
  bindSearch();
  bindTable();
  bindEmptyState();

  const sort = document.getElementById('sort-select');
  if (sort) sort.value = state.filters.sort;
  updateSortLabel();
  updateFilterSummary();
  updateExportLink();
  return refreshAll;
}

export async function refreshAll({ silent = false } = {}) {
  const sequence = ++state.requestSeq;
  showLoading(true);

  try {
    const query = buildQuery().toString();
    const [listing, stats] = await Promise.all([
      api(`/api/leads${query ? `?${query}` : ''}`),
      api('/api/stats'),
    ]);

    if (sequence !== state.requestSeq) return;

    state.leads = listing.items;
    state.total = listing.total;
    state.stats = stats;
    state.hasLoaded = true;

    renderStats(stats);
    renderTable();
    updateFilterSummary();
    updateExportLink();
    setLastUpdated();
    document.dispatchEvent(new CustomEvent('triageops:refreshed'));
  } catch (error) {
    if (sequence !== state.requestSeq) return;
    if (!state.hasLoaded || !state.leads.length) {
      renderLoadError(error.message);
    } else if (!silent) {
      toast(error.message, {
        tone: 'error',
        detail: 'Showing the last successful refresh.',
      });
    }
  } finally {
    if (sequence === state.requestSeq) showLoading(false);
  }
}

// ── Summary cards ───────────────────────────────────────────────────────────

function renderStats(stats) {
  const total = Number(stats.total) || 0;
  const high = Number(stats.high_urgency) || 0;
  const qualified = Number(stats.qualified) || 0;
  const average = Number(stats.avg_triage_score) || 0;
  const pipeline = Number(stats.qualified_pipeline) || 0;

  setText('stat-total', formatNumber(total));
  setText(
    'stat-total-sub',
    total ? `Avg priority ${average.toFixed(1)} / 100` : 'No leads in the pipeline yet',
  );

  setText('stat-high', formatNumber(high));
  setText(
    'stat-high-sub',
    total ? `${Math.round((high / total) * 100)}% of all leads` : 'Nothing urgent right now',
  );

  setText('stat-qualified', formatNumber(qualified));
  setText(
    'stat-qualified-sub',
    total ? `${Math.round((qualified / total) * 100)}% of pipeline meets policy` : 'Budget + brief policy',
  );

  setText('stat-pipeline', formatCurrency(pipeline, { compact: true }));
  setText(
    'stat-pipeline-sub',
    `${formatNumber(qualified)} qualified lead${qualified === 1 ? '' : 's'} at ≥ ${formatCurrency(bootstrap.budgetThreshold)}`,
  );

  const counts = {
    all: total,
    New: stats.new_leads,
    Contacted: stats.contacted,
    Closed: stats.closed,
  };
  document.querySelectorAll('[data-count]').forEach((element) => {
    const key = element.dataset.count;
    element.textContent = formatNumber(counts[key] ?? 0);
  });
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

// ── Filters ─────────────────────────────────────────────────────────────────

function bindStatusTabs() {
  document.querySelectorAll('[data-status-tab]').forEach((tab) => {
    tab.addEventListener('click', () => {
      const status = tab.dataset.statusTab || '';
      if (state.filters.status === status) return;
      state.filters.status = status;
      styleStatusTabs();
      updateFilterSummary();
      refreshAll();
    });
  });
  styleStatusTabs();
}

function styleStatusTabs() {
  document.querySelectorAll('[data-status-tab]').forEach((tab) => {
    const isActive = (tab.dataset.statusTab || '') === state.filters.status;
    tab.classList.toggle('is-active', isActive);
    tab.setAttribute('aria-selected', String(isActive));
    tab.tabIndex = isActive ? 0 : -1;
  });
}

function bindFilterControls() {
  const urgency = document.getElementById('filter-urgency');
  const category = document.getElementById('filter-category');
  const qualified = document.getElementById('qualified-toggle');
  const clear = document.getElementById('clear-filters');
  const sort = document.getElementById('sort-select');

  urgency?.addEventListener('change', () => {
    state.filters.urgency = urgency.value;
    updateFilterSummary();
    refreshAll();
  });

  category?.addEventListener('change', () => {
    state.filters.category = category.value;
    updateFilterSummary();
    refreshAll();
  });

  qualified?.addEventListener('click', () => {
    state.filters.qualified = !state.filters.qualified;
    styleQualifiedToggle();
    updateFilterSummary();
    refreshAll();
  });

  clear?.addEventListener('click', () => resetFilters());

  sort?.addEventListener('change', () => {
    state.filters.sort = sort.value || 'urgency';
    updateSortLabel();
    refreshAll();
  });

  styleQualifiedToggle();
}

function styleQualifiedToggle() {
  const button = document.getElementById('qualified-toggle');
  const dot = document.getElementById('qualified-dot');
  if (!button || !dot) return;
  const enabled = state.filters.qualified;

  button.setAttribute('aria-pressed', String(enabled));
  button.classList.toggle('border-emerald-200', enabled);
  button.classList.toggle('bg-emerald-50', enabled);
  button.classList.toggle('text-emerald-700', enabled);
  button.classList.toggle('border-slate-200', !enabled);
  button.classList.toggle('bg-white', !enabled);
  button.classList.toggle('text-slate-600', !enabled);
  dot.className = `h-1.5 w-1.5 rounded-full transition ${
    enabled ? 'bg-emerald-500' : 'bg-slate-300'
  }`;
}

function bindSearch() {
  const input = document.getElementById('search-input');
  if (!input) return;

  const commit = () => {
    const value = input.value.trim();
    if (state.filters.q === value) return;
    state.filters.q = value;
    updateFilterSummary();
    refreshAll();
  };

  const debounced = debounce(commit, 300);
  input.addEventListener('input', debounced);
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && input.value) {
      event.stopPropagation();
      input.value = '';
      window.clearTimeout(searchTimer);
      commit();
    }
    if (event.key === 'Enter') {
      window.clearTimeout(searchTimer);
      commit();
    }
  });
}

export function resetFilters({ refresh = true } = {}) {
  Object.assign(state.filters, defaultFilters());

  const search = document.getElementById('search-input');
  const urgency = document.getElementById('filter-urgency');
  const category = document.getElementById('filter-category');
  const sort = document.getElementById('sort-select');
  if (search) search.value = '';
  if (urgency) urgency.value = '';
  if (category) category.value = '';
  if (sort) sort.value = state.filters.sort;

  styleStatusTabs();
  styleQualifiedToggle();
  updateSortLabel();
  updateFilterSummary();
  updateExportLink();
  if (refresh) refreshAll();
}

function updateFilterSummary() {
  const count = activeFilterCount();
  const clear = document.getElementById('clear-filters');
  const summary = document.getElementById('filter-summary');
  const countElement = document.getElementById('filter-count');

  if (clear) {
    clear.classList.toggle('hidden', count === 0);
    clear.classList.toggle('inline-flex', count > 0);
  }
  if (summary) {
    summary.classList.toggle('hidden', count === 0);
    summary.classList.toggle('inline-flex', count > 0);
  }
  if (countElement) countElement.textContent = String(count);
}

function updateSortLabel() {
  setText('sort-label', SORT_LABELS[state.filters.sort] || SORT_LABELS.urgency);
}

function updateExportLink() {
  const link = document.getElementById('export-link');
  if (!link) return;
  const query = buildQuery(state.filters, { forExport: true }).toString();
  link.href = `/api/leads/export.csv${query ? `?${query}` : ''}`;
}

// ── Table ───────────────────────────────────────────────────────────────────

function bindTable() {
  const tbody = document.getElementById('lead-tbody');
  if (!tbody) return;

  tbody.addEventListener('click', (event) => {
    const row = event.target.closest('tr[data-lead-id]');
    if (!row) return;
    openRow(row);
  });

  tbody.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const row = event.target.closest('tr[data-lead-id]');
    if (!row) return;
    event.preventDefault();
    openRow(row);
  });
}

function openRow(row) {
  const id = Number(row.dataset.leadId);
  const lead = state.leads.find((item) => item.id === id);
  if (lead) onOpenLead(lead, row);
}

function renderTable() {
  const wrap = document.getElementById('table-wrap');
  const empty = document.getElementById('empty-state');
  const tbody = document.getElementById('lead-tbody');
  if (!wrap || !empty || !tbody) return;

  updateSortLabel();

  if (!state.leads.length) {
    tbody.innerHTML = '';
    wrap.classList.add('hidden');
    empty.classList.remove('hidden');
    renderEmptyState();
    setText('table-summary', '0 leads');
    return;
  }

  wrap.classList.remove('hidden');
  empty.classList.add('hidden');
  tbody.innerHTML = state.leads.map(renderRow).join('');

  const filtered = hasActiveFilters();
  const suffix = state.total === 1 ? '' : 's';
  setText(
    'table-summary',
    `Showing ${formatNumber(state.leads.length)} of ${formatNumber(state.total)} lead${suffix}${
      filtered ? ' · filtered view' : ''
    }`,
  );
}

function renderRow(lead) {
  const urgency = urgencyStyle(lead.urgency);
  const category = categoryStyle(lead.category);
  const status = statusStyle(lead.status);
  const tone = avatarTone(lead.id);
  const score = Math.max(0, Math.min(100, Number(lead.triage_score) || 0));
  const name = escapeHtml(lead.name);
  const companyLine = [lead.company, lead.email]
    .filter(Boolean)
    .map((value) => escapeHtml(value))
    .join('<span class="px-1 text-slate-300">·</span>');

  const qualifiedBadge = lead.qualified
    ? `<span class="inline-flex shrink-0 text-emerald-600" title="Qualified lead" aria-label="Qualified">
         <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6L9 17l-5-5" /></svg>
       </span>`
    : '';

  return `
    <tr data-lead-id="${lead.id}" tabindex="0" role="button" aria-label="Open lead from ${escapeHtml(lead.name)}" class="group cursor-pointer bg-white hover:bg-slate-50/80 focus:outline-none focus-visible:bg-indigo-50/50">
      <td class="px-5 py-3.5">
        <div class="flex items-center gap-3">
          <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ring-1 ${tone}">${escapeHtml(initials(lead.name))}</span>
          <div class="min-w-0">
            <div class="flex items-center gap-1.5">
              <p class="truncate text-[13px] font-semibold text-slate-900">${name}</p>
              ${qualifiedBadge}
            </div>
            <p class="mt-0.5 max-w-[260px] truncate text-[11px] text-slate-500">${companyLine || '—'}</p>
          </div>
        </div>
      </td>
      <td class="px-3 py-3.5">
        <span class="inline-flex items-center rounded-md px-2 py-1 text-[10px] font-semibold ring-1 ring-inset ${category}">${escapeHtml(lead.category)}</span>
      </td>
      <td class="px-3 py-3.5">
        <span class="inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[11px] font-semibold ring-1 ring-inset ${urgency.badge}">
          <span class="h-1.5 w-1.5 rounded-full ${urgency.dot}"></span>${escapeHtml(lead.urgency)}
        </span>
      </td>
      <td class="px-3 py-3.5">
        <div class="flex items-center gap-2" title="Priority score ${score} / 100">
          <span class="w-6 text-right text-xs font-semibold tabular-nums text-slate-700">${score}</span>
          <span class="h-1.5 w-12 overflow-hidden rounded-full bg-slate-100">
            <span class="block h-full rounded-full ${urgency.bar}" style="width:${Math.max(4, score)}%"></span>
          </span>
        </div>
      </td>
      <td class="px-3 py-3.5">
        <span class="font-mono text-[11px] tabular-nums text-slate-600">${formatCurrency(lead.budget)}</span>
      </td>
      <td class="px-3 py-3.5">
        <span class="inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[11px] font-medium ring-1 ring-inset ${status.badge}">
          <span class="h-1.5 w-1.5 rounded-full ${status.dot}"></span>${escapeHtml(lead.status)}
        </span>
      </td>
      <td class="px-3 py-3.5">
        <span class="text-[11px] font-medium text-slate-500" title="${escapeHtml(fullDate(lead.created_at))}">${timeAgo(lead.created_at)}</span>
      </td>
      <td class="px-3 py-3.5">
        <svg class="h-4 w-4 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
      </td>
    </tr>
  `;
}

function renderEmptyState() {
  const empty = document.getElementById('empty-state');
  if (!empty) return;

  if (hasActiveFilters()) {
    empty.innerHTML = `
      <div class="flex flex-col items-center justify-center px-6 py-16 text-center">
        <span class="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-50 text-slate-400 ring-1 ring-slate-200">
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
        </span>
        <h3 class="mt-4 text-sm font-semibold text-slate-900">No leads match these filters</h3>
        <p class="mt-1 max-w-sm text-xs leading-relaxed text-slate-500">Try widening the urgency or category filter, or clear the current view to see the full queue.</p>
        <div class="mt-5 flex flex-wrap items-center justify-center gap-2">
          <button type="button" data-action="clear" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-slate-950 px-3.5 text-xs font-semibold text-white shadow-sm transition hover:bg-slate-800 focus:outline-none focus-visible:ring-4 focus-visible:ring-slate-900/20">
            Clear filters
          </button>
          <button type="button" data-action="submit" class="inline-flex h-9 items-center rounded-lg border border-slate-200 bg-white px-3.5 text-xs font-medium text-slate-600 shadow-sm transition hover:border-slate-300 hover:text-slate-900 focus:outline-none focus-visible:ring-4 focus-visible:ring-indigo-500/15">
            Submit test lead
          </button>
        </div>
      </div>
    `;
    return;
  }

  const seedButton = bootstrap.demoToolsEnabled
    ? `<button type="button" data-action="seed" class="inline-flex h-9 items-center rounded-lg border border-slate-200 bg-white px-3.5 text-xs font-medium text-slate-600 shadow-sm transition hover:border-slate-300 hover:text-slate-900 focus:outline-none focus-visible:ring-4 focus-visible:ring-indigo-500/15">Load demo leads</button>`
    : '';

  empty.innerHTML = `
    <div class="flex flex-col items-center justify-center px-6 py-16 text-center">
      <span class="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-500 ring-1 ring-indigo-100">
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 3v18M3 12h18" />
        </svg>
      </span>
      <h3 class="mt-4 text-sm font-semibold text-slate-900">Your pipeline is empty</h3>
      <p class="mt-1 max-w-sm text-xs leading-relaxed text-slate-500">Submit a lead through the simulator, or send one to <code class="rounded bg-slate-100 px-1 py-0.5 font-mono text-[10px] text-slate-600">POST /api/leads</code> to watch triage run.</p>
      <div class="mt-5 flex flex-wrap items-center justify-center gap-2">
        <button type="button" data-action="submit" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-slate-950 px-3.5 text-xs font-semibold text-white shadow-sm transition hover:bg-slate-800 focus:outline-none focus-visible:ring-4 focus-visible:ring-slate-900/20">
          Submit test lead
        </button>
        ${seedButton}
      </div>
    </div>
  `;
}

function renderLoadError(message) {
  const wrap = document.getElementById('table-wrap');
  const empty = document.getElementById('empty-state');
  if (!wrap || !empty) return;
  wrap.classList.add('hidden');
  empty.classList.remove('hidden');
  empty.innerHTML = `
    <div class="flex flex-col items-center justify-center px-6 py-16 text-center">
      <span class="flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-50 text-rose-500 ring-1 ring-rose-100">
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16h.01" /></svg>
      </span>
      <h3 class="mt-4 text-sm font-semibold text-slate-900">Could not load the pipeline</h3>
      <p class="mt-1 max-w-md text-xs leading-relaxed text-slate-500">${escapeHtml(message)}</p>
      <button type="button" data-action="retry" class="mt-5 inline-flex h-9 items-center rounded-lg bg-slate-950 px-3.5 text-xs font-semibold text-white shadow-sm transition hover:bg-slate-800 focus:outline-none focus-visible:ring-4 focus-visible:ring-slate-900/20">
        Retry
      </button>
    </div>
  `;
  setText('table-summary', 'Could not load leads');
}

function bindEmptyState() {
  const empty = document.getElementById('empty-state');
  if (!empty) return;

  empty.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    const action = button.dataset.action;

    if (action === 'clear') {
      resetFilters();
      return;
    }
    if (action === 'submit') {
      document.getElementById('open-test-lead')?.click();
      return;
    }
    if (action === 'retry') {
      refreshAll();
      return;
    }
    if (action === 'seed') {
      const original = button.innerHTML;
      button.disabled = true;
      button.classList.add('opacity-60', 'cursor-wait');
      button.textContent = 'Loading…';
      try {
        const result = await api('/api/demo/seed', { method: 'POST' });
        toast(result.message || 'Demo leads loaded.', { tone: 'success' });
        await refreshAll({ silent: true });
      } catch (error) {
        toast(error.message, { tone: 'error' });
        button.disabled = false;
        button.classList.remove('opacity-60', 'cursor-wait');
        button.innerHTML = original;
      }
    }
  });
}
