/**
 * Dashboard bootstrap: wires the table, detail drawer, simulator, and shell.
 */

import { bootstrap, state, toast } from './core.js';
import { initDetail, openDetail } from './detail.js';
import { providerLabel } from './format.js';
import { initSimulator } from './simulator.js';
import { initTable } from './table.js';

const AUTO_REFRESH_KEY = 'triageops.autoRefresh';
const AUTO_REFRESH_MS = 30_000;

async function init() {
  applyEngineLabels();

  const refresh = initTable({
    onOpenLead: (lead, trigger) => openDetail(lead, trigger),
  });

  initDetail({
    onStatusChanged: () => refresh({ silent: true }),
  });

  initSimulator({
    onCreated: async (lead) => {
      await refresh({ silent: true });
      openDetail(lead);
    },
  });

  bindHeader(refresh);
  bindAutoRefresh(refresh);
  bindKeyboard(refresh);
  bindStatusTabKeyboard();
  restoreAutoRefresh(refresh);

  await refresh();
}

function applyEngineLabels() {
  const label = document.getElementById('engine-label');
  const footer = document.getElementById('footer-engine');
  const badge = document.getElementById('engine-badge');
  const provider = providerLabel(bootstrap.provider);

  if (label) label.textContent = provider;
  if (footer) footer.textContent = bootstrap.provider;
  if (badge) {
    badge.title = `Triage classifier: ${provider}. Set TRIAGE_PROVIDER to change it.`;
  }
  document.title = `${bootstrap.appName} · Lead operations`;
}

function bindHeader(refresh) {
  document.getElementById('refresh-btn')?.addEventListener('click', () => {
    void refresh();
  });
}

function bindAutoRefresh(refresh) {
  const button = document.getElementById('auto-refresh-btn');
  if (!button) return;

  button.addEventListener('click', () => {
    setAutoRefresh(refresh, !state.autoRefresh, { persist: true, announce: true });
  });
}

function setAutoRefresh(refresh, enabled, { persist = false, announce = false } = {}) {
  state.autoRefresh = enabled;
  if (state.autoTimer) {
    window.clearInterval(state.autoTimer);
    state.autoTimer = null;
  }

  const button = document.getElementById('auto-refresh-btn');
  const dot = document.getElementById('auto-dot');
  if (button) {
    button.setAttribute('aria-pressed', String(enabled));
    button.classList.toggle('border-emerald-200', enabled);
    button.classList.toggle('bg-emerald-50', enabled);
    button.classList.toggle('text-emerald-700', enabled);
    button.classList.toggle('border-slate-200', !enabled);
    button.classList.toggle('bg-white', !enabled);
    button.classList.toggle('text-slate-600', !enabled);
  }
  if (dot) {
    dot.className = `h-1.5 w-1.5 rounded-full transition ${
      enabled ? 'bg-emerald-500' : 'bg-slate-300'
    }`;
  }

  if (enabled) {
    state.autoTimer = window.setInterval(() => {
      if (document.visibilityState === 'visible' && !state.statusSaving) {
        void refresh({ silent: true });
      }
    }, AUTO_REFRESH_MS);
  }

  if (persist) {
    try {
      window.localStorage.setItem(AUTO_REFRESH_KEY, enabled ? '1' : '0');
    } catch {
      /* storage can be unavailable in private mode */
    }
  }

  if (announce) {
    toast(enabled ? 'Auto-refresh enabled' : 'Auto-refresh paused', {
      tone: enabled ? 'success' : 'info',
      detail: enabled
        ? 'The pipeline refreshes every 30 seconds while this tab is visible.'
        : 'Pull to refresh manually whenever you need.',
    });
  }
}

function restoreAutoRefresh(refresh) {
  let enabled = false;
  try {
    enabled = window.localStorage.getItem(AUTO_REFRESH_KEY) === '1';
  } catch {
    enabled = false;
  }
  setAutoRefresh(refresh, enabled);
}

function bindKeyboard(refresh) {
  document.addEventListener('keydown', (event) => {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
    const target = event.target;
    const tag = String(target?.tagName || '').toLowerCase();
    const typing =
      ['input', 'textarea', 'select'].includes(tag) || Boolean(target?.isContentEditable);

    if (event.key === '/' && !typing) {
      event.preventDefault();
      document.getElementById('search-input')?.focus();
      return;
    }

    if ((event.key === 'r' || event.key === 'R') && !typing) {
      event.preventDefault();
      void refresh();
    }
  });
}

function bindStatusTabKeyboard() {
  const tablist = document.querySelector('[role="tablist"]');
  if (!tablist) return;

  tablist.addEventListener('keydown', (event) => {
    const tabs = Array.from(tablist.querySelectorAll('[data-status-tab]'));
    const current = tabs.indexOf(document.activeElement);
    if (current === -1) return;

    let next = current;
    if (event.key === 'ArrowRight') next = (current + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') next = (current - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;

    event.preventDefault();
    tabs[next].focus();
    tabs[next].click();
  });
}

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && state.autoRefresh) {
    document.getElementById('refresh-btn')?.click();
  }
});

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    void init();
  });
} else {
  void init();
}
