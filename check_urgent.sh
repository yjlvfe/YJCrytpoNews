#!/bin/bash
# 🚨 YJCryptoNews - Breaking check every 5min: 11+ sources SAME STORY + high market impact = publish ALL
# Strict: semantic similarity >= 0.75, market impact >= 0.5, not published in 48h

cd /usr/local/lib/YJCryptoNews || exit 1

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

kill_previous() {
    local prev_pids="$1"
    for pid in $prev_pids; do kill -TERM $pid 2>/dev/null; done
    for i in 1 2 3 4 5; do
        sleep 1; local alive=0
        for pid in $prev_pids; do if kill -0 $pid 2>/dev/null; then alive=1; break; fi; done
        [ $alive -eq 0 ] && return 0
    done
    for pid in $prev_pids; do if kill -0 $pid 2>/dev/null; then kill -9 $pid 2>/dev/null; fi; done
}

PREV_PID=$(pgrep -f "python.*bot.py breaking_check" | head -5)
if [ -n "$PREV_PID" ]; then
    echo "[$(date '+%H:%M:%S')] ⚠️ Killing previous stuck breaking check: $PREV_PID"
    kill_previous "$PREV_PID"
fi

echo "[$(date '+%H:%M:%S')] 🚨 Breaking check (strict: 11+ sources same story)"
timeout 180 python bot.py breaking_check
EXIT=$?
if [ $EXIT -eq 124 ]; then
    echo "[$(date '+%H:%M:%S')] ⛔ Breaking check TIMEOUT"
elif [ $EXIT -ne 0 ]; then
    echo "[$(date '+%H:%M:%S')] ⚠️ Breaking check exit $EXIT"
else
    echo "[$(date '+%H:%M:%S')] ✅ Breaking check completed"
fi
exit $EXIT