export default defineNuxtConfig({
  compatibilityDate: '2025-07-01',
  devtools: { enabled: false },
  ssr: true,

  // Vercel: Nitro auto-selects the vercel preset there; elsewhere it stays node-server.
  // The scraper tool is the main page for now (the storefront remains at /products).
  routeRules: {
    '/': { redirect: { to: '/scraper', statusCode: 302 } }
  },

  devServer: {
    host: '0.0.0.0',
    port: 3000,
    // Keep the chokidar watcher away from the Python backend venv (inotify ENOSPC crash)
    watcher: {
      ignored: [
        '**/.venv/**',
        '**/mini-services/**',
        '**/.zscripts/**',
        '**/upload/**',
        '**/download/**',
        '**/legacy-next-backup/**',
        '**/data/**',
        '**/media/**'
      ]
    }
  },

  modules: ['@nuxtjs/tailwindcss', '@pinia/nuxt'],

  components: [{ path: '~/components', pathPrefix: false }],

  runtimeConfig: {
    // FastAPI backend URL used server-side and by the /api + /media proxies.
    // On Vercel set NUXT_API_INTERNAL=https://your-backend.example.com
    apiInternal: 'http://127.0.0.1:8000',
    public: {
      // Browser base for API calls. Default '/api' = same-origin Nitro proxy.
      // Optional: set NUXT_PUBLIC_API_BASE=https://your-backend.example.com/api to call the
      // backend directly (avoids Vercel's ~4.5 MB function body limit for big ZIP downloads/uploads).
      apiBase: '/api'
    }
  },

  tailwindcss: {
    cssPath: '~/assets/css/main.css',
    configPath: 'tailwind.config.ts'
  },

  app: {
    head: {
      // titleTemplate is set in app.vue (dynamic site name from Admin > Settings)
      htmlAttrs: { lang: 'en' },
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'description', content: 'Shopee - curated Korean wholesale finds, delivered to your door.' }
      ],
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
        {
          rel: 'stylesheet',
          href: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+KR:wght@400;500;700;800&display=swap'
        }
      ]
    }
  }
})
