#!/bin/bash
# Start both services if they are not already healthy.
cd /home/z/my-project

# Backend (FastAPI on :8000)
if ! curl -sf -o /dev/null http://127.0.0.1:8000/api/health; then
  setsid nohup mini-services/api/start.sh > /tmp/api.log 2>&1 < /dev/null &
  for i in $(seq 1 30); do
    curl -sf -o /dev/null http://127.0.0.1:8000/api/health && break
    sleep 1
  done
fi

# Frontend (Nuxt on :3000)
if ! curl -sf -o /dev/null http://127.0.0.1:3000/; then
  setsid nohup node node_modules/.bin/nuxt dev --host 0.0.0.0 --port 3000 > /tmp/nuxt-dev.log 2>&1 < /dev/null &
  for i in $(seq 1 60); do
    curl -sf -o /dev/null http://127.0.0.1:3000/ && break
    sleep 2
  done
fi

echo "api: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/health)"
echo "nuxt: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/)"
