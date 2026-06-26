#!/bin/bash
# 🤖 YJCryptoNews - Hourly cycle (24/7): fetch fresh → AI filter → translate → publish BEST article
# Token-efficient: 1 article/hour = 1 translation = 24/day max

cd /usr/local/lib/YJCryptoNews || exit 1

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Graceful kill previous
kill_previous() {
    local prev_pids="$1"
    for pid in $prev_pids; do
        kill -TERM $pid 2>/dev/null
    done
    for i in 1 2 3 4 5; do
        sleep 1
        local alive=0
        for pid in $prev_pids; do
            if kill -0 $pid 2>/dev/null; then
                alive=1; break
            fi
        done
        [ $alive -eq 0 ] && return 0
    done
    for pid in $prev_pids; do
        if kill -0 $pid 2>/dev/null; then
            echo "[$(date '+%H:%M:%S')] 🔪 Force kill $pid"
            kill -9 $pid 2>/dev/null
        fi
    done
}

PREV_PID=$(pgrep -f "python.*bot.py hourly" | grep -v "$$" | head -5)
if [ -n "$PREV_PID" ]; then
    echo "[$(date '+%H:%M:%S')] ⚠️ Killing previous stuck hourly: $PREV_PID"
    kill_previous "$PREV_PID"
fi

echo "[$(date '+%H:%M:%S')] ⏰ Starting hourly cycle (timeout: 15min)"
timeout 900 python bot.py hourly
EXIT=$?
if [ $EXIT -eq 124 ]; then
    echo "[$(date '+%H:%M:%S')] ⛔ Hourly cycle TIMEOUT"
elif [ $EXIT -ne 0 ]; then
    echo "[$(date '+%H:%M:%S')] ⚠️ Hourly cycle exit $EXIT"
else
    echo "[$(date '+%H:%M:%S')] ✅ Hourly cycle completed"
fi
exit $EXIT