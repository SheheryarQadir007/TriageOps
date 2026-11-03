/**
 * Shared application state, API client, and UI primitives.
 */

const DEFAULTS = {
  appName: 'TriageOps',
  provider: 'rules',
  budgetThreshold: 5000,
  urgencies: ['High', 'Medium', 'Low'],
  categories: ['Emergency Repair', 'New Implementation', 'Maintenance', 'General Inquiry'],
  statuses: ['New', 'Contacted', 'Closed'],
  demoToolsEnabled: true,
  seedDemoData: false,
};

export const bootstrap = { ...DEFAULTS, ...(window.__TRIAGEOPS__ || {}) };

export const state = {
  leads: [],
  total: 0,
  stats: null,
  hasLoaded: false,
  lastUpdated: null,
  requestSeq: 0,
  selectedId: null,
  selectedLead: null,
  statusSaving: false,
  autoRefresh: false,
  autoTimer: null,
  filters: {
    status: '',
    urgency: '',
    category: '',
    qualified: false,
    q: '',
    sort: 'urgency',
  },
};

export function defaultFilters() {
  return { status: '', urgency: '', category: '', qualified: false, q: '', sort: 'urgency' };
}

export function hasActiveFilters(filters = state.filters) {
  return Boolean(
    filters.status || filters.urgency || filters.category || filters.qualified || filters.q,
  );
}

export function activeFilterCount(filters = state.filters) {
  return [filters.status, filters.urgency, filters.category, filters.q].filter(Boolean).length +
    (filters.qualified ? 1 : 0);
}

export function buildQuery(filters = state.filters, { forExport = false } = {}) {
  const params = new URLSearchParams();
  if (filters.status) params.set('status', filters.status);
  if (filters.urgency) params.set('urgency', filters.urgency);
  if (filters.category) params.set('category', filters.category);
  if (filters.qualified) params.set('qualified', 'true');
  if (filters.q) params.set('q', filters.q);
  if (!forExport) {
    params.set('sort', filters.sort);
    params.set('limit', '200');
  }
  return params;
}

/**
 * Fetch JSON from the local API and normalise FastAPI error payloads.
 */
export async function api(path, options = {}) {
  const { body, headers, ...rest } = options;
  const requestHeaders = {
    Accept: 'application/json',
    ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    ...(headers || {}),
  };

  let response;
  try {
    response = await fetch(path, {
      credentials: 'same-origin',
      ...rest,
      headers: requestHeaders,
      body,
    });
  } catch (cause) {
    const error = new Error('Unable to reach the server. Check your connection and retry.');
    error.cause = cause;
    throw error;
  }

  if (!response.ok) {
    let detail = null;
    try {
      detail = await response.json();
    } catch {
      /* non-JSON error body */
    }

    let message = `Request failed (${response.status})`;
    if (typeof detail?.detail === 'string') {
      message = detail.detail;
    } else if (Array.isArray(detail?.detail)) {
      message = detail.detail
        .map((entry) => {
          const field = Array.isArray(entry.loc)
            ? entry.loc.filter((part) => part !== 'body').join('.')
            : '';
          return field ? `${field}: ${entry.msg}` : entry.msg;
        })
        .join(' · ');
    }

    const error = new Error(message);
    error.status = response.status;
    throw error;
  }

  if (response.status === 204) return null;
  const contentType = response.headers.get('content-type') || '';
  return contentType.includes('application/json') ? response.json() : response.text();
}

export function showLoading(visible) {
  const bar = document.getElementById('loading-bar');
  const button = document.getElementById('refresh-btn');
  const icon = document.getElementById('refresh-icon');
  if (bar) bar.classList.toggle('hidden', !visible);
  if (button) {
    button.disabled = visible;
    button.classList.toggle('opacity-60', visible);
    button.classList.toggle('cursor-wait', visible);
  }
  if (icon) icon.classList.toggle('animate-spin', visible);
}

export function setLastUpdated(date = new Date()) {
  state.lastUpdated = date;
  const element = document.getElementById('last-updated');
  if (!element) return;
  const time = date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  element.textContent = `Updated ${time}`;
}

export function syncBodyLock() {
  const detailOpen = !document.getElementById('detail-overlay')?.classList.contains('hidden');
  const testOpen = !document.getElementById('test-modal')?.classList.contains('hidden');
  document.body.classList.toggle('overflow-hidden', Boolean(detailOpen || testOpen));
}

const TOAST_ICONS = {
  success:
    '<path d="M20 6L9 17l-5-5" />',
  error:
    '<circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16h.01" />',
  info:
    '<circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" />',
};

const TOAST_TONES = {
  success: 'border-emerald-200 bg-white text-emerald-600',
  error: 'border-rose-200 bg-white text-rose-600',
  info: 'border-indigo-200 bg-white text-indigo-600',
};

/**
 * Lightweight toast notification. Text is inserted with textContent to keep
 * arbitrary lead content inert.
 */
export function toast(message, { tone = 'success', detail = '', duration = 4200 } = {}) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const element = document.createElement('div');
  element.className =
    'pointer-events-auto flex w-full items-start gap-3 rounded-xl border border-slate-200 bg-white p-3.5 shadow-xl ring-1 ring-slate-900/5';

  const iconWrap = document.createElement('span');
  iconWrap.className = `mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${TOAST_TONES[tone] || TOAST_TONES.info}`;
  iconWrap.innerHTML = `<svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${TOAST_ICONS[tone] || TOAST_ICONS.info}</svg>`;

  const body = document.createElement('div');
  body.className = 'min-w-0 flex-1';
  const title = document.createElement('p');
  title.className = 'text-xs font-semibold leading-5 text-slate-900';
  title.textContent = message;
  body.appendChild(title);
  if (detail) {
    const sub = document.createElement('p');
    sub.className = 'mt-0.5 text-[11px] leading-4 text-slate-500';
    sub.textContent = detail;
    body.appendChild(sub);
  }

  const close = document.createElement('button');
  close.type = 'button';
  close.className =
    'mt-0.5 rounded-md p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/30';
  close.setAttribute('aria-label', 'Dismiss notification');
  close.innerHTML =
    '<svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>';

  const dismiss = () => {
    element.classList.add('toast-leaving');
    window.setTimeout(() => element.remove(), 190);
  };
  close.addEventListener('click', dismiss);

  element.append(iconWrap, body, close);
  container.appendChild(element);
  window.setTimeout(dismiss, duration);
}

export function debounce(fn, wait = 280) {
  let timer;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), wait);
  };
}
