import type { InspectorState } from '../../core/types';
import { getState, send, subscribe } from '../shared/client';
import { applyStaticTranslations, bindLanguageSwitch } from '../shared/i18n';

let state: InspectorState;

function render(next: InspectorState): void {
  state = next;
  applyStaticTranslations(state.settings.uiLanguage);
}

bindLanguageSwitch(async (uiLanguage) => {
  if (state?.settings.uiLanguage === uiLanguage) return;
  const response = await send({ type: 'route:update-settings', settings: { uiLanguage } });
  if (response.state) render(response.state);
});
document.querySelector('#dashboard')?.addEventListener('click', () => void send({ type: 'route:open-page', page: 'dashboard' }));
document.querySelector('#options')?.addEventListener('click', () => void send({ type: 'route:open-page', page: 'options' }));

void getState().then((initial) => {
  render(initial);
  subscribe(render);
});
