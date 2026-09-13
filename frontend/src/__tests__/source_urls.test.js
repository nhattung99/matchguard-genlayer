import {
  validateChallengeUrls,
  assertUrlBound,
  EXAMPLE_PLATFORM_MATCH_ID,
  EXAMPLE_EVIDENCE_URL,
  EXAMPLE_REFERENCE_URLS,
  exampleOfficialUrl,
  exampleReplayUrl,
} from '../data/categories.js';

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

assert(validateChallengeUrls([EXAMPLE_EVIDENCE_URL], EXAMPLE_REFERENCE_URLS, EXAMPLE_PLATFORM_MATCH_ID).refs.length === 2, 'valid records');
assert(assertUrlBound(exampleOfficialUrl(), EXAMPLE_PLATFORM_MATCH_ID).includes(EXAMPLE_PLATFORM_MATCH_ID), 'official path');
assert(assertUrlBound(exampleReplayUrl(), EXAMPLE_PLATFORM_MATCH_ID).includes('/replay'), 'replay path');

let threw = false;
try {
  validateChallengeUrls(['https://www.hltv.org/matches/1'], EXAMPLE_REFERENCE_URLS, EXAMPLE_PLATFORM_MATCH_ID);
} catch {
  threw = true;
}
assert(threw, 'unbound hltv must fail');

threw = false;
try {
  assertUrlBound(`https://en.wikipedia.org/wiki/FACEIT?match=${EXAMPLE_PLATFORM_MATCH_ID}`, EXAMPLE_PLATFORM_MATCH_ID);
} catch {
  threw = true;
}
assert(threw, 'wikipedia query binding must fail');

threw = false;
try {
  assertUrlBound(`https://en.wikipedia.org/wiki/${EXAMPLE_PLATFORM_MATCH_ID}`, EXAMPLE_PLATFORM_MATCH_ID);
} catch {
  threw = true;
}
assert(threw, 'wikipedia path must fail');

threw = false;
try {
  assertUrlBound(`https://www.faceit.com/en/cs2/room?match=${EXAMPLE_PLATFORM_MATCH_ID}`, EXAMPLE_PLATFORM_MATCH_ID);
} catch {
  threw = true;
}
assert(threw, 'query-only platform URL must fail');

threw = false;
try {
  validateChallengeUrls([EXAMPLE_EVIDENCE_URL], [EXAMPLE_REFERENCE_URLS[0], EXAMPLE_REFERENCE_URLS[0]], EXAMPLE_PLATFORM_MATCH_ID);
} catch {
  threw = true;
}
assert(threw, 'duplicate refs must fail');

console.log('source URL validation tests passed.');
