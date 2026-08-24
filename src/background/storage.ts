import { DEFAULT_SETTINGS, normalizeOverlayMode, type InspectorState, type PowObservation, type RouteObservation } from '../core/types';
import { browserUiLanguage, normalizeUiLanguage } from '../core/language';
import { normalizePowObservation, upsertPowReading } from '../core/pow';
import { upsertTurn } from '../core/turns';

export const STORAGE_KEY = 'chatgptRouteInspectorStateV2';
let queue = Promise.resolve();

export function defaultState(): InspectorState {
  return {
    turns: [],
    powReadings: [],
    settings: { ...DEFAULT_SETTINGS, uiLanguage: browserUiLanguage() },
    parserHealth: { lastSuccessAt: null, lastFailureAt: null, consecutiveFailures: 0 }
  };
}

export async function readState(): Promise<InspectorState> {
  const stored = await chrome.storage.local.get(STORAGE_KEY);
  const candidate = stored[STORAGE_KEY] as Partial<InspectorState> | undefined;
  if (!candidate) return defaultState();
  const turns = Array.isArray(candidate.turns) ? candidate.turns : [];
  const powReadings = Array.isArray(candidate.powReadings)
    ? candidate.powReadings
      .map(normalizePowObservation)
      .filter((reading): reading is NonNullable<typeof reading> => reading !== null)
    : [];
  const captureMode = candidate.settings?.captureMode === 'reload' ? 'reload' : 'live';
  const uiLanguage = normalizeUiLanguage(candidate.settings?.uiLanguage) ?? browserUiLanguage();
  const overlayMode = normalizeOverlayMode(candidate.settings?.overlayMode);
  return {
    turns,
    powReadings,
    settings: {
      ...DEFAULT_SETTINGS,
      ...candidate.settings,
      captureMode,
      uiLanguage,
      overlayMode
    },
    parserHealth: candidate.parserHealth ?? { lastSuccessAt: null, lastFailureAt: null, consecutiveFailures: 0 }
  };
}

export function storePowObservation(observation: PowObservation): Promise<InspectorState> {
  return mutateState((state) => ({
    ...state,
    powReadings: upsertPowReading(state.powReadings, observation)
  }));
}

export function mutateState(mutator: (state: InspectorState) => InspectorState | Promise<InspectorState>): Promise<InspectorState> {
  const operation = queue.then(async () => {
    const current = await readState();
    const next = await mutator(current);
    await chrome.storage.local.set({ [STORAGE_KEY]: next });
    return next;
  });
  queue = operation.then(() => undefined, () => undefined);
  return operation;
}

export function storeObservation(observation: RouteObservation): Promise<InspectorState> {
  return mutateState((state) => {
    const turns = upsertTurn(state.turns, observation).slice(0, state.settings.retentionLimit);
    const failed = observation.phase === 'failed';
    return {
      ...state,
      turns,
      parserHealth: failed
        ? { lastSuccessAt: state.parserHealth.lastSuccessAt, lastFailureAt: observation.observedAt, consecutiveFailures: state.parserHealth.consecutiveFailures + 1 }
        : { lastSuccessAt: observation.observedAt, lastFailureAt: state.parserHealth.lastFailureAt, consecutiveFailures: 0 }
    };
  });
}
