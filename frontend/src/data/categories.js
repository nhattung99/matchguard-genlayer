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

export const ATTESTATION_KINDS = [
  { id: 'ANTI_CHEAT', label: 'Anti-cheat attestation' },
  { id: 'PLATFORM_API', label: 'Tournament / platform API' },
  { id: 'ORGANIZER', label: 'Organizer attestation (disclosed trust)' },
];

export const EXAMPLE_PLATFORM_MATCH_ID = 'FACEIT-CS2-88421';
export const EXAMPLE_GAME_TITLE = 'Counter-Strike 2';
export const EXAMPLE_PLAYER_A_TAG = 's1mple';
export const EXAMPLE_PLAYER_B_TAG = 'device';
export const EXAMPLE_REPLAY_HASH = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

export const RECORD_ORIGIN = 'https://matchguard-genlayer.vercel.app';
const BLOCKED_HOST_SUFFIXES = ['wikipedia.org', 'wikimedia.org', 'mediawiki.org'];
const RECORD_TOKENS = [
  'match', 'room', 'replay', 'vod', 'anticheat', 'anti-cheat',
  'bracket', 'result', 'report', 'records', 'vac',
];

export const recordUrl = (matchId, file) =>
  `${RECORD_ORIGIN}/records/${matchId}/${file}`;

export const exampleOfficialUrl = (matchId = EXAMPLE_PLATFORM_MATCH_ID) =>
  recordUrl(matchId, 'official.html');
export const exampleReplayUrl = (matchId = EXAMPLE_PLATFORM_MATCH_ID) =>
  recordUrl(matchId, 'replay.html');
export const EXAMPLE_EVIDENCE_URL = recordUrl(EXAMPLE_PLATFORM_MATCH_ID, 'anticheat.html');
export const EXAMPLE_REFERENCE_URLS = [
  recordUrl(EXAMPLE_PLATFORM_MATCH_ID, 'vac.html'),
  recordUrl(EXAMPLE_PLATFORM_MATCH_ID, 'bracket.html'),
];

const MAX_URL_LEN = 400;
const MAX_EVIDENCE_URLS = 3;
const MAX_REFERENCE_URLS = 3;

export function parseHttpsUrl(url) {
  let cleaned = String(url || '').trim();
  if (!cleaned) throw new Error('URL cannot be empty.');
  const hash = cleaned.indexOf('#');
  if (hash >= 0) cleaned = cleaned.slice(0, hash);
  if (cleaned.includes(' ')) throw new Error('URL cannot contain spaces.');
  if (cleaned.length < 8 || cleaned.slice(0, 8).toLowerCase() !== 'https://') {
    throw new Error('Only https:// URLs are allowed.');
  }
  if (cleaned.length > MAX_URL_LEN) throw new Error('URL is too long.');
  return cleaned;
}

function hostAndPath(url) {
  const rest = url.slice(8);
  const slash = rest.indexOf('/');
  let host = (slash < 0 ? rest : rest.slice(0, slash)).toLowerCase();
  let path = slash < 0 ? '' : rest.slice(slash + 1);
  if (host.includes('?')) host = host.slice(0, host.indexOf('?'));
  if (host.includes(':')) host = host.slice(0, host.indexOf(':'));
  if (host.startsWith('www.')) host = host.slice(4);
  if (path.includes('?')) path = path.slice(0, path.indexOf('?'));
  return { host, path };
}

function hostBlocked(host) {
  return BLOCKED_HOST_SUFFIXES.some((suf) => host === suf || host.endsWith(`.${suf}`));
}

export function assertUrlBound(url, platformMatchId) {
  const norm = parseHttpsUrl(url);
  const mid = String(platformMatchId || '').trim();
  if (!mid) throw new Error('platform_match_id is required.');
  const { host, path } = hostAndPath(norm);
  if (hostBlocked(host)) {
    throw new Error('Generic encyclopedia pages cannot establish a match result or cheat claim.');
  }
  if (!path.toLowerCase().includes(mid.toLowerCase())) {
    throw new Error(`URL path must contain platform_match_id ${mid}; query-string binding is rejected.`);
  }
  if (!RECORD_TOKENS.some((tok) => path.toLowerCase().includes(tok))) {
    throw new Error('URL must be a match-linked official, replay, bracket, or anti-cheat record.');
  }
  return norm;
}

export function validateChallengeUrls(evidenceUrls, referenceUrls, platformMatchId) {
  const evidence = (evidenceUrls || []).map((u) => String(u || '').trim()).filter(Boolean);
  const refs = (referenceUrls || []).map((u) => String(u || '').trim()).filter(Boolean);
  if (evidence.length < 1) throw new Error('Paste at least 1 match-bound evidence URL.');
  if (evidence.length > MAX_EVIDENCE_URLS) throw new Error('At most 3 evidence URLs.');
  if (refs.length < 2) throw new Error('Paste at least 2 distinct match-bound reference URLs.');
  if (refs.length > MAX_REFERENCE_URLS) throw new Error('At most 3 reference URLs.');

  const evidenceNorm = [];
  const keys = [];
  for (const u of evidence) {
    const norm = assertUrlBound(u, platformMatchId);
    const key = norm.toLowerCase();
    if (keys.includes(key)) throw new Error('Duplicate evidence URL.');
    evidenceNorm.push(norm);
    keys.push(key);
  }
  const refNorm = [];
  const refKeys = [];
  for (const u of refs) {
    const norm = assertUrlBound(u, platformMatchId);
    const key = norm.toLowerCase();
    if (refKeys.includes(key) || keys.includes(key)) {
      throw new Error('Duplicate or overlapping reference URL.');
    }
    refNorm.push(norm);
    refKeys.push(key);
  }
  if (refKeys[0] === refKeys[1]) {
    throw new Error('The two reference URLs must be distinct.');
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
