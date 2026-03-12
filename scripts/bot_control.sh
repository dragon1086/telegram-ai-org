#!/bin/bash
# PM봇 시작/종료/재시작 관리 (PID 파일 방식)

PID_FILE="$HOME/.ai-org/pm_bot.pid"
LOG_FILE="$HOME/.ai-org/pm_bot.log"
BOT_DIR="$HOME/telegram-ai-org"

start() {
    # 기존 프로세스 확인
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            echo "이미 실행 중 (PID: $OLD_PID)"
            return 0
        fi
    fi

    cd "$BOT_DIR"
    nohup .venv/bin/python3 -u main.py > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "✅ PM봇 시작 (PID: $(cat $PID_FILE))"
}

stop() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            kill -9 "$PID" 2>/dev/null
            echo "✅ PM봇 종료 (PID: $PID)"
        fi
        rm -f "$PID_FILE"
    else
        pkill -9 -if "python.*main.py" 2>/dev/null
    fi
    # 항상 잔여 좀비도 제거
    pkill -9 -if "python.*main.py" 2>/dev/null; true
    sleep 2
}

case "$1" in
    start)   start ;;
    stop)    stop ;;
    restart) stop && start ;;
    status)
        if [ -f "$PID_FILE" ] && ps -p "$(cat $PID_FILE)" > /dev/null 2>&1; then
            echo "✅ 실행 중 (PID: $(cat $PID_FILE))"
        else
            echo "❌ 정지됨"
        fi
        ;;
    *)
        echo "사용법: $0 {start|stop|restart|status}"
        ;;
esac
