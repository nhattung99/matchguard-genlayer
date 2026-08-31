export const CATEGORIES = [
  {
    id: 'fps',
    icon: '🎯',
    name: 'FPS',
    blurb: 'CS2 / Valorant / Aim',
    description: 'CS2 Bo3 — Community Cup Round 1. Two players, public VOD required if a cheat report is filed.',
  },
  {
    id: 'moba',
    icon: '🛡️',
    name: 'MOBA',
    blurb: 'League / Dota 2',
    description: 'League of Legends Bo3 — amateur cup. Winner is the side that takes the series; map veto recorded in the match notes.',
  },
  {
    id: 'fighting',
    icon: '🥊',
    name: 'Fighting Game',
    blurb: 'Street Fighter / Tekken',
    description: 'Street Fighter 6 FT5 — local weekly. Winner is first to 5 games. Replay and bracket page required for any challenge.',
  },
  {
    id: 'other',
    icon: '🎮',
    name: 'Other',
    blurb: 'Any community match',
    description: 'Community match with a GEN prize. Result must be declared before the deadline; a challenge needs replay/log plus two independent public sources.',
  },
];

export const PRIZE_PRESETS = ['0.1', '0.5', '1', '2', '5', '10'];

export const CHALLENGE_WINDOW_PRESETS = [
  { id: 'demo', label: '2 min (demo)', seconds: '120' },
  { id: '6h', label: '6 hours', seconds: '21600' },
  { id: '12h', label: '12 hours', seconds: '43200' },
  { id: '24h', label: '24 hours', seconds: '86400' },
  { id: '48h', label: '48 hours', seconds: '172800' },
];

export const DEADLINE_PRESETS = [
  { id: '1h', label: 'In 1 hour', offsetSec: '3600' },
  { id: '6h', label: 'In 6 hours', offsetSec: '21600' },
  { id: '1d', label: 'In 1 day', offsetSec: '86400' },
  { id: '3d', label: 'In 3 days', offsetSec: '259200' },
  { id: 'past', label: 'Already passed (refund demo)', offsetSec: '-60' },
];

/** Real public pages — paste-ready. Do not invent gists or localhost URLs. */
export const EXAMPLE_EVIDENCE_URL = 'https://en.wikipedia.org/wiki/Cheating_in_online_games';
export const EXAMPLE_REFERENCE_URLS = [
  'https://en.wikipedia.org/wiki/Valve_Anti-Cheat',
  'https://www.hltv.org/',
];

export function unixNow() {
  return BigInt(Date.now()) / 1000n;
}

export function deadlineUnixFromOffset(offsetSecStr) {
  const raw = String(offsetSecStr ?? '0').trim();
  const negative = raw.startsWith('-');
  const digits = (negative ? raw.slice(1) : raw).replace(/[^0-9]/g, '') || '0';
  const offset = BigInt(digits);
  const nowSec = unixNow();
  const unix = negative ? nowSec - offset : nowSec + offset;
  return unix > 0n ? unix : 1n;
}

export function remainingUntil(endUnix) {
  const end = BigInt(String(endUnix ?? '0').replace(/[^0-9]/g, '') || '0');
  const now = unixNow();
  return now >= end ? 0n : end - now;
}

export function formatDuration(secVal) {
  let sec = BigInt(String(secVal ?? '0').replace(/[^0-9]/g, '') || '0');
  if (sec <= 0n) return 'closed';
  const d = sec / 86400n;
  sec %= 86400n;
  const h = sec / 3600n;
  sec %= 3600n;
  const m = sec / 60n;
  const s = sec % 60n;
  const parts = [];
  if (d > 0n) parts.push(`${d.toString()}d`);
  if (h > 0n) parts.push(`${h.toString()}h`);
  if (m > 0n) parts.push(`${m.toString()}m`);
  parts.push(`${s.toString()}s`);
  return parts.join(' ');
}

export function isValidAddress(value) {
  return /^0x[0-9a-fA-F]{40}$/.test(String(value || '').trim());
}
