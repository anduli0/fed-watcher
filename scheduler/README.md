# 매일 아침 8시까지 자동 업데이트 완료 (Daily update done by 08:00 KST)

라이브 사이트(https://krw-watcher.tail3e31a9.ts.net/)의 위원회 예측 사이클
+ 당일 브리핑이 매일 아침 **8시(KST)까지 완료**되어 있도록 한다. 사이클이
20~35분, 브리핑이 5~15분 걸리므로 **06:45 KST에 기동**한다. 제때 실행되지
못하면(서버 오프라인, 러너 지연 등) **가능해지는 즉시** 재시도한다. 모든
경로가 멱등이라 레이어가 겹쳐 실행돼도 오늘 아침 결과가 이미 있으면
no-op — AI 토큰이 이중으로 소모되지 않는다.

## 3중 레이어

| 레이어 | 어디서 도나 | 언제 | 파일/설정 |
|---|---|---|---|
| ① GitHub Actions | GitHub 러너 (항상 켜져 있음, 휴대폰/PC 불필요) | 06:45 KST 본 실행 + 07:30 / 08:00 / 09~14시 매시 재시도 스윕 (신선하면 no-op) | `.github/workflows/daily-update.yml` (master) |
| ② Claude 클라우드 Routine | Claude Code 클라우드 (휴대폰/PC 불필요) | 08:30 KST — ①의 오늘 실행이 성공했는지 검증, 없거나 실패면 직접 dispatch·재시도, 최종 실패 시에만 푸시 알림 | claude.ai/code → Routines → "krw-watcher 매일 8시 업데이트 감시견" |
| ③ PC 폴백 | 사용자 Windows PC | 06:45, 놓치면 부팅/절전 해제 직후 즉시 (`StartWhenAvailable`) | `scheduler/daily_update.ps1` + `register_daily_update.ps1` |

①·②는 클라우드에서 돌므로 휴대폰과 PC가 모두 꺼져 있어도 실행된다.
단, **사이트 서버 자체가 꺼져 있으면** (사이트가 이 PC에서 호스팅되는 경우
PC가 꺼져 있으면) 업데이트할 대상이 없으므로 ①이 매시 재시도하며 대기하고,
서버가 살아나는 즉시 그 시각에 업데이트된다. ③은 그 경우를 위한 안전망 —
PC가 깨어나는 순간 로컬에서 바로 업데이트를 돌린다.

## 각 실행이 하는 일

1. `GET /health` 재시도로 사이트 도달 확인 (깨우기).
2. 신선도 검사 — `/api/agents`의 `run.completed_at`이 오늘 06:30(KST) 이후면
   사이클 스킵, `/api/briefing/latest`의 `brief.date`가 오늘이면 브리핑 스킵.
   (라이브 빌드의 `/api/forecast`는 `created_kst`를 노출하지 않으므로
   `run.completed_at`/`run.id`가 유일하게 신뢰할 수 있는 신호다.)
3. 필요 시 `POST /api/cycle` (위원회 예측, 비동기) 후 `run.id`가 바뀔 때까지
   폴링해 **완료**를 확인.
4. 필요 시 `POST /api/briefing/generate` (당일 브리핑, 블로킹) 후
   `brief.date == 오늘` 재검증.

## 설정 방법

**① GitHub Actions** — master에 머지되면 크론이 자동 동작.
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
