# 매일 아침 8시 자동 업데이트 (Daily 08:00 KST auto-update)

라이브 사이트(https://krw-watcher.tail3e31a9.ts.net/)를 매일 아침 8시(KST)에
자동으로 업데이트한다 — 위원회 예측 사이클 + 당일 브리핑. 8시에 실행되지
못하면(서버 오프라인, 러너 지연 등) **가능해지는 즉시** 재시도한다. 모든
경로가 멱등이라 레이어가 겹쳐 실행돼도 오늘 이미 업데이트됐으면 no-op으로
끝난다 — AI 토큰이 이중으로 소모되지 않는다.

## 3중 레이어

| 레이어 | 어디서 도나 | 언제 | 파일/설정 |
|---|---|---|---|
| ① GitHub Actions | GitHub 러너 (항상 켜져 있음) | 08:00 KST 크론 + 09~14시 KST 매시 재시도 스윕 (신선하면 no-op) | `.github/workflows/daily-update.yml` (master) |
| ② Claude 클라우드 Routine | Claude Code 클라우드 (모바일/PC 무관) | 08:30 KST — ①의 오늘 실행이 성공했는지 검증, 없거나 실패면 직접 dispatch·재시도, 최종 실패 시에만 푸시 알림 | claude.ai/code → Routines → "krw-watcher 매일 8시 업데이트 감시견" |
| ③ PC 폴백 | 사용자 Windows PC | 08:00, 놓치면 부팅/절전 해제 직후 즉시 (`StartWhenAvailable`) | `scheduler/daily_update.ps1` + `register_daily_update.ps1` |

①·②는 사용자 기기가 꺼져 있어도 동작한다(사이트 호스트가 살아 있는 한).
③은 사이트 호스트가 이 PC 자신이라 함께 잠들어 있던 경우 — PC가 깨어나는
순간 바로 업데이트를 돌리는 안전망이다.

## 각 실행이 하는 일

1. `GET /health` 재시도로 사이트 도달 확인 (깨우기).
2. 신선도 검사 — `/api/forecast`의 `created_kst`가 오늘 07:00(KST) 이후면
   사이클 스킵, `/api/briefing/latest`의 `brief.date`가 오늘이면 브리핑 스킵.
3. 필요 시 `POST /api/cycle` (위원회 예측, 비동기) 후 시작/완료 확인.
4. 필요 시 `POST /api/briefing/generate` (당일 브리핑, 블로킹).

## 설정 방법

**① GitHub Actions** — master에 머지되어 있으므로 크론이 자동 동작 중.
수동 실행: *Actions → Daily 8AM KST auto-update → Run workflow*
(url / force 입력 가능).

**② Claude Routine** — 등록되어 있음. claude.ai/code 의 Routines 목록에서
확인/일시정지/삭제 가능.

**③ PC 폴백** — 관리자 PowerShell에서 한 번만:

```powershell
powershell -ExecutionPolicy Bypass -File scheduler\register_daily_update.ps1
```

즉시 테스트:

```powershell
Start-ScheduledTask -TaskName "KRW-Watcher Daily 8AM Update"
Get-Content C:\Users\andul\fed-watcher\logs\daily_update.log -Tail 20
```
