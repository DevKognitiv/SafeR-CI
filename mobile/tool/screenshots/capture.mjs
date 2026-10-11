#!/usr/bin/env node
// Playwright screenshot harness for the SafeR demo web build.
//
// Serves a built web directory (default mobile/build/web) from a tiny static
// server, opens every screen of routes.json in the variant matrix (theme x
// locale x text scale x viewport, plus a tablet variant), waits for the app's
// readiness signal (window.saferReady), paints the masks of masks.json and
// writes PNGs plus a manifest. Node 22, no npm install: the globally
// available playwright module is loaded through createRequire (NODE_PATH).
//
//   node tool/screenshots/capture.mjs [--build] [--only=home,sos] [--serve-only]
//
// See README.md next to this file and docs/qa/screenshot-harness.md.

import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MOBILE_DIR = path.resolve(__dirname, '..', '..');
const REPO_DIR = path.resolve(MOBILE_DIR, '..');

// ----------------------------------------------------------------- matrix
const DEFAULT_MATRIX = {
  themes: ['light', 'dark'],
  locales: ['fr', 'en'],
  scales: ['1.0', '2.0'],
  viewports: ['360x780', '412x915'],
  tablet: '600x960',
  deviceScaleFactor: 2,
};

// ----------------------------------------------------------------- arguments
function parseArgs(argv) {
  const args = {
    build: false,
    serveOnly: false,
    check: false,
    only: null,
    webDir: path.join(MOBILE_DIR, 'build', 'web'),
    out: path.join(__dirname, 'out'),
    port: 0,
    settle: 1500,
    readyTimeout: 45000,
    parallel: 2,
    masks: true,
    strict: true,
    headed: false,
    extraStates: [],
    flutter: null,
    fontsDir: null,
    themes: null,
    locales: null,
    scales: null,
    viewports: null,
    tablet: true,
  };
  // Both `--flag=value` and `--flag value` are accepted for the flags that take a value.
  const takesValue = new Set([
    '--only', '--web-dir', '--out', '--port', '--settle', '--ready-timeout', '--parallel', '--states', '--flutter',
    '--fonts-dir', '--themes', '--locales', '--scales', '--viewports',
  ]);
  for (let i = 0; i < argv.length; i++) {
    const raw = argv[i];
    let [key, value] = raw.includes('=') ? raw.split(/=(.*)/s).slice(0, 2) : [raw, undefined];
    if (value === undefined && takesValue.has(key)) {
      const next = argv[i + 1];
      if (next === undefined || next.startsWith('-')) {
        console.error(`Missing value for ${key}`);
        printHelp();
        process.exit(2);
      }
      value = next;
      i++;
    }
    switch (key) {
      case '--build': args.build = true; break;
      case '--serve-only': args.serveOnly = true; break;
      case '--check': args.check = true; break;
      case '--only': args.only = value.split(',').map((s) => s.trim()).filter(Boolean); break;
      case '--web-dir': args.webDir = path.resolve(value); break;
      case '--out': args.out = path.resolve(value); break;
      case '--port': args.port = Number(value); break;
      case '--settle': args.settle = Number(value); break;
      case '--ready-timeout': args.readyTimeout = Number(value); break;
      case '--parallel': args.parallel = Math.max(1, Number(value)); break;
      case '--no-masks': args.masks = false; break;
      case '--no-strict': args.strict = false; break;
      case '--headed': args.headed = true; break;
      case '--states': args.extraStates = value.split(',').map((s) => s.trim()).filter(Boolean); break;
      case '--flutter': args.flutter = value; break;
      case '--fonts-dir': args.fontsDir = path.resolve(value); break;
      case '--themes': args.themes = value.split(','); break;
      case '--locales': args.locales = value.split(','); break;
      case '--scales': args.scales = value.split(','); break;
      case '--viewports': args.viewports = value.split(','); break;
      case '--no-tablet': args.tablet = false; break;
      case '--help': case '-h': printHelp(); process.exit(0); break;
      default:
        console.error(`Unknown argument: ${raw}`);
        printHelp();
        process.exit(2);
    }
  }
  return args;
}

