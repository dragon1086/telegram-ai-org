# gemini-image-gen — Gotchas

## Gotcha 1: 이미지 생성 모델은 텍스트 모델과 다른 엔드포인트

**상황**: `gemini-2.5-flash` 모델로 이미지 생성 시도
**증상**: 텍스트 응답만 반환, 이미지 없음
**해결**: 이미지 생성 전용 모델 사용: `gemini-2.5-flash-preview-image-generation`
```bash
gemini models list  # 사용 가능한 이미지 모델 확인
```

## Gotcha 2: API Key 환경변수와 OAuth 충돌

**상황**: `.env`에 `GOOGLE_API_KEY` 설정되어 있는 상태에서 gemini CLI 실행
**증상**: OAuth 인증 무시, API Key로 시도 → 인증 실패 또는 quota 초과
**해결**: GeminiCLIRunner는 subprocess 환경에서 `GEMINI_API_KEY`, `GOOGLE_API_KEY`를 자동 제거함. 별도 처리 불필요.

## Gotcha 3: Preview 모델 불안정

**상황**: 이미지 생성 모델이 Preview 단계
**증상**: 가끔 빈 응답, 타임아웃, 모델명 변경
**해결**:
- `GEMINI_CLI_DEFAULT_TIMEOUT_SEC=300` 으로 늘리기
- `gemini models list` 로 최신 이미지 모델명 확인
- 실패 시 재시도 로직 추가

## Gotcha 4: base64 이미지 데이터 크기

**상황**: 고해상도 이미지 생성 시 응답이 매우 큼
**증상**: JSON 파싱 메모리 오류, 느린 응답
**해결**: 이미지 크기를 512x512 이하로 요청하거나, streaming 방식 사용 고려.

## Gotcha 5: Telegram 이미지 전송 크기 제한

**상황**: 생성된 이미지가 10MB 초과
**증상**: Telegram API 413 오류
**해결**: PIL/Pillow로 리사이즈 후 전송
```python
from PIL import Image
img = Image.open(path)
img.thumbnail((2048, 2048))
img.save(path)
```
