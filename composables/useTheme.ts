/**
 * Runtime theme engine.
 * Settings come from the public /api/catalog/theme endpoint (managed in
 * Admin > Settings > Theme / Typography). The palette is derived from a single
 * brand color + accent color, written to CSS variables, and picked up by
 * tailwind (brand-*, ink-*, accent-*, radius, fonts).
 */

export interface ThemeConfig {
  primary: string
  accent: string
  radius: number
  darkDefault: boolean
}
export interface FontsConfig {
  family: string
  heading: string
  baseSize: number
  headingWeight: number
}
export interface ThemeSettingsPayload {
  site_name: string
  theme: ThemeConfig
  fonts: FontsConfig
}

export const FONT_OPTIONS: { name: string; system?: boolean }[] = [
  { name: 'Inter' },
  { name: 'Noto Sans KR' },
  { name: 'Noto Serif KR' },
  { name: 'Nanum Gothic' },
  { name: 'Poppins' },
  { name: 'Roboto' },
  { name: 'Nunito' },
  { name: 'Playfair Display' },
  { name: 'Merriweather' },
  { name: 'JetBrains Mono' },
  { name: 'System UI', system: true },
  { name: 'Georgia', system: true }
]

export const THEME_PRESETS: { name: string; primary: string; accent: string }[] = [
  { name: 'Shopee Orange', primary: '#EA580C', accent: '#F59E0B' },
  { name: 'Ocean Teal', primary: '#0D9488', accent: '#F59E0B' },
  { name: 'Royal Purple', primary: '#7C3AED', accent: '#EC4899' },
  { name: 'Forest Green', primary: '#16A34A', accent: '#F97316' },
  { name: 'Classic Blue', primary: '#2563EB', accent: '#F59E0B' },
  { name: 'Rose Red', primary: '#E11D48', accent: '#FB923C' },
  { name: 'Midnight Slate', primary: '#334155', accent: '#0EA5E9' },
  { name: 'Hot Pink', primary: '#DB2777', accent: '#8B5CF6' }
]

// ---------- color helpers ----------

function clamp(v: number, min = 0, max = 1): number {
  return Math.min(max, Math.max(min, v))
}

function hexToRgb(hex: string): [number, number, number] {
  let h = (hex || '').replace('#', '').trim()
  if (h.length === 3) h = h.split('').map((c) => c + c).join('')
  const n = parseInt(h || 'EA580C', 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function rgbToHex(r: number, g: number, b: number): string {
  const c = (v: number) => Math.round(clamp(v, 0, 255)).toString(16).padStart(2, '0')
  return `#${c(r)}${c(g)}${c(b)}`
}

function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255; g /= 255; b /= 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  let h = 0
  const l = (max + min) / 2
  const d = max - min
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1))
  if (d !== 0) {
    if (max === r) h = ((g - b) / d) % 6
    else if (max === g) h = (b - r) / d + 2
    else h = (r - g) / d + 4
  }
  h = (h * 60 + 360) % 360
  return [h, s, l]
}

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  h = ((h % 360) + 360) % 360 / 360
  const f = (n: number) => {
    const k = (n + h * 12) % 12
    const a = s * Math.min(l, 1 - l)
    return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))
  }
  return [f(0) * 255, f(8) * 255, f(4) * 255]
}

/** Shift lightness / saturation of a hex color. dl: -1..1, sMul: saturation multiplier. */
function shift(hex: string, dl: number, sMul = 1): string {
  const [r, g, b] = hexToRgb(hex)
  const [h, s, l] = rgbToHsl(r, g, b)
  const [nr, ng, nb] = hslToRgb(h, clamp(s * sMul), clamp(l + dl))
  return rgbToHex(nr, ng, nb)
}

/** Derive the full brand palette anchored on the given primary color (used as the 600 shade). */
export function deriveBrand(primary: string): Record<string, string> {
  return {
    '50': shift(primary, 0.66, 0.30),
    '100': shift(primary, 0.55, 0.42),
    '200': shift(primary, 0.42, 0.60),
    '300': shift(primary, 0.30, 0.80),
    '400': shift(primary, 0.15, 0.95),
    '500': shift(primary, 0.05, 1),
    '600': primary,
    '700': shift(primary, -0.10, 1),
    '800': shift(primary, -0.20, 0.95),
    '900': shift(primary, -0.30, 0.90)
  }
}

export function deriveAccent(accent: string): Record<string, string> {
  return {
    '50': shift(accent, 0.64, 0.3),
    '100': shift(accent, 0.52, 0.45),
    '200': shift(accent, 0.40, 0.6),
    '300': shift(accent, 0.28, 0.8),
    '400': shift(accent, 0.14, 0.95),
    '500': shift(accent, 0.05, 1),
    '600': accent,
    '700': shift(accent, -0.10, 1),
    '800': shift(accent, -0.20, 0.95),
    '900': shift(accent, -0.30, 0.9)
  }
}

const INK_LIGHT: Record<string, string> = {
  '50': '248 250 252', '100': '241 245 249', '200': '226 232 240', '300': '203 213 225', '400': '148 163 184',
  '500': '100 116 139', '600': '71 85 105', '700': '51 65 85', '800': '30 41 59', '900': '15 23 42'
}
const INK_DARK: Record<string, string> = {
  '50': '23 28 36', '100': '31 38 48', '200': '42 50 64', '300': '59 70 86', '400': '133 147 166',
  '500': '154 167 184', '600': '179 190 203', '700': '201 210 220', '800': '220 227 234', '900': '238 242 246'
}

