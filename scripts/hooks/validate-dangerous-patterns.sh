#!/usr/bin/env bash
# PreToolUse(Bash) 위험 패턴 차단 훅
# stdin으로 JSON을 받아 위험한 명령어 패턴을 감지하면 exit 2로 차단한다.

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")

if [[ -z "$COMMAND" ]]; then
  exit 0
fi

# 1) 홈/루트 재귀 glob 탐색 차단
if echo "$COMMAND" | grep -qE "glob\(['\"]/(Users)?/?\*\*"; then
  echo "차단: 홈 또는 루트 디렉토리 재귀 glob 탐색이 감지되었습니다." >&2
  exit 2
fi

# 2) os.walk로 홈/루트 탐색 차단
if echo "$COMMAND" | grep -qE "os\.walk\s*\(\s*(Path\.home\(\)|['\"]/?['\"]|['\"]/Users['\"])"; then
  echo "차단: os.walk를 사용한 홈/루트 디렉토리 탐색이 감지되었습니다." >&2
  exit 2
fi

# 3) find로 프로젝트 외부 탐색 차단
if echo "$COMMAND" | grep -qE "find\s+(~|/|/Users)\s+.*-name"; then
  echo "차단: find를 사용한 프로젝트 외부 디렉토리 탐색이 감지되었습니다." >&2
  exit 2
fi

# 4) .env 파일 직접 출력 차단
if echo "$COMMAND" | grep -qE "cat\s+.*\.env(\s|$)"; then
  echo "차단: .env 파일 직접 출력이 감지되었습니다." >&2
  exit 2
fi

# 5) curl/wget으로 시크릿 전송 차단 (토큰 포함 URL 패턴)
if echo "$COMMAND" | grep -qE "(curl|wget)\s+.*[?&](token|key|secret|password|api_key)="; then
  echo "차단: curl/wget을 통한 시크릿 전송이 감지되었습니다." >&2
  exit 2
fi

exit 0
