import en from '~/locales/en'
import ko from '~/locales/ko'

const dicts: Record<string, any> = { en, ko }

export type Locale = 'en' | 'ko'

/**
 * Lightweight bilingual i18n.
 * UI strings come from the locale dictionaries; dynamic content (products/categories)
 * carries *_ko / *_en fields and is picked per locale with graceful fallback.
 */
export function useI18n() {
  const locale = useState<Locale>('locale', () => 'en')

  const t = (key: string, params?: Record<string, string | number>): string => {
    const resolve = (dict: any): any =>
      key.split('.').reduce((o, k) => (o == null ? undefined : o[k]), dict)
    let v = resolve(dicts[locale.value])
    if (typeof v !== 'string') v = resolve(dicts.en)
    if (typeof v !== 'string') return key
    if (params) {
      for (const [k, val] of Object.entries(params)) v = v.replace(new RegExp(`\\{${k}\\}`, 'g'), String(val))
    }
    return v
  }

  /** Pick the localized field of dynamic content: tr(product, 'title') -> title_en / title_ko */
  const tr = (obj: any, field: string): string => {
    if (!obj) return ''
    const key = `${field}_${locale.value}`
    const fallback = `${field}_en`
    const fallback2 = `${field}_ko`
    return obj[key] || obj[fallback] || obj[fallback2] || ''
  }

  const setLocale = (l: Locale) => {
    locale.value = l
    useCookie<Locale>('locale').value = l
    if (import.meta.client) document.documentElement.lang = l
  }

  return { locale, t, tr, setLocale }
}

export function useMoney() {
  const { locale } = useI18n()
  return (n: number | null | undefined): string =>
    new Intl.NumberFormat(locale.value === 'ko' ? 'ko-KR' : 'en-US', {
      style: 'currency',
      currency: 'KRW',
      maximumFractionDigits: 0
    }).format(Number(n || 0))
}
