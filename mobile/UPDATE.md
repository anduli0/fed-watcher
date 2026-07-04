# FED-WATCHER 모바일 대시보드 — 자동 업데이트 런북

이 문서는 예약 트리거가 이 세션을 깨울 때마다 수행할 절차다.
결과물은 Claude 아티팩트로 배포되며, 사용자는 휴대폰 Claude 앱에서 본다.

- **아티팩트 URL (고정, 같은 URL로 재배포할 것):**
  `https://claude.ai/code/artifact/e11867b7-f727-433c-b232-50250b27222e`
- **favicon: 🏦 (변경 금지)**
- **브랜치:** `claude/mobile-offline-functionality-h7k7bm`
- **갱신 주기:** 매일 07:30 / 12:30 / 17:30 / 22:30 KST (UTC 22:30 / 03:30 / 08:30 / 13:30)

## 환경 제약 (중요)

이 클라우드 환경의 네트워크 정책상 curl/WebFetch로는 외부에 접근할 수 **없다**
(프록시 403). **WebSearch만 작동한다.** 데이터 수집은 전부 WebSearch로 한다.

## 절차

1. **브랜치 동기화**
   ```bash
   git fetch origin claude/mobile-offline-functionality-h7k7bm
   git checkout claude/mobile-offline-functionality-h7k7bm
   git pull origin claude/mobile-offline-functionality-h7k7bm
   ```

2. **데이터 수집 (WebSearch, 4~6개 쿼리)**
   - CME FedWatch 다음 FOMC 동결/인상/인하 확률 (오늘 날짜 기준)
   - 최신 CPI / 코어 PCE / 실업률 / 비농업고용 발표치
   - 미 10년물 국채 금리 현재 수준
   - USD/KRW 환율 현재 수준과 주간 동향
   - 연준 의장·FOMC 위원 최신 발언, 점도표/정책 뉴스
   - (오전 07:30 KST 실행 시) 지난 24시간 매크로 뉴스 — 데일리 브리핑용

3. **분석 후 `mobile/data.json` 갱신**
   - `updated_at_kst` = 지금 KST (`TZ=Asia/Seoul date '+%Y-%m-%d %H:%M'`),
     `next_update_kst` = 다음 예약 시각
   - `meeting_probs`, `macro` 값·날짜 최신화 (`asof` 포함)
   - `hawk_dove_score`(0=비둘기, 100=매파)와 `stance`, `horizons`
     (signal/delta_bps/confidence/note)를 근거 기반으로 재산정
   - FOMC가 지나면 `next_fomc`를 다음 회의로 교체
   - `briefing`은 하루 1회(07:30 실행분)에 전면 재작성, 그 외에는
     달라진 사실만 반영. 전부 한국어.
   - `history`에 `{date, hold, hike, cut, signal, usdkrw}` 1행 append
     (하루 마지막 실행 기준으로 중복 날짜면 교체). 최근 30개 유지.

4. **렌더 + 배포**
   ```bash
   python3 mobile/render.py
   ```
   Artifact 도구로 `mobile/dashboard.html`을 배포하되 반드시
   `url` 파라미터에 위 고정 URL을 넣어 **같은 주소로 재배포**한다.
   favicon은 🏦 유지. label은 `auto-YYYYMMDD-HHMM` 형식.

5. **커밋 & 푸시**
   ```bash
   git add mobile/data.json mobile/dashboard.html
   git commit -m "chore(mobile): auto-update dashboard data"
   git push -u origin claude/mobile-offline-functionality-h7k7bm
   ```
   (푸시 실패 시 2s/4s/8s/16s 백오프로 최대 4회 재시도)

6. **Gucci Intelligence 클라우드 미러 갱신**
   - **아티팩트 URL (고정):** `https://claude.ai/code/artifact/1cb77b8f-c5f0-498e-bea1-026c555be548`
   - **favicon: 👜 (변경 금지)**
   - GitHub Actions(`fetch-gucci.yml`, 6시간마다)가 사용자 PC의 Tailscale funnel에서
     `gucci-mirror/`로 데이터를 커밋해 둔다 (PC가 꺼져 있으면 기존 데이터 유지).
   - 브랜치 pull 후 `gucci-mirror/`에 새 커밋이 있으면:
     ```bash
     python3 gucci-cloud/build.py
     ```
     실행 후 Artifact 도구로 `gucci-cloud/artifact.html`을 위 고정 URL에 재배포한다.
   - 미러 변경이 없으면 재배포하지 않는다 (동일 데이터 재배포 금지).

7. **보고는 간결하게** — 한 줄 요약(변경된 핵심 수치)만 남기고 종료.
   사용자에게 질문하지 말 것. 데이터 일부를 못 구하면 이전 값을 유지하고
   `sub`/`asof`에 기준일을 정직하게 남긴다.
