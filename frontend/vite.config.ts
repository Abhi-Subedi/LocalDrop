import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { existsSync } from 'node:fs'

const DEV_BUILD_DIR = '/dist/development/'
const PROD_BUILD_DIR = '/dist/production/'

/**
 * Ship react-router's *production* build.
 *
 * react-router and react-router-dom 7.18 point every export condition at
 * `dist/development/`. There is no "production" condition, so an ordinary
 * production build silently bundles the development build: 366 KB of source,
 * plus dev-only warning and assertion branches that a user should never run.
 * `dist/production/` ships in the package; nothing in its map selects it.
 *
 * The id has to be rewritten *after* resolution. Two simpler approaches fail:
 *
 *  - aliasing to `react-router/dist/production/index.mjs` errors out, because
 *    that is not an exported subpath;
 *  - substituting the file's contents in `load` breaks the production file's own
 *    relative imports, which then resolve against the development directory.
 *
 * If a future react-router fixes its exports map, the resolved id no longer
 * contains `/dist/development/`, this returns null, and the correct build is
 * used — no cleanup required.
 */
function routerProductionBuild(): Plugin {
  return {
    name: 'localdrop:react-router-production-build',
    enforce: 'pre',
    apply: 'build',
    async resolveId(source, importer, options) {
      if (!/^react-router(-dom)?$/.test(source)) return null
      // skipSelf: resolve the package's own mapping, not this plugin's rewrite.
      const resolved = await this.resolve(source, importer, { ...options, skipSelf: true })
      if (!resolved?.id?.includes(DEV_BUILD_DIR)) return null

      const production = resolved.id.replace(DEV_BUILD_DIR, PROD_BUILD_DIR)
      if (!existsSync(production)) {
        // Upstream moved things. Fail loudly rather than quietly shipping the
        // development build again after an upgrade.
        this.error(
          `localdrop:react-router-production-build: expected a production build at ` +
            `${production}, and it is not there. This workaround is stale — check ` +
            `node_modules/react-router/dist after upgrading react-router.`
        )
      }
      return production
    },
  }
}

/**
 * Make the workaround above impossible to lose silently. The whole point is
 * that a development build is invisible in the output: the app still runs, it
 * is just larger and carries dev-only branches. A build-time assertion is the
 * only thing that turns that back into a visible failure.
 */
function assertNoDevelopmentBuilds(): Plugin {
  return {
    name: 'localdrop:assert-no-development-builds',
    apply: 'build',
    generateBundle(_options, bundle) {
      const offenders: string[] = []
      for (const [file, chunk] of Object.entries(bundle)) {
        if (chunk.type !== 'chunk') continue
        const dev = Object.keys(chunk.modules).filter((m) => m.includes(DEV_BUILD_DIR))
        if (dev.length) offenders.push(`${file}: ${dev.join(', ')}`)
      }
      if (offenders.length) {
        this.error(
          'A development build reached the bundle, which silently costs ~360 KB and ' +
            'ships dev-only code paths. Check the localdrop:react-router-production-build ' +
            `plugin:\n  ${offenders.join('\n  ')}`
        )
      }
    },
  }
}

export default defineConfig({
  plugins: [
    routerProductionBuild(),
    assertNoDevelopmentBuilds(),
    react(),
    tailwindcss(),
  ],

  define: {
    // Some dependencies branch on this at runtime. Vite sets it for application
    // code but not always for pre-bundled deps, which can ship a dev-only path.
    'process.env.NODE_ENV': JSON.stringify('production'),
  },

  server: {
    proxy: {
      '/api': { target: 'http://localhost:8080', changeOrigin: true },
    },
  },

  build: {
    // Emits into the Python package so the SPA ships inside the wheel and the
    // PyInstaller binary (see backend/src/localdrop/main.py SPA_DIST).
    outDir: '../backend/src/localdrop/static',
    emptyOutDir: true,
    target: 'es2022',
    sourcemap: false,
    reportCompressedSize: true,
    // A single chunk is deliberate: this is a small LAN app, and one extra
    // request on a phone's first load costs more than a parallel-download
    // saving. The service worker caches /assets/ immutably, so the hashed
    // filename is the only cache-busting needed.
    chunkSizeWarningLimit: 400,
  },
})
