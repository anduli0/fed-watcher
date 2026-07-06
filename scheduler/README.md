# 매일 아침 8시까지 자동 업데이트 완료 (Daily update done by 08:00 KST)

krw-watcher의 위원회 예측 사이클 + 당일 브리핑이 매일 아침 **8시(KST)까지
완료**되어 있도록 하는 시스템의 전체 지도. 제때 완료되지 못하면 **가능해지는
즉시** 복구·재검증한다. 모든 레이어가 멱등(오늘 아침 결과가 이미 있으면
no-op)이라 겹쳐 실행돼도 AI 토큰이 이중으로 소모되지 않는다.

인스턴스는 두 개이고 둘 다 매일 아침 갱신된다:

- **클라우드**: https://krw-watcher.onrender.com — Render 무료 티어, 24/7.
  **PC·휴대폰이 모두 꺼져 있어도 여기는 항상 8시까지 업데이트 완료.**
- **PC(Tailscale Funnel)**: https://krw-watcher.tail3e31a9.ts.net — PC가
  켜져 있으면 자체 스케줄러가 아침 사이클을 돌린다(실측: 07:30 KST 완료).
  꺼져 있으면 켜질 때 부팅 warm-up이 스스로 따라잡는다.

핵심 사실 (실측): PC 퍼널 사이트의 조작용 POST(/api/cycle,
/api/briefing/generate)는 인증으로 보호되어 **외부에서는 401**이 난다.
따라서 외부(클라우드)에서 PC 사이트를 "기동"할 수는 없고, 기동은 앱
내부 스케줄러/부팅 warm-up/PC 로컬 작업(localhost)이 담당하며 클라우드는
**검증**을 담당한다. 클라우드 인스턴스(Render 포트)는 POST가 열려 있어
직접 기동·복구가 가능하다.

## 레이어 지도

| 레이어 | 대상 | 언제 (KST) | 역할 | 파일/설정 |
|---|---|---|---|---|
| 앱 내부 스케줄러 | 클라우드 | 06:40 사이클 · 07:30 브리핑 | 기동 | Render env `CYCLE_HOURS_KST=6,13,20` |
| `daily-update-krw.yml` | 클라우드 | 07:50 + 09:50/12:50 스윕 | 검증·복구 (잠들었으면 깨우고 필요 시 POST로 기동) | `.github/workflows/` |
| 앱 내부 스케줄러 | PC 퍼널 | ~07:30 완료 (+ 부팅 warm-up) | 기동 | PC 앱 자체 |
| `daily-update.yml` | PC 퍼널 | 07:45 + 08:45/10:45/12:45/14:45 | 검증 전용 (외부 기동 불가 — 401) | `.github/workflows/` |
| PC 로컬 작업 | PC 퍼널 | 07:45, 놓치면 부팅 즉시 (`StartWhenAvailable`) | 복구 (localhost POST) | `scheduler/daily_update_krw.ps1` |
| Claude Routine (감시견) | 둘 다 | 08:10 — 두 워크플로우의 오늘 성공 검증, 없으면 dispatch, 지속 실패 시에만 푸시 알림 | 감시·보고 | claude.ai/code → Routines |

클라우드 레이어들은 사용자 기기가 전부 꺼져 있어도 동작한다. PC 퍼널
사이트가 오프라인이면(PC 꺼짐) 검증 워크플로우는 "SITE OFFLINE"으로
표시하고 오후까지 재검증하며, PC가 켜지는 순간 앱과 로컬 작업이 따라잡는다.

(참고: `scheduler/daily_update.ps1`은 별개인 **Fed-Watcher** 백엔드의
아침 wake-up 폴백, `daily-wakeup.yml`/`daily-update-fed.yml`은 그 클라우드
버전이다.)

## 설정 방법

**GitHub Actions** — master에 있으므로 크론 자동 동작. 수동 실행:
*Actions → 해당 워크플로우 → Run workflow*.

**Claude Routine** — 등록되어 있음. claude.ai/code 의 Routines 목록에서
확인/일시정지/삭제 가능.

**PC 로컬 복구 작업** — 관리자 PowerShell에서 한 번만:

```powershell
powershell -ExecutionPolicy Bypass -File scheduler\register_daily_update_krw.ps1
```

즉시 테스트:

```powershell
Start-ScheduledTask -TaskName "KRW-Watcher Daily 8AM Update"
Get-Content C:\Users\andul\fed-watcher\logs\daily_update_krw.log -Tail 20
```

만약 localhost POST도 401이 나면(앱이 토큰 인증을 요구하는 경우) 로컬
작업의 복구는 불가하고 앱 내부 스케줄러/재시작이 유일한 기동 경로다 —
로그에 해당 안내가 남는다.
