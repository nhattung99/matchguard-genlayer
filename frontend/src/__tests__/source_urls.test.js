import { splitWikiHostPath, validateChallengeUrls } from '../data/categories.js';

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const ev = 'https://en.wikipedia.org/wiki/Cheating_in_online_games';
const r1 = 'https://en.wikipedia.org/wiki/Valve_Anti-Cheat';
const r2 = 'https://en.wikipedia.org/wiki/Esports';

assert(splitWikiHostPath(ev).path === '/wiki/Cheating_in_online_games', 'path preserve case');
assert(validateChallengeUrls([ev], [r1, r2]).refs.length === 2, 'valid trio');

let threw = false;
try {
  validateChallengeUrls(['https://www.hltv.org/'], [r1, r2]);
} catch {
  threw = true;
}
assert(threw, 'hltv must fail');

threw = false;
try {
  validateChallengeUrls([ev], [r1, r1]);
} catch {
  threw = true;
}
assert(threw, 'duplicate refs must fail');

console.log('source URL validation tests passed.');
