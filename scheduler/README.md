# 매일 아침 8시까지 자동 업데이트 완료 (Daily update done by 08:00 KST)

krw-watcher의 위원회 예측 사이클 + 당일 브리핑이 매일 아침 **8시(KST)까지
완료**되어 있도록 하는 시스템의 전체 지도. 사이클 20~35분 + 브리핑 5~15분이
걸리므로 06:40~06:50에 기동한다. 제때 실행되지 못하면(서버 오프라인, 러너
지연 등) **가능해지는 즉시** 재시도한다. 모든 레이어가 멱등(오늘 아침 결과가
이미 있으면 no-op)이라 겹쳐 실행돼도 AI 토큰이 이중으로 소모되지 않는다.

인스턴스는 두 개이고 둘 다 매일 아침 업데이트된다:

- **클라우드**: https://krw-watcher.onrender.com — Render 무료 티어, 24/7.
  **PC·휴대폰이 모두 꺼져 있어도 여기는 항상 8시까지 업데이트 완료.**
- **PC(Tailscale Funnel)**: https://krw-watcher.tail3e31a9.ts.net — PC가
  켜져 있으면 같이 업데이트, 꺼져 있으면 켜지는 대로 즉시 따라잡음.

## 레이어 지도

| 레이어 | 대상 | 언제 (KST) | 파일/설정 |
|---|---|---|---|
| 앱 내부 스케줄러 | 클라우드 | 06:40 사이클 · 07:30 브리핑 (자체 실행) | Render 환경변수 `CYCLE_HOURS_KST=6,13,20` |
| GitHub Actions `daily-update-krw.yml` | 클라우드 | 07:50 검증·복구 + 09:50/12:50 스윕 | `.github/workflows/daily-update-krw.yml` |
| GitHub Actions `daily-update.yml` | PC 퍼널 | 06:40 본 실행 + 07:40~14:40 매시 스윕 | `.github/workflows/daily-update.yml` |
| Claude 클라우드 Routine (감시견) | 전부 (krw 클라우드·PC, Fed 클라우드, KOSPI PC) | 08:10 — `daily-update-krw/-fed/-kospi/daily-update.yml`의 오늘 성공 여부 검증, 없으면 직접 dispatch·재시도, 조치·이상 시에만 푸시 알림 | claude.ai/code → Routines → "아침 8시 업데이트 통합 감시견 (08:10 KST, 4개 대상)" |
| PC 로컬 폴백 | PC 퍼널 | 06:45, 놓치면 부팅/절전 해제 즉시 (`StartWhenAvailable`) | `scheduler/daily_update_krw.ps1` + `register_daily_update_krw.ps1` |

클라우드 레이어들은 사용자 기기가 전부 꺼져 있어도 동작한다. PC 퍼널
사이트는 PC가 꺼져 있으면 대상 자체가 없으므로 매시 스윕 + 로컬 폴백이
PC가 켜지는 순간 따라잡는다.

(참고: `scheduler/daily_update.ps1`은 별개인 **Fed-Watcher** 백엔드의
아침 wake-up 폴백, `daily-wakeup.yml`은 그 클라우드 버전이다.)

## 각 실행이 하는 일

1. `GET /health` 재시도로 사이트를 깨우고 도달 확인.
2. 신선도 검사 — 오늘(KST) 06:00 이후 완료된 예측이 있으면 사이클 스킵,
   오늘자 브리핑이 있으면 브리핑 스킵. 두 빌드의 API 차이(포트는
   `created_kst`, 원본 PC 앱은 `/api/agents`의 `run.completed_at`)와
   시간대(naive KST vs UTC)를 모두 처리한다.
3. 필요 시 `POST /api/cycle` → 시작 감지(activity seq) → 완료 폴링.
4. 필요 시 `POST /api/briefing/generate` → 오늘 날짜 브리핑 재검증.

## 설정 방법

**GitHub Actions** — master에 있으므로 크론 자동 동작. 수동 실행:
*Actions → 해당 워크플로우 → Run workflow*.

**Claude Routine** — 등록되어 있음. claude.ai/code 의 Routines 목록에서
확인/일시정지/삭제 가능.

**PC 로컬 폴백** — 관리자 PowerShell에서 한 번만:

```powershell
powershell -ExecutionPolicy Bypass -File scheduler\register_daily_update_krw.ps1
```

즉시 테스트:

```powershell
Start-ScheduledTask -TaskName "KRW-Watcher Daily 8AM Update"
Get-Content C:\Users\andul\fed-watcher\logs\daily_update_krw.log -Tail 20
```
