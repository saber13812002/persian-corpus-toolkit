#!/bin/bash
# M9 watchdog: wait for the khamenei prod drain to finish (or die), then report state.
for i in $(seq 1 70); do
  sleep 60
  if ! pgrep -f 'scrape_khamenei.py --max 5000' >/dev/null; then
    echo "PROCESS-ENDED at t+${i}m"
    break
  fi
  P=$(curl -s http://127.0.0.1:5055/api/khamenei/crawl-status | python3 -c 'import json,sys; print(json.load(sys.stdin)["pending"])')
  T=$(curl -s http://127.0.0.1:5055/api/khamenei/crawl-status | python3 -c 'import json,sys; print(json.load(sys.stdin)["total"])')
  echo "t+${i}m pending=$P total=$T"
  if [ "$P" = "0" ]; then
    echo "PENDING-ZERO"
    break
  fi
done
echo '---final---'
tail -5 /tmp/pcm-ext07-m9-prod-drain.log
pgrep -f 'scrape_khamenei.py --max 5000' >/dev/null && echo ALIVE || echo PROC-GONE
echo '---status---'
curl -s http://127.0.0.1:5055/api/khamenei/crawl-status
echo
