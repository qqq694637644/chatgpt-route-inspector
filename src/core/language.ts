import type { UiLanguage } from './types';

export function normalizeUiLanguage(value: unknown): UiLanguage | null {
  if (typeof value !== 'string') return null;
  const normalized = value.trim().toLowerCase().replaceAll('_', '-');
  if (normalized === 'zh' || normalized.startsWith('zh-')) return 'zh';
  if (normalized === 'en' || normalized.startsWith('en-')) return 'en';
  return null;
}

export function detectUiLanguage(locale: string | null | undefined): UiLanguage {
  return normalizeUiLanguage(locale) === 'zh' ? 'zh' : 'en';
}

export function browserUiLanguage(): UiLanguage {
  return detectUiLanguage(chrome.i18n.getUILanguage());
}
