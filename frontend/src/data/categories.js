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

/** Wikipedia pages — GenVM web.render can fetch these. JS-heavy sites (HLTV, Twitter) fail. */
export const EXAMPLE_EVIDENCE_URL = 'https://en.wikipedia.org/wiki/Cheating_in_online_games';
export const EXAMPLE_REFERENCE_URLS = [
  'https://en.wikipedia.org/wiki/Valve_Anti-Cheat',
  'https://en.wikipedia.org/wiki/Esports',
];

const MAX_URL_LEN = 256;
const MAX_EVIDENCE_URLS = 3;
const MAX_REFERENCE_URLS = 3;

export function splitWikiHostPath(url) {
  let cleaned = String(url || '').trim();
  if (!cleaned) throw new Error('URL cannot be empty.');
  const hash = cleaned.indexOf('#');
  if (hash >= 0) cleaned = cleaned.slice(0, hash);
  const q = cleaned.indexOf('?');
  if (q >= 0) cleaned = cleaned.slice(0, q);
  while (cleaned.endsWith('/')) cleaned = cleaned.slice(0, -1);
  if (cleaned.length < 8 || cleaned.slice(0, 8).toLowerCase() !== 'https://') {
    throw new Error('Only https:// Wikipedia URLs are allowed.');
  }
  const rest = cleaned.slice(8);
  const slash = rest.indexOf('/');
  let host = (slash >= 0 ? rest.slice(0, slash) : rest).toLowerCase();
  const path = slash >= 0 ? `/${rest.slice(slash + 1)}` : '';
  if (host.startsWith('www.')) host = host.slice(4);
  if (host !== 'wikipedia.org' && !host.endsWith('.wikipedia.org')) {
    throw new Error(`Source host is not Wikipedia: ${host}`);
  }
  if (path.length < 2) throw new Error('Wikipedia URL must include an article path.');
  const normalized = `https://${host}${path}`;
  if (normalized.length > MAX_URL_LEN) throw new Error('URL is too long.');
  return { host, path, normalized };
}

export function validateChallengeUrls(evidenceUrls, referenceUrls) {
  const evidence = (evidenceUrls || []).map((u) => String(u || '').trim()).filter(Boolean);
  const refs = (referenceUrls || []).map((u) => String(u || '').trim()).filter(Boolean);
  if (evidence.length < 1) throw new Error('Paste at least 1 Wikipedia evidence URL.');
  if (evidence.length > MAX_EVIDENCE_URLS) throw new Error('At most 3 evidence URLs.');
  if (refs.length < 2) throw new Error('Paste at least 2 distinct Wikipedia reference articles.');
  if (refs.length > MAX_REFERENCE_URLS) throw new Error('At most 3 reference URLs.');

  const evidenceNorm = [];
  const evidenceKeys = [];
  for (const u of evidence) {
    const parsed = splitWikiHostPath(u);
    if (evidenceKeys.some((k) => k.toLowerCase() === parsed.path.toLowerCase())) {
      throw new Error('Duplicate evidence URL.');
    }
    evidenceNorm.push(parsed.normalized);
    evidenceKeys.push(parsed.path);
  }
  const refNorm = [];
  const refKeys = [];
  for (const u of refs) {
    const parsed = splitWikiHostPath(u);
    if (refKeys.some((k) => k.toLowerCase() === parsed.path.toLowerCase())) {
      throw new Error('Duplicate reference URL.');
    }
    if (evidenceKeys.some((k) => k.toLowerCase() === parsed.path.toLowerCase())) {
      throw new Error('Reference URLs must be distinct from evidence URLs.');
    }
    refNorm.push(parsed.normalized);
    refKeys.push(parsed.path);
  }
  if (refKeys[0].toLowerCase() === refKeys[1].toLowerCase()) {
    throw new Error('The two reference URLs must be distinct Wikipedia articles.');
  }
  return { evidence: evidenceNorm, refs: refNorm };
}

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
