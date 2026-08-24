import { defaultState, mutateState, readState, STORAGE_KEY, storeObservation, storePowObservation } from './storage';
import { normalizeUiLanguage } from '../core/language';
import { normalizeObservation } from '../core/observation';
import type { InspectorState, PowObservation, RouteObservation } from '../core/types';
import type { RuntimeRequest, RuntimeResponse } from '../shared/messages';

const allowedOrigins = new Set(__ROUTE_INSPECTOR_ALLOWED_ORIGINS__);

async function updateBadge(tabId: number | undefined, state: InspectorState): Promise<void> {
  if (tabId === undefined) return;
  const latest = state.turns.find((turn) => turn.tabId === tabId && turn.captureMode === state.settings.captureMode);
  const text = latest?.verdict === 'mismatch' || latest?.verdict === 'conflict'
    ? '!'
    : latest?.verdict === 'normal'
      ? 'OK'
      : latest?.phase === 'requested' || latest?.phase === 'responding'
        ? '…'
        : '?';
  const color = text === '!' ? '#d95343' : text === 'OK' ? '#6fa92e' : '#b47d2d';
  await chrome.action.setBadgeBackgroundColor({ tabId, color });
  await chrome.action.setBadgeText({ tabId, text });
}

async function broadcast(state: InspectorState): Promise<void> {
  const message = { type: 'route:state-changed', state };
  try {
    await chrome.runtime.sendMessage(message);
  } catch {
    // No extension page is currently listening.
  }
  try {
    const tabs = await chrome.tabs.query({});
    await Promise.allSettled(tabs.map(async (tab) => {
      if (tab.id === undefined || !tab.url) return;
      try {
        if (!allowedOrigins.has(new URL(tab.url).origin)) return;
      } catch {
        return;
      }
      await chrome.tabs.sendMessage(tab.id, message);
    }));
  } catch {
    // A tab can disappear or deny messaging between query and delivery.
  }
}

async function acceptObservation(observation: RouteObservation): Promise<InspectorState> {
  const normalized = normalizeObservation(observation);
  if (!normalized) throw new Error('无效的路由观察记录。');
  const state = await storeObservation(normalized);
  await updateBadge(normalized.tabId, state);
  await broadcast(state);
  return state;
}

async function acceptPowObservation(observation: PowObservation): Promise<InspectorState> {
  const state = await storePowObservation(observation);
  await broadcast(state);
  return state;
}

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') void chrome.tabs.create({ url: chrome.runtime.getURL('ui/onboarding/index.html') });
});

chrome.runtime.onMessage.addListener((raw: unknown, sender, sendResponse: (response: RuntimeResponse) => void) => {
  const request = raw as RuntimeRequest;
  void (async () => {
    if (request.type === 'route:observation') {
      const observation: RouteObservation = sender.tab?.id === undefined
        ? request.observation
        : { ...request.observation, tabId: sender.tab.id };
      return { ok: true, state: await acceptObservation(observation) };
    }
    if (request.type === 'pow:observation') {
      const observation: PowObservation = sender.tab?.id === undefined
        ? request.observation
        : { ...request.observation, tabId: sender.tab.id };
      return { ok: true, state: await acceptPowObservation(observation) };
    }
    if (request.type === 'route:get-state') {
      const state = await readState();
      return sender.tab?.id === undefined ? { ok: true, state } : { ok: true, state, tabId: sender.tab.id };
    }
    if (request.type === 'route:update-settings') {
      const requestedLanguage = request.settings.uiLanguage;
      const uiLanguage = requestedLanguage === undefined ? undefined : normalizeUiLanguage(requestedLanguage);
      if (requestedLanguage !== undefined && !uiLanguage) return { ok: false, error: 'Invalid UI language.' };
      const settings = uiLanguage ? { ...request.settings, uiLanguage } : request.settings;
      const state = await mutateState((current) => ({ ...current, settings: { ...current.settings, ...settings } }));
      await broadcast(state);
      return { ok: true, state };
    }
    if (request.type === 'route:clear') {
      const current = await readState();
      const state: InspectorState = { ...defaultState(), settings: current.settings };
      await chrome.storage.local.clear();
      await chrome.storage.local.set({ [STORAGE_KEY]: state });
      await broadcast(state);
      return { ok: true, state };
    }
    if (request.type === 'route:open-page') {
      await chrome.tabs.create({ url: chrome.runtime.getURL(`ui/${request.page}/index.html`) });
      return { ok: true };
    }
    return { ok: false, error: '未知请求。' };
  })().then(sendResponse).catch((error: unknown) => sendResponse({
    ok: false,
    error: error instanceof Error ? error.message : '扩展内部错误。'
  }));
  return true;
});
