#!/bin/bash
# One-shot E2E verification: install deps, boot backend+frontend, browser-test the golden paths.
set -u
cd /home/z/my-project

LOG=/home/z/my-project/.zscripts/verify.log
SHOTS=/home/z/my-project/.zscripts/shots
mkdir -p "$SHOTS"
: > "$LOG"

step() { echo "=== $1 ===" | tee -a "$LOG"; }

step "0. clean ports (kill leftovers from previous runs)"
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "nuxt dev" 2>/dev/null || true
pkill -f "bun run dev" 2>/dev/null || true
sleep 2
for port in 3000 8000; do
  (curl -s --max-time 1 "http://127.0.0.1:$port/" > /dev/null 2>&1) && echo "port $port still busy!" || echo "port $port free"
done

step "1. bun install (root nuxt deps)"
if [ ! -d node_modules/nuxt ]; then
  bun install >> "$LOG" 2>&1 || { echo "BUN INSTALL FAILED"; tail -30 "$LOG"; exit 1; }
fi
echo "nuxt: $(ls node_modules/nuxt/package.json >/dev/null 2>&1 && echo present || echo MISSING)"
echo "tailwind module: $(ls node_modules/@nuxtjs/tailwindcss/package.json >/dev/null 2>&1 && echo present || echo MISSING)"

step "2. start FastAPI :8000"
cd /home/z/my-project/mini-services/api
setsid nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 > /home/z/my-project/.zscripts/api.log 2>&1 < /dev/null &
for i in $(seq 1 30); do curl -s -o /dev/null http://127.0.0.1:8000/api/health && break; sleep 1; done
curl -s http://127.0.0.1:8000/api/health || { echo "API FAILED"; tail -20 /home/z/my-project/.zscripts/api.log; exit 1; }
echo " api ok"

step "3. start Nuxt dev :3000"
cd /home/z/my-project
setsid nohup bun run dev > /home/z/my-project/dev.log 2>&1 < /dev/null &
for i in $(seq 1 90); do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 4 http://127.0.0.1:3000/ 2>/dev/null)
  [ "$code" = "200" ] && break
  sleep 2
done
curl -s -o /dev/null -w "home: %{http_code}\n" http://127.0.0.1:3000/

step "4. API through Nitro proxy"
curl -s "http://127.0.0.1:3000/api/health" && echo ""
curl -s "http://127.0.0.1:3000/api/catalog/products?per_page=2" | head -c 200; echo ""
curl -s -o /dev/null -w "media: %{http_code} %{content_type}\n" "http://127.0.0.1:3000/media/seed/$(ls /home/z/my-project/mini-services/api/media/seed | head -1)"

step "5. page HTTP codes"
for p in / /products /cart /checkout /admin /admin/login /admin/products /admin/sources /admin/scraping /admin/orders /admin/finance /admin/settings; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 "http://127.0.0.1:3000$p")
  echo "$p -> $code"
done

step "6. browser walkthrough"
B="agent-browser --session shopee-verify"
$B set viewport 1440 900 >> "$LOG" 2>&1

$B open http://127.0.0.1:3000/ >> "$LOG" 2>&1 && $B wait --load networkidle >> "$LOG" 2>&1
$B screenshot "$SHOTS/01-home.png" >> "$LOG" 2>&1
$B get title

# switch locale to KO then back
$B find text "한국어" click >> "$LOG" 2>&1 && sleep 1
$B screenshot "$SHOTS/02-home-ko.png" >> "$LOG" 2>&1
$B find text "EN" click >> "$LOG" 2>&1 && sleep 1

# product listing + detail
$B open "http://127.0.0.1:3000/products" >> "$LOG" 2>&1 && $B wait --load networkidle >> "$LOG" 2>&1
$B screenshot "$SHOTS/03-products.png" >> "$LOG" 2>&1
SLUG=$(curl -s "http://127.0.0.1:3000/api/catalog/products?per_page=1" | python3 -c "import sys,json;print(json.load(sys.stdin)['items'][0]['slug'])")
echo "using slug: $SLUG"
$B open "http://127.0.0.1:3000/products/$SLUG" >> "$LOG" 2>&1 && $B wait --load networkidle >> "$LOG" 2>&1
$B screenshot "$SHOTS/04-product.png" >> "$LOG" 2>&1

# add to cart via UI
$B find text "Add to cart" click >> "$LOG" 2>&1 && sleep 1
$B open http://127.0.0.1:3000/cart >> "$LOG" 2>&1 && $B wait --load networkidle >> "$LOG" 2>&1
$B screenshot "$SHOTS/05-cart.png" >> "$LOG" 2>&1

# checkout
$B open http://127.0.0.1:3000/checkout >> "$LOG" 2>&1 && $B wait --load networkidle >> "$LOG" 2>&1
$B find label "Full name" fill "Sora Lee" >> "$LOG" 2>&1
$B find label "Phone" fill "010-8888-7777" >> "$LOG" 2>&1
$B find label "Address line 1" fill "42 Jongno-gu" >> "$LOG" 2>&1
$B find text "Place order" click >> "$LOG" 2>&1
sleep 3
$B get url
$B screenshot "$SHOTS/06-order.png" >> "$LOG" 2>&1

# admin login
$B open http://127.0.0.1:3000/admin/login >> "$LOG" 2>&1 && $B wait --load networkidle >> "$LOG" 2>&1
$B find label "Email" fill "admin@shopee.kr" >> "$LOG" 2>&1
$B find label "Password" fill "admin1234" >> "$LOG" 2>&1
$B find role button click --name "Sign in" >> "$LOG" 2>&1
sleep 3
$B get url
$B screenshot "$SHOTS/07-admin-dashboard.png" >> "$LOG" 2>&1

for p in products sources scraping orders finance settings; do
  $B open "http://127.0.0.1:3000/admin/$p" >> "$LOG" 2>&1 && $B wait --load networkidle >> "$LOG" 2>&1
  $B screenshot "$SHOTS/08-admin-$p.png" >> "$LOG" 2>&1
done

$B errors | head -20
$B close >> "$LOG" 2>&1

step "7. dev.log tail"
tail -12 /home/z/my-project/dev.log
echo "DONE"
