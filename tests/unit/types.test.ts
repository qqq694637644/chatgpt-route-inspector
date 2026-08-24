import { describe, expect, it } from 'vitest';
import { normalizeOverlayMode } from '../../src/core/types';

describe('overlay mode normalization', () => {
  it('keeps every supported overlay mode', () => {
    expect(normalizeOverlayMode('full')).toBe('full');
    expect(normalizeOverlayMode('compact')).toBe('compact');
    expect(normalizeOverlayMode('mini')).toBe('mini');
    expect(normalizeOverlayMode('docked')).toBe('docked');
  });

  it('rejects an unsupported stored mode instead of preserving it', () => {
    expect(normalizeOverlayMode('tiny')).toBe('full');
  });
});