function hexToTriplet(hex: string): string {
  const [r, g, b] = hexToRgb(hex)
  return `${r} ${g} ${b}`
}

export function fontStack(family: string): string {
  const f = (family || 'Inter').trim()
  if (f === 'System UI') return 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif'
  if (f === 'Georgia') return 'Georgia, "Times New Roman", serif'
  return `"${f}", 'Noto Sans KR', ui-sans-serif, system-ui, sans-serif`
}

export function googleFontsHref(families: string[]): string | null {
  const list = Array.from(new Set(families.filter((f) => f && f !== 'System UI' && f !== 'Georgia')))
  if (!list.length) return null
  const q = list.map((f) => `family=${f.replace(/ /g, '+')}:wght@400;500;600;700;800`).join('&')
  return `https://fonts.googleapis.com/css2?${q}&display=swap`
}

const shadeKeys = ['50', '100', '200', '300', '400', '500', '600', '700', '800', '900']

/** Build the full :root CSS variables block for the given settings + color mode. */
export function buildVarsCss(theme: ThemeConfig, fonts: FontsConfig, mode: 'light' | 'dark'): string {
  const brand = deriveBrand(theme.primary || '#EA580C')
  const accent = deriveAccent(theme.accent || '#F59E0B')
  const r = clamp(Number(theme.radius ?? 12), 0, 32)
  const lines: string[] = []
  for (const k of shadeKeys) lines.push(`--brand-${k}: ${hexToTriplet(brand[k])};`)
  for (const k of shadeKeys) lines.push(`--accent-${k}: ${hexToTriplet(accent[k])};`)
  lines.push(`--c-surface: ${mode === 'dark' ? '19 25 34' : '255 255 255'};`)
  lines.push(`--c-bg: ${mode === 'dark' ? '12 16 23' : '255 255 255'};`)
  lines.push(`--c-inverse-bg: ${mode === 'dark' ? '13 20 32' : '15 23 42'};`)
  lines.push(`--radius-sm: ${Math.max(2, r * 0.5)}px;`)
  lines.push(`--radius-md: ${Math.max(3, r * 0.75)}px;`)
  lines.push(`--radius-lg: ${r}px;`)
  lines.push(`--radius-xl: ${r + 4}px;`)
  lines.push(`--radius-2xl: ${r + 8}px;`)
  lines.push(`--radius-3xl: ${r + 12}px;`)
  lines.push(`--font-body: ${fontStack(fonts.family)};`)
  lines.push(`--font-heading: ${fontStack(fonts.heading)};`)
  lines.push(`--heading-weight: ${fonts.headingWeight || 800};`)
  const ink = mode === 'dark' ? INK_DARK : INK_LIGHT
  for (const k of shadeKeys) lines.push(`--ink-${k}: ${ink[k]};`)
  // html:root keeps a slightly higher specificity than the :root defaults in
  // the compiled tailwind stylesheet, so admin settings always win there.
  return `html:root{${lines.join('')}}`
}

const DEFAULT_SETTINGS: ThemeSettingsPayload = {
  site_name: 'Shopee',
  theme: { primary: '#EA580C', accent: '#F59E0B', radius: 12, darkDefault: false },
  fonts: { family: 'Inter', heading: 'Inter', baseSize: 16, headingWeight: 800 }
}

export function useTheme() {
  const settings = useState<ThemeSettingsPayload>('themeSettings', () => DEFAULT_SETTINGS)
  const modeCookie = useCookie<'light' | 'dark' | null>('shopee_mode')
  const mode = useState<'light' | 'dark'>('colorMode', () => {
    if (modeCookie.value === 'dark' || modeCookie.value === 'light') return modeCookie.value
    return settings.value.theme.darkDefault ? 'dark' : 'light'
  })

  const setMode = (m: 'light' | 'dark') => {
    mode.value = m
    modeCookie.value = m
  }
  const toggleMode = () => setMode(mode.value === 'dark' ? 'light' : 'dark')

  const varsCss = computed(() => buildVarsCss(settings.value.theme, settings.value.fonts, mode.value))
  const fontsHref = computed(() => googleFontsHref([settings.value.fonts.family, settings.value.fonts.heading]))
  const siteName = computed(() => settings.value.site_name || 'Shopee')

  if (import.meta.client) {
    watchEffect(() => {
      document.documentElement.dataset.mode = mode.value
    })
  }

  return { settings, mode, setMode, toggleMode, varsCss, fontsHref, siteName }
}

/** Fetch theme settings once (server or client) and keep them in state. */
export async function loadThemeSettings() {
  // All composable calls happen synchronously (valid Nuxt context):
  // state handles are captured first, only the fetch is awaited.
  const theme = useTheme()
  const api = useApi()
  const { data, error } = await useAsyncData<ThemeSettingsPayload>('theme-settings', async () => {
    try {
      return await api<ThemeSettingsPayload>('/catalog/theme')
    } catch {
      return DEFAULT_SETTINGS
    }
  })
  if (data.value) theme.settings.value = { ...DEFAULT_SETTINGS, ...data.value }
  if (error.value) theme.settings.value = DEFAULT_SETTINGS
  return theme
}
