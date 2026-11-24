export interface CheckoutIn {
  items: { slug: string; quantity: number }[]
  customer: {
    name: string
    email?: string
    phone: string
    address1: string
    address2?: string
    city?: string
    postal_code?: string
    memo?: string
  }
  payment_method: 'card' | 'bank'
  locale: string
}

export interface AdminProduct {
  id: number
  slug: string
  title_ko: string
  title_en: string | null
  desc_ko: string
  desc_en: string | null
  price_cost: number
  price_sell: number
  effective_margin_pct: number
  markup_override: number | null
  images: string[]
  status: string
  is_manual: boolean
  source_id: number | null
  source_name: string | null
  source_url: string | null
  category_id: number | null
  category: { slug: string; name_en: string; name_ko: string } | null
  stock_status: string
  rating: number
  reviews: number
  translation_status: string
  updated_at: string | null
}

export interface AdminSource {
  id: number
  name: string
  url: string
  category_hint: string
  products_hint: string
  contact: string
  notes: string
  paid_membership: boolean
  requires_cafe: boolean
  image_provided: boolean
  dropship_possible: boolean
  adapter: string
  config: { listing_url?: string; max_products?: number; max_pages?: number; category_id?: number | null }
  enabled: boolean
  status: string
  last_scraped_at: string | null
  last_error: string
  product_count: number
  category_id: number | null
}

export interface AdminOrder {
  id: number
  order_number: string
  customer_name: string
  email: string
  phone: string
  address1: string
  address2: string
  city: string
  postal_code: string
  memo: string
  status: string
  payment_method: string
  locale: string
  subtotal: number
  shipping: number
  total: number
  cost_total: number
  profit: number
  created_at: string | null
  items: {
    id: number
    title_ko: string
    title_en: string
    image: string
    unit_sell: number
    unit_cost: number
    quantity: number
  }[]
}

export interface ScrapeLogRow {
  id: number
  source_name: string
  trigger: string
  status: string
  new_products: number
  updated_products: number
  message: string
  started_at: string | null
}

export interface AdminCategory {
  id: number
  slug: string
  name_en: string
  name_ko: string
  markup_percent: number | null
  sort_order: number
  product_count: number
}
