import { createHash } from 'node:crypto';
import { createWriteStream } from 'node:fs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import archiver from 'archiver';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const releaseDir = path.join(root, 'release');
const packageJson = JSON.parse(await readFile(path.join(root, 'package.json'), 'utf8'));
const version = packageJson.version;
await mkdir(releaseDir, { recursive: true });
execFileSync(process.execPath, [path.join(root, 'scripts', 'build.mjs')], { cwd: root, stdio: 'inherit' });

async function zipDirectory(source, target) {
  await new Promise((resolve, reject) => {
    const output = createWriteStream(target);
    const archive = archiver('zip', { zlib: { level: 9 } });
    output.on('close', resolve);
    output.on('error', reject);
    archive.on('error', reject);
    archive.pipe(output);
    archive.directory(source, false);
    void archive.finalize();
  });
}

const name = `chatgpt-route-inspector-edge-android-${version}.zip`;
const target = path.join(releaseDir, name);
await zipDirectory(path.join(root, 'dist', 'edge-android'), target);
const hash = createHash('sha256').update(await readFile(target)).digest('hex');
await writeFile(path.join(releaseDir, 'SHA256SUMS.txt'), `${hash}  ${name}\n`, 'utf8');
process.stdout.write(`Packaged releases in ${releaseDir}\n`);