function printHelp() {
  console.log(`Usage: node tool/screenshots/capture.mjs [options]

  --build              run "flutter build web --release --dart-define=SAFER_DEMO=1 --no-web-resources-cdn" first
  --serve-only         serve the web dir (default port 8089) and wait; no capture
  --only=a,b           capture only these screens of routes.json
  --check              verify out/manifest.json is complete for the matrix (no browser)
  --web-dir=DIR        built web directory (default mobile/build/web)
  --out=DIR            output directory (default tool/screenshots/out)
  --port=N             port of the static server (default: random free port; 8089 with --serve-only)
  --settle=MS          extra wait after window.saferReady (default 1500)
  --ready-timeout=MS   max wait for window.saferReady (default 45000)
  --parallel=N         concurrent pages (default 2)
  --states=a,b         extra DemoState names appended to every screen
  --themes=.. --locales=.. --scales=.. --viewports=..  narrow the matrix (lists)
  --no-tablet          skip the 600x960 variant
  --no-masks           do not paint masks.json
  --no-strict          exit 0 even when a variant failed
  --headed             show the browser
  --flutter=PATH       flutter executable for --build (default $FLUTTER_ROOT/bin/flutter or "flutter")
  --fonts-dir=DIR      directory holding Roboto-*.ttf served to the engine instead of fonts.gstatic.com
                       (default $FLUTTER_ROOT/bin/cache/artifacts/material_fonts)
`);
}

// ----------------------------------------------------------------- helpers
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.wasm': 'application/wasm',
  '.css': 'text/css; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.ttf': 'font/ttf',
  '.otf': 'font/otf',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.frag': 'text/plain; charset=utf-8',
  '.symbols': 'text/plain; charset=utf-8',
};

/** Static server over webDir with an index.html fallback (the app uses the hash URL strategy, so only "/" is ever requested). */
function startServer(webDir, port) {
  const root = path.resolve(webDir);
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://127.0.0.1');
      let rel = decodeURIComponent(url.pathname);
      if (rel.endsWith('/')) rel += 'index.html';
      let file = path.normalize(path.join(root, rel));
      if (!file.startsWith(root)) {
        res.writeHead(403);
        res.end();
        return;
      }
      let stat = await fsp.stat(file).catch(() => null);
      if (!stat || stat.isDirectory()) {
        file = path.join(root, 'index.html');
        stat = await fsp.stat(file).catch(() => null);
        if (!stat) {
          res.writeHead(404);
          res.end('not found');
          return;
        }
      }
      res.writeHead(200, {
        'Content-Type': MIME[path.extname(file).toLowerCase()] ?? 'application/octet-stream',
        'Content-Length': stat.size,
        'Cache-Control': 'no-store',
      });
      fs.createReadStream(file).pipe(res);
    } catch (error) {
      res.writeHead(500);
      res.end(String(error));
    }
  });
  return new Promise((resolve, reject) => {
    server.on('error', reject);
    server.listen(port, '127.0.0.1', () => resolve({ server, port: server.address().port }));
  });
}

function flutterExecutable(args) {
  if (args.flutter) return args.flutter;
  if (process.env.FLUTTER_ROOT) return path.join(process.env.FLUTTER_ROOT, 'bin', 'flutter');
  if (fs.existsSync('/opt/flutter/bin/flutter')) return '/opt/flutter/bin/flutter';
  return 'flutter';
}

function flutterRoot(args) {
  if (process.env.FLUTTER_ROOT) return process.env.FLUTTER_ROOT;
  const exe = flutterExecutable(args);
  if (exe !== 'flutter') return path.resolve(path.dirname(exe), '..');
  const which = spawnSync('which', ['flutter'], { encoding: 'utf8' });
  if (which.status === 0 && which.stdout.trim()) {
    const real = fs.realpathSync(which.stdout.trim());
    return path.resolve(path.dirname(real), '..');
  }
  return null;
}

/** Roboto files of the Flutter SDK cache, served to the engine in place of fonts.gstatic.com. */
function localFonts(args) {
  const dir = args.fontsDir ?? (flutterRoot(args) && path.join(flutterRoot(args), 'bin', 'cache', 'artifacts', 'material_fonts'));
  if (!dir || !fs.existsSync(path.join(dir, 'Roboto-Regular.ttf'))) return null;
  return dir;
}

/** The bundled Inter subset of the web build (Latin + arrows), served for the engine's Noto fallback requests. */
function bundledFallbackFont(webDir) {
  const file = path.join(webDir, 'assets', 'assets', 'fonts', 'inter', 'Inter-Variable.ttf');
  return fs.existsSync(file) ? file : null;
}

function buildWeb(args) {
  const exe = flutterExecutable(args);
  const cmd = ['build', 'web', '--release', '--dart-define=SAFER_DEMO=1', '--no-web-resources-cdn'];
  console.log(`[build] ${exe} ${cmd.join(' ')} (cwd ${MOBILE_DIR})`);
  const result = spawnSync(exe, cmd, { cwd: MOBILE_DIR, stdio: 'inherit' });
  if (result.status !== 0) {
    console.error(`[build] flutter build web failed with status ${result.status}`);
    process.exit(result.status ?? 1);
  }
}

