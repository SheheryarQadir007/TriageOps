/**
 * Presentation helpers and design tokens for leads.
 */

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => {
    switch (character) {
      case '&':
        return '&amp;';
      case '<':
        return '&lt;';
      case '>':
        return '&gt;';
      case '"':
        return '&quot;';
      case "'":
        return '&#39;';
      default:
        return character;
    }
  });
}

export const AVATAR_TONES = [
  'bg-indigo-50 text-indigo-700 ring-indigo-100',
  'bg-emerald-50 text-emerald-700 ring-emerald-100',
  'bg-amber-50 text-amber-700 ring-amber-100',
  'bg-sky-50 text-sky-700 ring-sky-100',
  'bg-violet-50 text-violet-700 ring-violet-100',
  'bg-rose-50 text-rose-700 ring-rose-100',
  'bg-teal-50 text-teal-700 ring-teal-100',
];

export function avatarTone(id) {
  const index = Math.abs(Number(id) || 0) % AVATAR_TONES.length;
  return AVATAR_TONES[index];
}

export function initials(name) {
  const parts = String(name || '')
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

export function formatCurrency(value, { compact = false } = {}) {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  const useCompact = compact && Math.abs(number) >= 10_000;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
    notation: useCompact ? 'compact' : 'standard',
  }).format(number);
}

export function formatNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString() : '—';
}

export function timeAgo(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  const seconds = Math.max(0, (Date.now() - date.getTime()) / 1000);

  if (seconds < 45) return 'Just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 7 * 86_400) return `${Math.floor(seconds / 86_400)}d ago`;

  const sameYear = date.getFullYear() === new Date().getFullYear();
  return date.toLocaleDateString([], {
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : { year: 'numeric' }),
  });
}

export function fullDate(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export const URGENCY_STYLES = {
  High: {
    badge: 'bg-rose-50 text-rose-700 ring-rose-600/15',
    dot: 'bg-rose-500',
    bar: 'bg-rose-500',
    text: 'text-rose-600',
  },
  Medium: {
    badge: 'bg-amber-50 text-amber-700 ring-amber-600/15',
    dot: 'bg-amber-500',
    bar: 'bg-amber-500',
    text: 'text-amber-600',
  },
  Low: {
    badge: 'bg-emerald-50 text-emerald-700 ring-emerald-600/15',
    dot: 'bg-emerald-500',
    bar: 'bg-emerald-500',
    text: 'text-emerald-600',
  },
};

export function urgencyStyle(urgency) {
  return URGENCY_STYLES[urgency] || URGENCY_STYLES.Low;
}

export const CATEGORY_STYLES = {
  'Emergency Repair': 'bg-rose-50 text-rose-700 ring-rose-600/15',
  'New Implementation': 'bg-indigo-50 text-indigo-700 ring-indigo-600/15',
  Maintenance: 'bg-amber-50 text-amber-700 ring-amber-600/15',
  'General Inquiry': 'bg-slate-100 text-slate-600 ring-slate-500/15',
};

export function categoryStyle(category) {
  return CATEGORY_STYLES[category] || CATEGORY_STYLES['General Inquiry'];
}

export const STATUS_STYLES = {
  New: {
    badge: 'bg-sky-50 text-sky-700 ring-sky-600/15',
    dot: 'bg-sky-500',
  },
  Contacted: {
    badge: 'bg-amber-50 text-amber-700 ring-amber-600/15',
    dot: 'bg-amber-500',
  },
  Closed: {
    badge: 'bg-slate-100 text-slate-600 ring-slate-500/15',
    dot: 'bg-slate-400',
  },
};

export function statusStyle(status) {
  return STATUS_STYLES[status] || STATUS_STYLES.New;
}

export function statusHint(status) {
  return (
    {
      New: 'Awaiting first response.',
      Contacted: 'Conversation in progress.',
      Closed: 'Archived from the active queue.',
    }[status] || 'Workflow status.'
  );
}

export function signalTone(signal) {
  const value = String(signal || '').toLowerCase();
  if (
    value.includes('deadline') ||
    value.includes('urgent') ||
    value.includes('down') ||
    value.includes('asap') ||
    value.includes('emergency')
  ) {
    return 'bg-rose-50 text-rose-600 ring-rose-600/15';
  }
  if (
    value.startsWith('budget:met') ||
    value.startsWith('description:complete') ||
    value.includes('qualified')
  ) {
    return 'bg-emerald-50 text-emerald-700 ring-emerald-600/15';
  }
  if (
    value.startsWith('budget:below') ||
    value.startsWith('budget:missing') ||
    value.startsWith('description:incomplete')
  ) {
    return 'bg-amber-50 text-amber-700 ring-amber-600/15';
  }
  return 'bg-slate-50 text-slate-600 ring-slate-500/15';
}

export function providerLabel(provider) {
  return (
    {
      rules: 'Rules engine',
      openai: 'OpenAI',
      gemini: 'Gemini',
    }[provider] || provider || 'Rules engine'
  );
}

export function engineLabel(engine) {
  return (
    {
      rules: 'Rules',
      'rules-fallback': 'Rules fallback',
      openai: 'OpenAI',
      gemini: 'Gemini',
    }[engine] || engine || 'Rules'
  );
}

export function titleCase(value) {
  const text = String(value || '').replace(/[_-]+/g, ' ').trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : '—';
}
