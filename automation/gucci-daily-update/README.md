# Gucci Intelligence 일간 자동 업데이트 구성

https://anduli0.github.io/gucci-intel-site/ 를 **매일 아침 08:00 KST까지 업데이트 완료**되도록 하는 3중 구성.
실행에 통상 30~45분이 걸리므로 06:50에 시작해 8시 전에 배포가 끝나게 한다.

## 구조

```
[1차] 클라우드 정기 실행   매일 06:50 KST 시작 → 08:00 전 완료  ← Claude(Max 구독) 클라우드 예약 작업
[2차] 클라우드 보정 실행   매일 08:05 KST 체크                  ← 1차 미완료 감지 시에만 즉시 대신 실행
[3차] 배포 검증 (GitHub)   매일 08:20 KST 체크                  ← 라이브 사이트가 오늘자인지 GitHub Actions가 검증.
                                                                  배포만 실패했으면 자동 재배포, 업데이트 자체가
                                                                  누락됐으면 실패 처리 → GitHub이 실패 메일 발송
[4차] PC 폴백 (선택)       매일 09:00 KST 체크                  ← 위가 모두 실패 시에만 실제 동작
```

3차는 사이트 저장소의 `.github/workflows/verify-freshness.yml`이며 Claude와 무관하게 GitHub 서버에서 실행된다.

- **1·2차는 폰/PC가 꺼져 있어도 실행된다.** Anthropic 클라우드에서 도는 예약 작업(Routine)이라
  기기와 무관하며, Claude 모바일 앱(claude.ai)의 Code 탭에서 실행 내역·결과를 확인할 수 있다.
- 1차 완료 시 **모바일 푸시 + 이메일 알림**이 발송된다 (그날의 GMAI 요약 포함).
- 8시까지 완료되지 못했으면 2차(08:05 KST 체크)가 자동으로 감지해 즉시 대신 실행한다
  ("8시에 안 되면 되는대로 바로").
- 업데이트 절차 자체는 사이트 저장소의 `automation/DAILY_UPDATE.md` 런북에 정의돼 있다.
  런북 수정 = 자동 업데이트 동작 수정.

## 예약 작업 관리

claude.ai (모바일/웹) → Claude Code → Routines에서 확인/중지 가능:

| 이름 | cron (UTC) | KST | 알림 |
|---|---|---|---|
| Gucci Intel 일간 업데이트 (06:50 KST 시작 → 08:00 전 완료) | `50 21 * * *` | 06:50 시작 | 푸시+이메일 |
| Gucci Intel 미완료 보정 체크 (08:05 KST) | `5 23 * * *` | 08:05 | 없음(보정 실행 시에만 세션 기록) |

## PC 폴백 설치 (선택 사항)

클라우드 실행이 계속 실패하는 경우를 대비한 최후 안전망. 윈도우 PC에서:

1. 이 폴더(`automation/gucci-daily-update/`)를 PC로 복사
2. Claude Code CLI 설치·로그인 확인 (`claude --version`)
3. 관리자 PowerShell에서:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\register-task.ps1
   ```

동작 방식: 매일 09:00에 라이브 사이트의 `api/summary` 날짜를 확인 → 이미 오늘 날짜면 즉시 종료(중복 실행 없음) → 오래됐으면 로컬에서 `claude -p`로 런북을 실행해 업데이트·푸시. PC가 10:30에 꺼져 있었으면 켜질 때 즉시 실행된다. 로그는 `~\gucci-intel-logs\`에 남는다.

## 참고: 클라우드 환경의 네트워크 제한

현재 클라우드 환경은 임의 외부 사이트 fetch가 차단돼 있고 **WebSearch(검색)는 허용**된다.
따라서 클라우드 실행은 검색 결과 기반으로 리서치한다. 기사 본문까지 읽는 더 깊은 리서치를
원하면 claude.ai → Code → 환경 설정에서 네트워크 정책을 완화하면 된다(런북은 그대로 동작).
