# 매일 아침 8시 자동 업데이트 (Daily 08:00 KST auto-update)

라이브 사이트(https://krw-watcher.tail3e31a9.ts.net/)를 매일 아침 8시(KST)에
자동으로 업데이트한다 — 당일 브리핑 생성 + 예측 사이클 1회. 8시에 실행되지
못하면(러너 지연, PC 꺼짐 등) **가능해지는 즉시** 실행된다. 모든 경로가
멱등(idempotent)이라 여러 레이어가 겹쳐 실행돼도 오늘 이미 업데이트됐으면
그냥 통과한다 — AI 토큰이 이중으로 소모되지 않는다.

## 3중 레이어

| 레이어 | 어디서 도나 | 언제 | 파일/설정 |
|---|---|---|---|
| ① Claude 클라우드 Routine | Claude Code 클라우드 (모바일/PC 무관, 항상 켜져 있음) | 08:00 KST — 워크플로우 ②를 디스패치하고 결과 검증, 실패 시 오전 중 재시도 | claude.ai/code → 세션 환경의 Routine `krw-watcher-daily-8am` |
| ② GitHub Actions | GitHub 러너 | 08:00 KST 크론 + 08:45 KST 재시도 크론 (이미 됐으면 no-op) | `.github/workflows/daily-update.yml` |
| ③ PC 폴백 | 사용자 Windows PC | 08:00, 놓치면 부팅/절전 해제 직후 즉시 (`StartWhenAvailable`) | `scheduler/daily_update.ps1` + `register_daily_update.ps1` |

①·②는 PC가 꺼져 있어도 동작한다(사이트 호스트가 살아 있는 한). ③은
①·②가 모두 실패했거나 사이트 호스트 자체가 이 PC라 함께 잠들어 있던
경우를 커버한다.

## 각 실행이 하는 일

1. `GET /health` 재시도 루프로 사이트를 깨운다.
2. 신선도 검사 — 오늘 자 브리핑(`/api/briefing/latest`의 `brief.date`)과
   오늘 07시 이후 예측(`/api/forecast`의 `created_kst`)이 이미 있으면 종료.
3. 없으면 `POST /api/briefing/generate` (당일 브리핑, 블로킹).
4. `POST /api/cycle` (예측 사이클, 비동기) 후 예측이 갱신될 때까지 폴링.

## 설정 방법

**② GitHub Actions** — `master`에 머지되면 크론이 자동 활성화된다.
수동 실행: *Actions → Daily 8AM KST update → Run workflow*
(url/force 입력 가능).

**③ PC 폴백** — 관리자 PowerShell에서 한 번:

```powershell
powershell -ExecutionPolicy Bypass -File scheduler\register_daily_update.ps1
```

즉시 테스트:

```powershell
Start-ScheduledTask -TaskName "KRW-Watcher Daily 8AM Update"
Get-Content C:\Users\andul\fed-watcher\logs\daily_update.log -Tail 20
```

**① Claude Routine** — 이미 등록되어 있음. claude.ai/code 의 Routines
목록에서 `krw-watcher-daily-8am` 으로 확인/일시정지/삭제할 수 있다.
