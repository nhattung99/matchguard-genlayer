import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Shield,
  Wallet,
  PlusCircle,
  List,
  RefreshCw,
  ClipboardPaste,
  RotateCcw,
  Plus,
  Trash2,
  Share2,
  ExternalLink,
  Timer,
  Swords,
} from 'lucide-react';
import {
  CONTRACT_ADDRESS,
  hasContractAddress,
  getReadClient,
  getWriteClient,
  parseJsonMaybe,
  waitForTx,
  switchToStudionet,
  parseGenToWei,
  formatWeiToGen,
  sanitizeGenInput,
  toWeiString,
  toPercentInt,
  formatWriteError,
  isRateLimitError,
  txExplorerUrl,
  addressExplorerUrl,
  receiptLooksFailed,
} from './genlayerClient.js';
import {
  CATEGORIES,
  PRIZE_PRESETS,
  CHALLENGE_WINDOW_PRESETS,
  DEADLINE_PRESETS,
  deadlineUnixFromOffset,
  remainingUntil,
  formatDuration,
  isValidAddress,
  EXAMPLE_EVIDENCE_URL,
  EXAMPLE_REFERENCE_URLS,
  validateChallengeUrls,
} from './data/categories.js';

const shortAddr = (a) => {
  if (!a) return '—';
  const s = String(a);
  if (s.length < 12) return s;
  return `${s.slice(0, 6)}...${s.slice(-4)}`;
};

const sameAddr = (a, b) => String(a || '').toLowerCase() === String(b || '').toLowerCase();

const pasteClipboard = async () => {
  const text = await navigator.clipboard.readText();
  return (text || '').trim();
};

const statusClass = (status) => `badge badge-${String(status || '').toLowerCase()}`;

const readMatchIdFromUrl = () => {
  try {
    return new URLSearchParams(window.location.search).get('match') || '';
  } catch {
    return '';
  }
};

