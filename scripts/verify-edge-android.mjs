import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourceManifestPath = path.join(root, 'manifest', 'manifest.json');
const builtManifestPath = path.join(root, 'dist', 'edge-android', 'manifest.json');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function readJson(file) {
  return JSON.parse(await readFile(file, 'utf8'));
}

function verifyManifest(manifest, label) {
  assert(manifest.manifest_version === 3, `${label}: manifest_version must be 3`);
  assert(manifest.version === '2.0.0', `${label}: version must be 2.0.0`);
  assert(manifest.minimum_chrome_version === '151', `${label}: minimum_chrome_version must be 151`);
  assert(JSON.stringify(manifest.permissions) === JSON.stringify(['storage']), `${label}: permissions must be storage only`);
  assert(JSON.stringify(manifest.host_permissions) === JSON.stringify(['https://chatgpt.com/*']), `${label}: only chatgpt.com may be a host permission`);
  assert(!('options_ui' in manifest), `${label}: options_ui desktop entry point is forbidden`);
  assert(!('options_page' in manifest), `${label}: options_page desktop entry point is forbidden`);
  assert(manifest.background?.service_worker === 'background/service-worker.js', `${label}: MV3 service worker is required`);
  assert(manifest.background?.type === 'module', `${label}: service worker must be a module`);
  assert(manifest.action?.default_popup === 'ui/popup/index.html', `${label}: mobile action popup is required`);
  assert(Array.isArray(manifest.content_scripts) && manifest.content_scripts.length === 2, `${label}: exactly two content scripts are required`);

  const worlds = manifest.content_scripts.map((script) => script.world);
  assert(JSON.stringify(worlds) === JSON.stringify(['MAIN', 'ISOLATED']), `${label}: content script worlds must be MAIN then ISOLATED`);
  for (const script of manifest.content_scripts) {
    assert(script.run_at === 'document_start', `${label}: every content script must run at document_start`);
    assert(JSON.stringify(script.matches) === JSON.stringify(['https://chatgpt.com/*']), `${label}: every content script must target chatgpt.com only`);
  }
}

const sourceManifest = await readJson(sourceManifestPath);
const builtManifest = await readJson(builtManifestPath);
verifyManifest(sourceManifest, 'source manifest');
verifyManifest(builtManifest, 'built manifest');
assert(JSON.stringify(sourceManifest) === JSON.stringify(builtManifest), 'built manifest must exactly match the source manifest');

process.stdout.write('Edge Android artifact contract verified.\n');
