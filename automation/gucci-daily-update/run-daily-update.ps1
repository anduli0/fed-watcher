# Gucci Intelligence 일간 업데이트 — PC 폴백 실행기
#
# 동작:
#   1. 라이브 사이트의 api/summary 날짜를 확인한다.
#      오늘(KST) 날짜면 클라우드 정기 업데이트가 이미 성공한 것 → 아무것도 안 하고 종료.
#   2. 오래된 날짜면 로컬에서 Claude Code CLI로 런북(automation/DAILY_UPDATE.md)을 실행해
#      직접 업데이트하고 main에 푸시한다.
#
# 요구사항: git, Claude Code CLI(claude)가 PATH에 있고 로그인(Max 구독)돼 있을 것.

$ErrorActionPreference = "Stop"

$SiteUrl   = "https://anduli0.github.io/gucci-intel-site"
$RepoUrl   = "https://github.com/anduli0/gucci-intel-site.git"
$LocalRepo = Join-Path $HOME "gucci-intel-site"
$LogDir    = Join-Path $HOME "gucci-intel-logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile   = Join-Path $LogDir ("update-{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))

function Log($msg) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $LogFile -Value $line
}

# KST 기준 오늘 날짜 (PC가 KST가 아니어도 안전하게)
$kst = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, "Korea Standard Time")
$Today = $kst.ToString("yyyy-MM-dd")
Log "KST today = $Today"

# 1) 이미 업데이트됐는지 확인 (캐시 우회 쿼리스트링)
try {
    $summary = Invoke-RestMethod -Uri "$SiteUrl/api/summary?cb=$(Get-Random)" -TimeoutSec 30
    Log "live site summary.date = $($summary.date)"
    if ($summary.date -eq $Today) {
        Log "클라우드 정기 업데이트가 이미 완료됨 — PC 폴백 불필요. 종료."
        exit 0
    }
} catch {
    Log "라이브 사이트 확인 실패($_) — 폴백 업데이트를 진행한다."
}

# 2) 로컬 클론 준비
if (Test-Path (Join-Path $LocalRepo ".git")) {
    Log "git pull origin main"
    git -C $LocalRepo pull origin main 2>&1 | Add-Content $LogFile
} else {
    Log "git clone $RepoUrl"
    git clone $RepoUrl $LocalRepo 2>&1 | Add-Content $LogFile
}

# 3) Claude Code로 런북 실행 (필요 도구만 허용)
$Prompt = @"
이 저장소는 Gucci Intelligence 사이트다. automation/DAILY_UPDATE.md 런북을 읽고 그대로 따라 오늘($Today, KST)자 일간 업데이트를 수행하라.
api/summary의 date가 이미 $Today 이면 아무것도 변경하지 말고 종료하라.
리서치는 WebSearch/WebFetch를 사용하고, 모든 수정 JSON을 검증한 뒤 main에 커밋·푸시하라 (커밋 메시지: "auto publish $Today (claude pc fallback)").
이 작업은 자동 작업이다 — 질문으로 멈추지 말고 런북 원칙에 따라 완주하라.
"@

Log "claude 실행 시작"
Push-Location $LocalRepo
try {
    claude -p $Prompt `
        --permission-mode acceptEdits `
        --allowedTools "WebSearch,WebFetch,Read,Write,Edit,Glob,Grep,Bash(git:*),Bash(python:*),Bash(python3:*)" `
        2>&1 | Add-Content $LogFile
    Log "claude 실행 종료 (exit=$LASTEXITCODE)"
} finally {
    Pop-Location
}

# 4) 결과 확인
$after = git -C $LocalRepo log -1 --format="%h %s"
Log "HEAD after run: $after"
