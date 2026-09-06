import { createClient, chains } from 'genlayer-js';
import {
  parseGenToWei,
  formatWeiToGen,
  sanitizeGenInput,
  toWeiString,
  toPercentInt,
  WEI_PER_GEN,
} from './money.js';

export {
  parseGenToWei,
  formatWeiToGen,
  sanitizeGenInput,
  toWeiString,
  toPercentInt,
  WEI_PER_GEN,
};

const ZERO = '0x0000000000000000000000000000000000000000';
const rawAddress = (import.meta.env.VITE_CONTRACT_ADDRESS || '').trim();

export const EXPLORER_BASE = 'https://explorer-studio.genlayer.com';
export const STUDIONET_RPC = 'https://studio.genlayer.com/api';

export const txExplorerUrl = (hash) => {
  if (!hash) return EXPLORER_BASE;
  return `${EXPLORER_BASE}/tx/${hash}`;
};

export const addressExplorerUrl = (addr) => {
  if (!addr) return EXPLORER_BASE;
  return `${EXPLORER_BASE}/address/${addr}`;
};

export const CONTRACT_ADDRESS = rawAddress || ZERO;

export const hasContractAddress = Boolean(
  rawAddress &&
  rawAddress !== ZERO &&
  /^0x[0-9a-fA-F]{40}$/.test(rawAddress)
);

export const studionet = chains.studionet;

const toAddress = (account) => {
  if (!account) return '';
  if (typeof account === 'string') return account;
  return account.address || '';
};

export const getReadClient = () => {
  try {
    return createClient({ chain: studionet, endpoint: STUDIONET_RPC });
  } catch (err) {
    console.warn('Read client init failed:', err);
    return null;
  }
};

export const getWriteClient = (account) => {
  if (typeof window === 'undefined' || !window.ethereum) {
    throw new Error('MetaMask is required to sign MatchGuard transactions on GenLayer.');
  }
  return createClient({
    chain: studionet,
    endpoint: STUDIONET_RPC,
    account: toAddress(account),
    provider: window.ethereum,
  });
};

export const parseJsonMaybe = (res) => {
  if (res === null || res === undefined) return res;
  if (typeof res === 'string') {
    try {
      return JSON.parse(res);
    } catch {
      return res;
    }
  }
  return res;
};

const errorBlob = (err) =>
  [
    err?.shortMessage,
    err?.details,
    err?.cause?.message,
    err?.cause?.data?.message,
    err?.message,
    err,
  ]
    .filter(Boolean)
    .map(String)
    .join(' ');

export const getRetryAfterSeconds = (err) => {
  const nodes = [err, err?.cause, err?.cause?.cause, err?.data, err?.cause?.data];
  for (const node of nodes) {
    const n = Number(node?.retry_after_seconds ?? node?.data?.retry_after_seconds);
    if (Number.isFinite(n) && n > 0) return Math.ceil(n);
  }
  return 0;
};

export const isRateLimitError = (err) => {
  const low = errorBlob(err).toLowerCase();
  return (
    low.includes('rate limit') ||
    low.includes('-32029') ||
    low.includes('-32429') ||
    low.includes('429')
  );
};

export const formatWriteError = (err) => {
  const parts = [
    err?.shortMessage,
    err?.details,
    err?.cause?.message,
    err?.message,
    err,
  ].filter(Boolean).map(String);
  const msg = parts[0] || '';
  const low = errorBlob(err).toLowerCase();
  if (low.includes('user rejected') || low.includes('user denied') || low.includes('rejected the request')) {
    return 'Cancelled in MetaMask. Check the fox icon — approve the studionet switch first (chain 61999), then Confirm the Create transaction that locks the prize GEN.';
  }
  if (low.includes('insufficient') || low.includes('funds')) {
    return 'Not enough GEN for the prize plus gas.';
  }
  if (isRateLimitError(err)) {
    const wait = getRetryAfterSeconds(err);
    const mins = wait ? Math.max(1, Math.ceil(wait / 60)) : 10;
    return `Studionet rate limit reached. Wait about ${mins} minute(s). Do not refresh or click Create. Close extra MatchGuard tabs, then retry once.`;
  }
  if (low.includes('failed to fetch') || low.includes('unknown rpc')) {
    return 'Cannot reach Studionet RPC (Failed to fetch). Confirm MetaMask is on studionet (chain 61999), wait if you hit the hourly limit, then retry once.';
  }
  return msg || 'Write transaction failed.';
};

const studionetChainIdHex = () => {
  const id = studionet?.id || 61999;
  return `0x${BigInt(id).toString(16)}`;
};

const sameChainId = (left, right) => {
  try {
    return BigInt(left).toString() === BigInt(right).toString();
  } catch {
    return String(left).toLowerCase() === String(right).toLowerCase();
  }
};

export const switchToStudionet = async () => {
  if (typeof window === 'undefined' || !window.ethereum) return;
  const chainIdHex = studionetChainIdHex();
  const current = await window.ethereum.request({ method: 'eth_chainId' });
  if (sameChainId(current, chainIdHex)) return;

  try {
    await window.ethereum.request({
      method: 'wallet_switchEthereumChain',
      params: [{ chainId: chainIdHex }],
    });
  } catch (switchError) {
    if (Number(switchError.code) === 4902) {
      try {
        await window.ethereum.request({
          method: 'wallet_addEthereumChain',
          params: [{
            chainId: chainIdHex,
            chainName: studionet.name || 'GenLayer Studionet',
            nativeCurrency: studionet.nativeCurrency || {
              name: 'GenLayer Token',
              symbol: 'GEN',
              decimals: 18,
            },
            rpcUrls: studionet.rpcUrls?.default?.http || [STUDIONET_RPC],
            blockExplorerUrls: [studionet.blockExplorers?.default?.url || EXPLORER_BASE],
          }],
        });
      } catch (addError) {
        if (Number(addError.code) === 4001) {
          throw new Error('You cancelled adding studionet in MetaMask. Approve the network, then retry.');
        }
        throw addError;
      }
    } else if (Number(switchError.code) === 4001) {
      throw new Error('You cancelled the studionet switch in MetaMask. Switch to chain 61999, then retry Create.');
    } else {
      throw switchError;
    }
  }

  const after = await window.ethereum.request({ method: 'eth_chainId' });
  if (!sameChainId(after, chainIdHex)) {
    throw new Error('MetaMask is not on studionet (chain 61999). Switch network, then retry Create.');
  }
};

export const waitForTx = async (client, hash, { retries = 30, interval = 2000 } = {}) => {
  if (!hash) return null;
  if (client && typeof client.waitForTransactionReceipt === 'function') {
    try {
      return await client.waitForTransactionReceipt({
        hash,
        status: 'FINALIZED',
        retries,
        interval,
      });
    } catch (err) {
      if (isRateLimitError(err)) return hash;
      console.warn('waitForTransactionReceipt note:', err);
    }
  }
  return hash;
};

export const receiptLooksFailed = (receipt) => {
  if (!receipt || typeof receipt !== 'object') return false;
  const blob = JSON.stringify(receipt).toLowerCase();
  return (
    blob.includes('rollback') ||
    blob.includes('"error"') ||
    blob.includes('failed to fetch') ||
    blob.includes('execution result":"error')
  );
};