function sha256(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

function gitCommit() {
  const result = spawnSync('git', ['rev-parse', '--short', 'HEAD'], { cwd: REPO_DIR, encoding: 'utf8' });
  return result.status === 0 ? result.stdout.trim() : null;
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

/** Expands the matrix for the selected screens into capture jobs. */
function buildJobs(args, routes) {
  const matrix = {
    themes: args.themes ?? DEFAULT_MATRIX.themes,
    locales: args.locales ?? DEFAULT_MATRIX.locales,
    scales: args.scales ?? DEFAULT_MATRIX.scales,
    viewports: args.viewports ?? DEFAULT_MATRIX.viewports,
    tablet: args.tablet ? DEFAULT_MATRIX.tablet : null,
    deviceScaleFactor: DEFAULT_MATRIX.deviceScaleFactor,
  };
  const selected = routes.screens.filter((r) => !args.only || args.only.includes(r.screen));
  if (args.only) {
    for (const name of args.only) {
      if (!routes.screens.some((r) => r.screen === name)) throw new Error(`--only: unknown screen "${name}" (routes.json has ${routes.screens.map((r) => r.screen).join(', ')})`);
    }
  }
  const jobs = [];
  for (const route of selected) {
    const states = [...(route.states ?? []), ...args.extraStates];
    const add = (theme, locale, scale, viewport) => {
      const [w, h] = viewport.split('x').map(Number);
      jobs.push({
        screen: route.screen,
        route: route.route,
        states,
        theme,
        locale,
        scale,
        viewport: { w, h, dpr: matrix.deviceScaleFactor },
        file: `${route.screen}/${theme}-${locale}-${scale}-${w}x${h}.png`,
      });
    };
    for (const theme of matrix.themes) {
      for (const locale of matrix.locales) {
        for (const scale of matrix.scales) {
          for (const viewport of matrix.viewports) add(theme, locale, scale, viewport);
        }
      }
    }
    if (route.tablet && matrix.tablet) add('light', 'fr', '1.0', matrix.tablet);
  }
  return { matrix, jobs };
}

function appUrl(base, job) {
  const url = new URL(base);
  url.searchParams.set('locale', job.locale);
  url.searchParams.set('theme', job.theme);
  url.searchParams.set('textScale', job.scale);
  url.searchParams.set('route', job.route);
  if (job.states.length) url.searchParams.set('state', job.states.join(','));
  url.searchParams.set('animations', 'off');
  return url.toString();
}

/** Resolves one mask rectangle to CSS px for the job's viewport. */
function resolveRect(rect, viewport) {
  const dim = (value, total) => {
    if (typeof value === 'number') return value;
    if (typeof value === 'string' && value.endsWith('%')) return (parseFloat(value) / 100) * total;
    throw new Error(`mask value "${value}" must be a number or a percentage`);
  };
  const w = dim(rect.w, viewport.w);
  const h = dim(rect.h, viewport.h);
  const x = rect.x === 'center' ? (viewport.w - w) / 2 : dim(rect.x, viewport.w);
  const y = dim(rect.y, viewport.h);
  return { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) };
}

function masksFor(masks, job) {
  const viewportName = `${job.viewport.w}x${job.viewport.h}`;
  return masks
    .filter((m) => !m.screens || m.screens.includes(job.screen))
    .filter((m) => !m.scales || m.scales.includes(job.scale))
    .filter((m) => !m.viewports || m.viewports.includes(viewportName))
    .filter((m) => !m.themes || m.themes.includes(job.theme))
    .filter((m) => !m.locales || m.locales.includes(job.locale))
    .map((m) => ({ name: m.name, ...resolveRect(m.rect, job.viewport) }));
}

const ANDROID_UA = 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36';

async function capture(browser, base, job, args, masks, fontsDir, outDir) {
  const context = await browser.newContext({
    viewport: { width: job.viewport.w, height: job.viewport.h },
    deviceScaleFactor: job.viewport.dpr,
    isMobile: true,
    hasTouch: true,
    userAgent: ANDROID_UA,
    locale: job.locale === 'fr' ? 'fr-CI' : 'en-US',
    colorScheme: job.theme,
    reducedMotion: 'reduce',
    timezoneId: 'Africa/Abidjan',
  });
  const consoleErrors = [];
  const fontRequests = [];
  try {
    // The engine fetches its fallback Roboto from Google Fonts at runtime, and a Noto font
    // for any glyph Roboto lacks (the arrow of "27.5 °C → 24.0 °C"): answer the first from
    // the SDK cache and the second with the bundled Inter subset (Latin + arrows), so no
    // request leaves the machine and the glyph set is the same on every run.
    await context.route(/https:\/\/fonts\.(gstatic|googleapis)\.com\/.*/, async (route) => {
      const url = route.request().url();
      fontRequests.push(url);
      if (fontsDir && /roboto/i.test(url)) {
        const file = /bold|wght@700|,700/i.test(url) ? 'Roboto-Bold.ttf' : /medium|wght@500|,500/i.test(url) ? 'Roboto-Medium.ttf' : 'Roboto-Regular.ttf';
        await route.fulfill({ status: 200, contentType: 'font/ttf', body: await fsp.readFile(path.join(fontsDir, file)) });
        return;
      }
      const fallback = bundledFallbackFont(args.webDir);
      if (fallback) {
        await route.fulfill({ status: 200, contentType: 'font/ttf', body: await fsp.readFile(fallback) });
        return;
      }
      if (fontsDir) {
        await route.abort();
        return;
      }
      await route.continue();
    });
    const page = await context.newPage();
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', (error) => consoleErrors.push(String(error)));
    const url = appUrl(base, job);
    await page.goto(url, { waitUntil: 'load', timeout: args.readyTimeout });
    await page.waitForFunction(() => window.saferReady === true || typeof window.saferError === 'string', null, { timeout: args.readyTimeout });
    const appError = await page.evaluate(() => (typeof window.saferError === 'string' ? window.saferError : null));
    if (appError) throw new Error(`app error: ${appError}`);
    await page.waitForTimeout(args.settle);
    const applied = args.masks ? masksFor(masks, job) : [];
    if (applied.length) {
      await page.evaluate((rects) => {
        for (const r of rects) {
          const div = document.createElement('div');
          div.dataset.saferMask = r.name;
          Object.assign(div.style, {
            position: 'fixed',
            left: `${r.x}px`,
            top: `${r.y}px`,
            width: `${r.w}px`,
            height: `${r.h}px`,
            background: '#6b7280',
            zIndex: '2147483647',
            pointerEvents: 'none',
          });
          document.body.appendChild(div);
        }
      }, applied);
      // One frame so the overlay is composited before the shot.
      await page.waitForTimeout(100);
    }
    const file = path.join(outDir, job.file);
    await fsp.mkdir(path.dirname(file), { recursive: true });
    const buffer = await page.screenshot({ path: file, type: 'png', fullPage: false, animations: 'disabled', caret: 'hide' });
    return { ok: true, path: path.relative(outDir, file), sha256: sha256(buffer), bytes: buffer.length, masks: applied.map((m) => m.name), url, consoleErrors, fontRequests };
  } catch (error) {
    return { ok: false, error: String(error && error.message ? error.message : error), url: appUrl(base, job), consoleErrors, fontRequests };
  } finally {
    await context.close();
  }
}

async function runPool(jobs, worker, parallel) {
  const results = new Array(jobs.length);
  let next = 0;
  const lanes = Array.from({ length: Math.min(parallel, jobs.length) }, async () => {
    while (next < jobs.length) {
      const index = next++;
      results[index] = await worker(jobs[index], index);
    }
  });
  await Promise.all(lanes);
  return results;
}

function checkManifest(args, routes) {
  const manifestFile = path.join(args.out, 'manifest.json');
  if (!fs.existsSync(manifestFile)) {
    console.error(`[check] ${manifestFile} is missing`);
    return 1;
  }
  const manifest = readJson(manifestFile);
  const { jobs } = buildJobs(args, routes);
  let missing = 0;
  for (const job of jobs) {
    const entry = manifest.entries.find((e) => (e.file ?? e.path) === job.file);
    const file = path.join(args.out, job.file);
    if (!entry || !entry.ok || !fs.existsSync(file)) {
      console.error(`[check] missing or failed: ${job.file}${entry && entry.error ? ` (${entry.error})` : ''}`);
      missing += 1;
    }
  }
  console.log(`[check] ${jobs.length - missing}/${jobs.length} variants present`);
  return missing ? 1 : 0;
}

// ----------------------------------------------------------------- main
async function main() {
  const args = parseArgs(process.argv.slice(2));
  const routes = readJson(path.join(__dirname, 'routes.json'));
  const masks = readJson(path.join(__dirname, 'masks.json')).masks;

  if (args.check) process.exit(checkManifest(args, routes));
  if (args.build) buildWeb(args);

  if (!fs.existsSync(path.join(args.webDir, 'index.html'))) {
    console.error(`[serve] ${args.webDir}/index.html not found: build first (--build) or pass --web-dir`);
    process.exit(2);
  }
  const { server, port } = await startServer(args.webDir, args.serveOnly && !args.port ? 8089 : args.port);
  const base = `http://127.0.0.1:${port}/`;
  console.log(`[serve] ${args.webDir} on ${base}`);
  if (args.serveOnly) {
    console.log('[serve] press Ctrl+C to stop. Example: ' + appUrl(base, { locale: 'fr', theme: 'light', scale: '1.0', route: '/security/sos', states: [] }));
    await new Promise(() => {});
    return;
  }

  const { matrix, jobs } = buildJobs(args, routes);
  const fontsDir = localFonts(args);
  console.log(`[fonts] ${fontsDir ? `serving Roboto from ${fontsDir}` : 'no local Roboto found: the engine will fetch it from fonts.gstatic.com'}`);
  console.log(`[capture] ${jobs.length} variants, ${args.parallel} in parallel, settle ${args.settle} ms, out ${args.out}`);
  await fsp.mkdir(args.out, { recursive: true });

  const { chromium } = require('playwright');
  const browser = await chromium.launch({ headless: !args.headed });
  const started = Date.now();
  let done = 0;
  const results = await runPool(jobs, async (job) => {
    const result = await capture(browser, base, job, args, masks, fontsDir, args.out);
    done += 1;
    const status = result.ok ? `${(result.bytes / 1024).toFixed(0)} KB` : `FAILED ${result.error}`;
    console.log(`[${String(done).padStart(3)}/${jobs.length}] ${job.file} ${status}`);
    return { ...job, ...result };
  }, args.parallel);
  await browser.close();
  server.close();

  const failed = results.filter((r) => !r.ok);
  // A partial run (--only, a narrowed matrix) merges into the manifest of a previous
  // full run instead of replacing it, so --check still sees the whole matrix.
  const manifestFile = path.join(args.out, 'manifest.json');
  const partial = Boolean(args.only || args.themes || args.locales || args.scales || args.viewports || !args.tablet);
  const previous = partial && fs.existsSync(manifestFile) ? readJson(manifestFile).entries ?? [] : [];
  const fresh = new Set(results.map((r) => r.file));
  const kept = previous.filter((e) => !fresh.has(e.file ?? e.path));
  const manifest = {
    generatedAt: new Date().toISOString(),
    commit: gitCommit(),
    host: `${os.platform()} ${os.release()} node ${process.version} playwright ${require('playwright/package.json').version}`,
    webDir: path.relative(REPO_DIR, args.webDir),
    matrix,
    masksApplied: args.masks,
    // Totals over every entry of the manifest (merged), then the figures of this run.
    expected: kept.length + jobs.length,
    captured: kept.filter((e) => e.ok).length + results.length - failed.length,
    failed: kept.filter((e) => !e.ok).length + failed.length,
    run: { expected: jobs.length, captured: results.length - failed.length, failed: failed.length, mergedFromPreviousRun: kept.length },
    entries: [...kept, ...results.map((r) => ({
      screen: r.screen,
      route: r.route,
      states: r.states,
      variant: { theme: r.theme, locale: r.locale, textScale: r.scale },
      viewport: r.viewport,
      url: r.url,
      path: r.ok ? r.path : null,
      sha256: r.ok ? r.sha256 : null,
      bytes: r.ok ? r.bytes : null,
      masks: r.masks ?? [],
      ok: r.ok,
      error: r.ok ? null : r.error,
      consoleErrors: r.consoleErrors,
      fontRequests: r.fontRequests,
      file: r.file,
    }))],
  };
  await fsp.writeFile(path.join(args.out, 'manifest.json'), JSON.stringify(manifest, null, 2));
  const seconds = ((Date.now() - started) / 1000).toFixed(0);
  console.log(`[done] ${manifest.captured}/${manifest.expected} captured in ${seconds} s, manifest at ${path.join(args.out, 'manifest.json')}`);
  if (failed.length) {
    console.error(`[done] ${failed.length} variant(s) failed:`);
    for (const f of failed) console.error(`  - ${f.file}: ${f.error}`);
    if (args.strict) process.exit(1);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