export default function App() {
  const [account, setAccount] = useState(null);
  const [tab, setTab] = useState('list');
  const [matches, setMatches] = useState([]);
  const [details, setDetails] = useState({});
  const [loading, setLoading] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  const [resolvingId, setResolvingId] = useState(null);
  const [txHash, setTxHash] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [shareHint, setShareHint] = useState('');
  const [nowTick, setNowTick] = useState(0);

  const [categoryId, setCategoryId] = useState(CATEGORIES[0].id);
  const [description, setDescription] = useState(CATEGORIES[0].description);
  const [playerA, setPlayerA] = useState('');
  const [playerB, setPlayerB] = useState('');
  const [amountStr, setAmountStr] = useState('1');
  const [deadlinePresetId, setDeadlinePresetId] = useState('1d');
  const [windowPresetId, setWindowPresetId] = useState('24h');

  const [evidenceUrls, setEvidenceUrls] = useState(['']);
  const [refUrls, setRefUrls] = useState(['', '']);
  const [activeMatchId, setActiveMatchId] = useState(readMatchIdFromUrl());

  const weiPreview = parseGenToWei(amountStr);
  const deadlinePreset = DEADLINE_PRESETS.find((d) => d.id === deadlinePresetId) || DEADLINE_PRESETS[2];
  const windowPreset = CHALLENGE_WINDOW_PRESETS.find((d) => d.id === windowPresetId) || CHALLENGE_WINDOW_PRESETS[3];
  const deadlineUnix = useMemo(
    () => deadlineUnixFromOffset(deadlinePreset.offsetSec),
    [deadlinePreset]
  );

  useEffect(() => {
    const id = window.setInterval(() => setNowTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, []);

  const applyCategory = (c) => {
    setCategoryId(c.id);
    setDescription(c.description);
  };

  const requireReady = () => {
    if (!hasContractAddress) {
      throw new Error('No contract address is configured. Deploy on GenLayer Studio, then set VITE_CONTRACT_ADDRESS.');
    }
    if (!account) {
      throw new Error('Connect a wallet first.');
    }
  };

  const connectWallet = async () => {
    try {
      if (!window.ethereum) {
        setErrorMessage('MetaMask is required to use MatchGuard.');
        return;
      }
      setErrorMessage(null);
      await switchToStudionet();
      const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
      const addr = accounts[0];
      try {
        const client = getWriteClient(addr);
        if (client.connect) await client.connect('studionet');
      } catch (err) {
        console.warn('studionet connect note:', err);
      }
      setAccount(addr);
    } catch (err) {
      setErrorMessage(formatWriteError(err) || 'Could not connect wallet');
    }
  };

  const fetchList = useCallback(async () => {
    if (!hasContractAddress) {
      setMatches([]);
      return;
    }
    const client = getReadClient();
    if (!client) return;
    try {
      setListLoading(true);
      let rows = [];
      let listOk = false;
      try {
        const res = await client.readContract({
          address: CONTRACT_ADDRESS,
          functionName: 'list_matches',
          args: [''],
        });
        const data = parseJsonMaybe(res);
        if (Array.isArray(data)) rows = data;
        listOk = true;
      } catch (err) {
        console.warn('list_matches failed:', err);
        if (!isRateLimitError(err)) setErrorMessage(formatWriteError(err));
      }

      if (rows.length === 0 && listOk) {
        try {
          const countRaw = await client.readContract({
            address: CONTRACT_ADDRESS,
            functionName: 'get_count',
            args: [],
          });
          const count = Number(String(countRaw ?? '0').replace(/[^0-9]/g, '') || '0');
          const rebuilt = [];
          for (let i = 0; i < count; i += 1) {
            try {
              const one = await client.readContract({
                address: CONTRACT_ADDRESS,
                functionName: 'get_match',
                args: [String(i)],
              });
              const row = parseJsonMaybe(one);
              if (row && typeof row === 'object' && !Array.isArray(row)) {
                rebuilt.push({ match_id: String(i), ...row });
              }
            } catch (err) {
              console.warn(`get_match ${i} failed:`, err);
            }
          }
          rows = rebuilt;
        } catch (err) {
          console.warn('get_count fallback failed:', err);
        }
      }

      setMatches(rows);
    } finally {
      setListLoading(false);
    }
  }, []);

  const fetchDetail = async (matchId) => {
    if (!hasContractAddress || !matchId) return null;
    try {
      const client = getReadClient();
      const res = await client.readContract({
        address: CONTRACT_ADDRESS,
        functionName: 'get_match',
        args: [String(matchId)],
      });
      const row = parseJsonMaybe(res);
      setDetails((prev) => ({ ...prev, [matchId]: row }));
      return row;
    } catch (err) {
      console.warn('get_match failed:', err);
      return null;
    }
  };

  useEffect(() => {
    fetchList();
    if (activeMatchId) fetchDetail(activeMatchId);
  }, [fetchList, activeMatchId]);

  const runWrite = async (fnName, args, value, { resolving, waitRetries, waitInterval } = {}) => {
    requireReady();
    setErrorMessage(null);
    setTxHash(null);
    if (resolving) setResolvingId(resolving);
    setLoading(true);
    try {
      await switchToStudionet();
      const client = getWriteClient(account);
      const hash = await client.writeContract({
        address: CONTRACT_ADDRESS,
        functionName: fnName,
        args,
        ...(value !== undefined ? { value } : {}),
      });
      setTxHash(hash);
      let receipt = hash;
      if (fnName !== 'create_match') {
        receipt = await waitForTx(client, hash, {
          retries: waitRetries ?? 12,
          interval: waitInterval ?? 3000,
        });
      }
      try {
        await fetchList();
      } catch (err) {
        console.warn('post-write list failed:', err);
      }
      const detailId = args && args[0] !== undefined ? String(args[0]) : '';
      const row = detailId ? await fetchDetail(detailId) : null;
      if (fnName === 'resolve_challenge' && row && row.status === 'CHALLENGED') {
        throw new Error(
          `AI transaction finalized but GenVM rolled back — match is still CHALLENGED. ` +
          `Open Explorer: ${txExplorerUrl(hash)}. ` +
          `Usual cause: web.render failed on a JS-heavy URL (HLTV, Twitter). ` +
          `Create a new match and challenge with two Wikipedia pages.`
        );
      }
      if (receiptLooksFailed(receipt)) {
        throw new Error(
          `Transaction finalized with a GenVM error. Check Explorer: ${txExplorerUrl(hash)}`
        );
      }
      return hash;
    } catch (err) {
      setErrorMessage(formatWriteError(err) || `${fnName} failed`);
      throw err;
    } finally {
      setLoading(false);
      setResolvingId(null);
    }
  };

  const shareLink = (matchId) => {
    const url = `${window.location.origin}${window.location.pathname}?match=${matchId}`;
    return url;
  };

  const copyShare = async (matchId) => {
    const url = shareLink(matchId);
    try {
      await navigator.clipboard.writeText(url);
      setShareHint(`Copied match link #${matchId}`);
    } catch {
      setShareHint(url);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      const wei = parseGenToWei(amountStr);
      if (wei <= 0n) throw new Error('Prize must be greater than 0 GEN.');
      if (!description.trim()) throw new Error('Description cannot be empty.');
      if (!isValidAddress(playerA) || !isValidAddress(playerB)) {
        throw new Error('Player A and Player B must be valid 0x addresses.');
      }
      if (sameAddr(playerA, playerB)) throw new Error('Player A and Player B must be different.');
      const windowSec = BigInt(windowPreset.seconds);
      await runWrite(
        'create_match',
        [playerA.trim(), playerB.trim(), description.trim(), deadlineUnix, windowSec],
        wei
      );
      setTab('list');
    } catch (err) {
      setErrorMessage(formatWriteError(err) || 'Create match failed');
    }
  };

  const cleanUrls = (arr) => arr.map((u) => u.trim()).filter(Boolean);

  const handleDeclare = async (matchId, side) => {
    try {
      await runWrite('declare_result', [matchId, side]);
    } catch (err) {
      setErrorMessage(formatWriteError(err) || 'Declare result failed');
    }
  };

  const handleChallenge = async (matchId) => {
    try {
      const ev = cleanUrls(evidenceUrls);
      const refs = cleanUrls(refUrls);
      const checked = validateChallengeUrls(ev, refs);
      await runWrite('challenge_result', [matchId, checked.evidence, checked.refs]);
      setEvidenceUrls(['']);
      setRefUrls(['', '']);
    } catch (err) {
      setErrorMessage(formatWriteError(err) || 'Challenge failed');
    }
  };

  const handleResolve = async (matchId) => {
    try {
      await runWrite('resolve_challenge', [matchId], undefined, {
        resolving: matchId,
        waitRetries: 90,
        waitInterval: 4000,
      });
      setActiveMatchId(matchId);
      await fetchDetail(matchId);
    } catch (err) {
      setErrorMessage(formatWriteError(err) || 'AI adjudication failed');
    }
  };

  const handleFinalize = async (matchId) => {
    try {
      await runWrite('finalize_unchallenged_payout', [matchId]);
    } catch (err) {
      setErrorMessage(formatWriteError(err) || 'Claim prize failed');
    }
  };

  const handleExpiredRefund = async (matchId) => {
    try {
      await runWrite('claim_expired_refund', [matchId]);
    } catch (err) {
      setErrorMessage(formatWriteError(err) || 'Expired refund failed');
    }
  };

  const handleRecover = async (matchId) => {
    try {
      await runWrite('recover_unresolved_escrow', [matchId]);
    } catch (err) {
      setErrorMessage(formatWriteError(err) || 'Timeout recovery failed');
    }
  };

  const handleRetry = async (matchId) => {
    try {
      await runWrite('retry_resolution', [matchId]);
    } catch (err) {
      setErrorMessage(formatWriteError(err) || 'Retry payout failed');
    }
  };

  const renderUrlEditor = () => (
    <>
      <div className="field">
        <label className="label">Evidence URLs (min 1)</label>
        <p className="hint">
          Only https Wikipedia articles. GenVM cannot render HLTV, Twitter, or YouTube. One click fills examples:
        </p>
        <button
          type="button"
          className="btn-secondary"
          style={{ marginBottom: '0.55rem' }}
          onClick={() => {
            setEvidenceUrls([EXAMPLE_EVIDENCE_URL]);
            setRefUrls([...EXAMPLE_REFERENCE_URLS]);
          }}
        >
          Fill example Wikipedia URLs (GenVM can fetch these)
        </button>
        {evidenceUrls.map((u, i) => (
          <div className="url-row" key={`e-${i}`}>
            <input
              className="input mono"
              placeholder="https://en.wikipedia.org/wiki/…"
              value={u}
              onChange={(e) => {
                const next = [...evidenceUrls];
                next[i] = e.target.value;
                setEvidenceUrls(next);
              }}
            />
            <button
              type="button"
              className="btn-ghost"
              onClick={async () => {
                const text = await pasteClipboard();
                const next = [...evidenceUrls];
                next[i] = text;
                setEvidenceUrls(next);
              }}
            >
              <ClipboardPaste size={14} /> Paste
            </button>
            {evidenceUrls.length > 1 && (
              <button type="button" className="btn-ghost" onClick={() => setEvidenceUrls(evidenceUrls.filter((_, j) => j !== i))}>
                <Trash2 size={14} />
              </button>
            )}
          </div>
        ))}
        <button type="button" className="btn-ghost" onClick={() => setEvidenceUrls([...evidenceUrls, ''])}>
          <Plus size={14} /> Add evidence URL
        </button>
      </div>
      <div className="field">
        <label className="label">Independent reference URLs (min 2)</label>
        {refUrls.map((u, i) => (
          <div className="url-row" key={`r-${i}`}>
            <input
              className="input mono"
              placeholder="https://en.wikipedia.org/wiki/…"
              value={u}
              onChange={(e) => {
                const next = [...refUrls];
                next[i] = e.target.value;
                setRefUrls(next);
              }}
            />
            <button
              type="button"
              className="btn-ghost"
              onClick={async () => {
                const text = await pasteClipboard();
                const next = [...refUrls];
                next[i] = text;
                setRefUrls(next);
              }}
            >
              <ClipboardPaste size={14} /> Paste
            </button>
            {refUrls.length > 2 && (
              <button type="button" className="btn-ghost" onClick={() => setRefUrls(refUrls.filter((_, j) => j !== i))}>
                <Trash2 size={14} />
              </button>
            )}
          </div>
        ))}
        <button type="button" className="btn-ghost" onClick={() => setRefUrls([...refUrls, ''])}>
          <Plus size={14} /> Add reference URL
        </button>
      </div>
    </>
  );

  const renderMatchCard = (row) => {
    const detail = details[row.match_id] || {};
    const status = detail.status || row.status;
    const verdict = detail.verdict || row.verdict;
    const reason = detail.verdict_reason;
    const confidence = detail.confidence ?? row.confidence;
    const prizeWei = toWeiString(detail.prize_amount || row.prize_amount);
    const isOpen = activeMatchId === row.match_id;
    const organizer = detail.organizer || row.organizer;
    const pA = detail.player_a || row.player_a;
    const pB = detail.player_b || row.player_b;
    const isOrganizer = account && sameAddr(account, organizer);
    const isPlayerA = account && sameAddr(account, pA);
    const isPlayerB = account && sameAddr(account, pB);
    const isPlayer = isPlayerA || isPlayerB;
    const isParty = isPlayer || isOrganizer;
    const declared = detail.declared_winner || row.declared_winner || '';
    const deadlineLeft = remainingUntil(detail.result_deadline || row.result_deadline);
    const declaredAt = BigInt(String(detail.result_declared_at || row.result_declared_at || '0').replace(/[^0-9]/g, '') || '0');
    const challengedAt = BigInt(String(detail.challenged_at || row.challenged_at || '0').replace(/[^0-9]/g, '') || '0');
    const windowSec = BigInt(String(detail.challenge_window_seconds || row.challenge_window_seconds || '0').replace(/[^0-9]/g, '') || '0');
    const challengeEnd = declaredAt + windowSec;
    const challengeLeft = remainingUntil(challengeEnd.toString());
    const windowClosed = declaredAt > 0n && challengeLeft === 0n;
    const recoverEnd = challengedAt + windowSec;
    const recoverLeft = remainingUntil(recoverEnd.toString());
    const recoverReady = challengedAt > 0n && recoverLeft === 0n;
    const stuckAi = status === 'CHALLENGED' || status === 'DISPUTED_LOW_CONFIDENCE';
    const deadlinePassed = deadlineLeft === 0n;

    return (
      <div className="card" key={row.match_id}>
        <div className="row-between">
          <div>
            <div className="label">Match #{row.match_id}</div>
            <div className="amount">{formatWeiToGen(prizeWei)} GEN prize</div>
          </div>
          <span className={statusClass(status)}>{status}</span>
        </div>
        <p className="desc">{(detail.description || row.description || '').slice(0, 220)}</p>
        <div className="sides">
          <div className={`side ${declared === 'A' ? 'mine' : ''}`}>
            <span>Side A {declared === 'A' ? '· declared winner' : ''}</span>
            <b className="mono">{shortAddr(pA)}</b>
          </div>
          <div className={`side ${declared === 'B' ? 'mine' : ''}`}>
            <span>Side B {declared === 'B' ? '· declared winner' : ''}</span>
            <b className="mono">{shortAddr(pB)}</b>
          </div>
        </div>
        <div className="stack meta">
          <div>Organizer: <span className="mono">{shortAddr(organizer)}</span></div>
          {status === 'AWAITING_RESULT' && (
            <div className="countdown">
              <Timer size={13} /> Result deadline: {deadlinePassed ? 'passed' : formatDuration(deadlineLeft)}
            </div>
          )}
          {status === 'RESULT_DECLARED' && (
            <div className={`countdown ${windowClosed ? 'closed' : ''}`}>
              <Timer size={13} /> Challenge window: {windowClosed ? 'closed — prize can be claimed' : formatDuration(challengeLeft)}
            </div>
          )}
          {stuckAi && challengedAt > 0n && (
            <div className={`countdown ${recoverReady ? 'closed' : ''}`}>
              <Timer size={13} /> Timeout refund: {recoverReady ? 'available — prize can return to organizer' : formatDuration(recoverLeft)}
            </div>
          )}
        </div>

        {verdict && (
          <div className={`verdict-box verdict-${String(verdict).toLowerCase()}`}>
            <strong>Verdict: {verdict}</strong>
            {confidence !== undefined && confidence !== '' && (
              <span className="mono conf">confidence {toPercentInt(confidence)}</span>
            )}
            {reason && <p>{reason}</p>}
          </div>
        )}

        <div className="actions">
          <button
            className="btn-ghost full"
            type="button"
            onClick={() => {
              setActiveMatchId(isOpen ? '' : row.match_id);
              fetchDetail(row.match_id);
            }}
          >
            {isOpen ? 'Hide actions' : 'Open actions'}
          </button>

          {isOpen && (
            <button className="btn-secondary full" type="button" onClick={() => copyShare(row.match_id)}>
              <Share2 size={15} /> Share match link with players
            </button>
          )}

          {isOpen && status === 'AWAITING_RESULT' && isParty && !deadlinePassed && (
            <div className="two-col">
              <button className="btn-primary full" type="button" disabled={loading} onClick={() => handleDeclare(row.match_id, 'A')}>
                Declare A wins
              </button>
              <button className="btn-primary full" type="button" disabled={loading} onClick={() => handleDeclare(row.match_id, 'B')}>
                Declare B wins
              </button>
            </div>
          )}

          {isOpen && status === 'AWAITING_RESULT' && isOrganizer && deadlinePassed && (
            <button className="btn-danger full" type="button" disabled={loading} onClick={() => handleExpiredRefund(row.match_id)}>
              Claim expired refund
            </button>
          )}

          {isOpen && (status === 'RESULT_DECLARED' || status === 'DISPUTED_LOW_CONFIDENCE') && isPlayer && !windowClosed && (
            <>
              {status === 'DISPUTED_LOW_CONFIDENCE' && (
                <div className="warn-box">Low confidence. Submit new evidence, then request AI adjudication again.</div>
              )}
              {renderUrlEditor()}
              <button className="btn-secondary full" type="button" disabled={loading} onClick={() => handleChallenge(row.match_id)}>
                <Swords size={15} /> File cheat challenge
              </button>
            </>
          )}

          {isOpen && status === 'RESULT_DECLARED' && windowClosed && (
            <button className="btn-primary full" type="button" disabled={loading} onClick={() => handleFinalize(row.match_id)}>
              Claim prize for declared winner
            </button>
          )}

          {isOpen && status === 'CHALLENGED' && (
            <>
              <div className="warn-box">
                Use Wikipedia evidence only. Consensus can take several minutes. If GenVM ERROR,
                wait for the timeout refund or start a new match with two distinct Wikipedia articles.
              </div>
              <button className="btn-ai" type="button" disabled={loading} onClick={() => handleResolve(row.match_id)}>
                {resolvingId === row.match_id ? (
                  <>
                    <span className="spinner" /> AI is reading the evidence — wait for consensus…
                  </>
                ) : (
                  <>
                    <Shield size={16} /> Request AI adjudication
                  </>
                )}
              </button>
            </>
          )}

          {isOpen && stuckAi && recoverReady && (
            <button className="btn-danger full" type="button" disabled={loading} onClick={() => handleRecover(row.match_id)}>
              Timeout refund to organizer
            </button>
          )}

          {isOpen && status === 'PAYOUT_FAILED' && isParty && (
            <button className="btn-primary full" type="button" disabled={loading} onClick={() => handleRetry(row.match_id)}>
              <RotateCcw size={15} /> Retry payout
            </button>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="app">
      <div className="free-banner">
        Free to use — you only pay GenLayer network gas when you sign a transaction. There is no platform fee.
      </div>

      {!hasContractAddress && (
        <div className="missing-banner">
          No contract address is wired yet. The app is in preview mode and will not crash.
          Deploy on GenLayer Studio, confirm <strong>Result: SUCCESS</strong>, then set{' '}
          <span className="mono">VITE_CONTRACT_ADDRESS</span> in <span className="mono">frontend/.env</span> and restart{' '}
          <span className="mono">npm run dev</span>.
        </div>
      )}

      <header className="header">
        <div className="brand">
          <div className="brand-mark">
            <Shield size={22} />
          </div>
          <div>
            <h1>MatchGuard</h1>
            <p>Amateur esports prize escrow · cheat challenge</p>
          </div>
        </div>
        <div className="header-right">
          <div className="network"><span className="dot" /> studionet</div>
          {account ? (
            <button className="btn-secondary mono" type="button">
              <Wallet size={16} /> {shortAddr(account)}
            </button>
          ) : (
            <button className="btn-primary" type="button" onClick={connectWallet}>
              <Wallet size={16} /> Connect wallet
            </button>
          )}
        </div>
      </header>

      <section className="howto-card">
        <h2>How to try this app</h2>
        <ol>
          <li>Install MetaMask. Click <strong>Connect wallet</strong> — the app switches to <strong>studionet</strong> (not Asimov/Bradbury testnet).</li>
          <li>Fund that same address with GEN from the GenLayer Studio <strong>Accounts</strong> panel. Do not use the public testnet faucet.</li>
          <li>Create a match: pick two player addresses, a category chip, a prize chip, a result deadline, and a challenge window. Share the <span className="mono">?match=</span> link.</li>
          <li>A player or the organizer declares A or B before the deadline. The challenge countdown starts.</li>
          <li>If nobody challenges, anyone can click <strong>Claim prize</strong> after the window. If a player challenges, paste 1 Wikipedia evidence article + 2 different Wikipedia reference articles, then <strong>Request AI adjudication</strong>.</li>
          <li>Read the on-chain <strong>verdict</strong> + <strong>reason</strong> + confidence. If AI stays stuck in CHALLENGED or low-confidence past the timeout, anyone can click <strong>Timeout refund to organizer</strong>. Confirm Explorer <strong>GenVM Result: SUCCESS</strong>, not only FINALIZED.</li>
        </ol>
      </section>

      <nav className="tabs">
        <button className={`tab ${tab === 'list' ? 'active' : ''}`} onClick={() => setTab('list')}>
          <List size={16} /> Matches ({matches.length})
        </button>
        <button className={`tab ${tab === 'create' ? 'active' : ''}`} onClick={() => setTab('create')}>
          <PlusCircle size={16} /> Create match
        </button>
      </nav>

      {txHash && (
        <div className="ok-banner">
          Transaction submitted:{' '}
          <a className="explorer-link" href={txExplorerUrl(txHash)} target="_blank" rel="noreferrer">
            {shortAddr(txHash)} <ExternalLink size={13} />
          </a>
        </div>
      )}
      {shareHint && <div className="ok-banner">{shareHint}</div>}
      {errorMessage && <div className="err-banner">{errorMessage}</div>}

      {tab === 'list' && (
        <div>
          <div className="row-between" style={{ marginBottom: '1rem' }}>
            <h2>Open matches</h2>
            <button className="btn-secondary" type="button" onClick={fetchList} disabled={listLoading || !hasContractAddress}>
              <RefreshCw size={14} /> Refresh
            </button>
          </div>

          {!hasContractAddress && (
            <div className="card empty">
              <Shield size={36} />
              <p style={{ marginTop: '0.75rem' }}>Preview mode — a deployed contract address is required to load live matches.</p>
              <button className="btn-primary" style={{ marginTop: '1rem' }} type="button" onClick={() => setTab('create')}>
                Explore create flow
              </button>
            </div>
          )}

          {hasContractAddress && listLoading && matches.length === 0 && (
            <div className="card empty">
              <p>Loading matches from studionet…</p>
            </div>
          )}

          {hasContractAddress && !listLoading && matches.length === 0 && (
            <div className="card empty">
              <p>No matches yet.</p>
              <button className="btn-primary" style={{ marginTop: '1rem' }} type="button" onClick={() => setTab('create')}>
                Create the first match
              </button>
            </div>
          )}

          <div className="grid">
            {matches.map(renderMatchCard)}
          </div>
        </div>
      )}

      {tab === 'create' && (
        <form className="card create-card" onSubmit={handleCreate}>
          <h2>Create a prize match</h2>

          <div className="field">
            <label className="label">Game category</label>
            <div className="chips">
              {CATEGORIES.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={`chip-card ${categoryId === c.id ? 'active' : ''}`}
                  onClick={() => applyCategory(c)}
                >
                  <b>{c.icon} {c.name}</b>
                  <span>{c.blurb}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="field">
            <label className="label">Match description (edit the template)</label>
            <textarea
              className="input textarea"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div className="two-col">
            <div className="field">
              <label className="label">Player A address</label>
              <div className="url-row">
                <input
                  className="input mono"
                  placeholder="0x…"
                  value={playerA}
                  onChange={(e) => setPlayerA(e.target.value.trim())}
                />
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={async () => setPlayerA(await pasteClipboard())}
                >
                  <ClipboardPaste size={14} /> Paste
                </button>
                {account && (
                  <button type="button" className="btn-ghost" onClick={() => setPlayerA(account)}>
                    Me
                  </button>
                )}
              </div>
            </div>
            <div className="field">
              <label className="label">Player B address</label>
              <div className="url-row">
                <input
                  className="input mono"
                  placeholder="0x…"
                  value={playerB}
                  onChange={(e) => setPlayerB(e.target.value.trim())}
                />
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={async () => setPlayerB(await pasteClipboard())}
                >
                  <ClipboardPaste size={14} /> Paste
                </button>
              </div>
            </div>
          </div>

          <div className="field">
            <label className="label">Prize (GEN)</label>
            <div className="chips" style={{ marginBottom: '0.55rem' }}>
              {PRIZE_PRESETS.map((p) => (
                <button
                  key={p}
                  type="button"
                  className={`chip ${amountStr === p ? 'active' : ''}`}
                  onClick={() => setAmountStr(p)}
                >
                  {p} GEN
                </button>
              ))}
            </div>
            <input
              className="input mono"
              inputMode="decimal"
              value={amountStr}
              onChange={(e) => setAmountStr(sanitizeGenInput(e.target.value))}
            />
            <div className="hint mono">wei (parseGenToWei): {weiPreview.toString()}</div>
          </div>

          <div className="field">
            <label className="label">Result deadline</label>
            <div className="chips">
              {DEADLINE_PRESETS.map((d) => (
                <button
                  key={d.id}
                  type="button"
                  className={`chip ${deadlinePresetId === d.id ? 'active' : ''}`}
                  onClick={() => setDeadlinePresetId(d.id)}
                >
                  {d.label}
                </button>
              ))}
            </div>
            <div className="hint mono">unix: {deadlineUnix.toString()}</div>
          </div>

          <div className="field">
            <label className="label">Challenge window</label>
            <div className="chips">
              {CHALLENGE_WINDOW_PRESETS.map((d) => (
                <button
                  key={d.id}
                  type="button"
                  className={`chip ${windowPresetId === d.id ? 'active' : ''}`}
                  onClick={() => setWindowPresetId(d.id)}
                >
                  {d.label}
                </button>
              ))}
            </div>
            <div className="hint mono">seconds: {windowPreset.seconds}</div>
          </div>

          <button className="btn-primary full" type="submit" disabled={loading || !hasContractAddress}>
            {loading ? 'Locking GEN…' : `Create match · lock ${formatWeiToGen(weiPreview)} GEN`}
          </button>
          {!hasContractAddress && (
            <p className="hint">Create stays disabled until VITE_CONTRACT_ADDRESS is set.</p>
          )}
        </form>
      )}

      {hasContractAddress && (
        <footer className="footer">
          Contract{' '}
          <a className="explorer-link mono" href={addressExplorerUrl(CONTRACT_ADDRESS)} target="_blank" rel="noreferrer">
            {shortAddr(CONTRACT_ADDRESS)} <ExternalLink size={12} />
          </a>
          {' · '}studionet
        </footer>
      )}
    </div>
  );
}
