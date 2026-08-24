import { describe, expect, it } from 'vitest';
import type { InspectorState, PowReading, RouteTurn } from '../../src/core/types';
import { latestForTab, latestPowForTab } from '../../src/ui/shared/client';

function stateWith(turns: RouteTurn[] = [], powReadings: PowReading[] = []): InspectorState {
  return {
    turns,
    powReadings,
    settings: {
      overlayEnabled: true,
      overlayMode: 'full',
      retentionLimit: 100,
      includeRequestIdsInExport: false,
      autoCaptureEnabled: true,
      captureMode: 'live',
      uiLanguage: 'zh'
    },
    parserHealth: { lastSuccessAt: null, lastFailureAt: null, consecutiveFailures: 0 }
  };
}

function turn(tabId: number, captureMode: 'live' | 'reload', requestedModel: string): RouteTurn {
  return { tabId, captureMode, requestedModel } as RouteTurn;
}

describe('popup current-tab selectors', () => {
  it('selects the latest matching mode from the active tab', () => {
    const current = turn(7, 'live', 'gpt-5-6-thinking');
    const otherTab = turn(9, 'live', 'gpt-5-6-pro');
    const otherMode = turn(7, 'reload', 'gpt-5-5-mini');

    expect(latestForTab(stateWith([otherTab, otherMode, current]), 7, 'live')).toBe(current);
  });

  it('does not fall back to another tab or a global history record', () => {
    const otherTab = turn(9, 'live', 'gpt-5-6-pro');
    const state = stateWith([otherTab]);

    expect(latestForTab(state, 7, 'live')).toBeNull();
    expect(latestForTab(state, undefined, 'live')).toBeNull();
  });

  it('keeps PoW readings scoped to the active tab', () => {
    const otherTab: PowReading = {
      rawHex: '063556',
      decimal: '406870',
      observedAt: '2026-08-11T01:00:00.000Z',
      tabId: 9
    };
    const current: PowReading = {
      rawHex: '0774fe',
      decimal: '488702',
      observedAt: '2026-08-11T01:01:00.000Z',
      tabId: 7
    };
    const state = stateWith([], [otherTab, current]);

    expect(latestPowForTab(state, 7)).toBe(current);
    expect(latestPowForTab(state, 8)).toBeNull();
    expect(latestPowForTab(state, undefined)).toBeNull();
  });
});
