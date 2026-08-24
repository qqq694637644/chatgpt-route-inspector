import { copyFile, cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const target = 'edge-android';

const uiEntries = ['popup', 'dashboard', 'options', 'onboarding'];
const commonBuild = {
  absWorkingDir: root,
  bundle: true,
  target: 'chrome151',
  logLevel: 'info',
  legalComments: 'none',
  sourcemap: false
};

async function ensureParent(file) {
  await mkdir(path.dirname(file), { recursive: true });
}

async function copy(source, target) {
  await ensureParent(target);
  await copyFile(path.join(root, source), target);
}

async function buildTarget() {
  const outdir = path.join(root, 'dist', target);
  const allowedOrigins = ['https://chatgpt.com'];
  const define = {
    __ROUTE_INSPECTOR_ALLOWED_ORIGINS__: JSON.stringify(allowedOrigins)
  };

  await rm(outdir, { recursive: true, force: true });
  await mkdir(outdir, { recursive: true });

  await build({
    ...commonBuild,
    entryPoints: { 'background/service-worker': 'src/background/service-worker.ts' },
    outdir,
    format: 'esm',
    define
  });

  await build({
    ...commonBuild,
    entryPoints: {
      'content/page-hook': 'src/content/page-hook.ts',
      'content/bridge': 'src/content/bridge.ts',
      ...Object.fromEntries(uiEntries.map((name) => [`ui/${name}/index`, `src/ui/${name}/index.ts`]))
    },
    outdir,
    format: 'iife',
    define
  });

  for (const name of uiEntries) {
    await copy(`src/ui/${name}/index.html`, path.join(outdir, 'ui', name, 'index.html'));
  }
  await copy('src/ui/shared/styles.css', path.join(outdir, 'ui', 'shared', 'styles.css'));
  await copy('schemas/route-turn.v1.schema.json', path.join(outdir, 'schemas', 'route-turn.v1.schema.json'));
  await cp(path.join(root, '_locales'), path.join(outdir, '_locales'), { recursive: true });
  await cp(path.join(root, 'icons'), path.join(outdir, 'icons'), { recursive: true });

  const manifest = JSON.parse(await readFile(path.join(root, 'manifest', 'manifest.json'), 'utf8'));
  await writeFile(path.join(outdir, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
  process.stdout.write(`Built ${target}: ${outdir}\n`);
}

await buildTarget();
