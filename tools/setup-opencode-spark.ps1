<#
 Prepara il PC Windows per usare DeepSeek V4.1 Flash servito dal DGX Spark con OpenCode.
 - verifica che l'endpoint risponda
 - crea o aggiorna %USERPROFILE%\.config\opencode\opencode.json fondendo il provider "ds4"
   (backup del file esistente in opencode.json.bak-<data>)
 - imposta il modello predefinito ds4/deepseek-v4.1-flash
 - controlla se OpenCode è installato e, se manca, mostra il comando di installazione

 Uso (PowerShell):  powershell -ExecutionPolicy Bypass -File .\setup-opencode-spark.ps1 [-SparkHost 172.31.32.197] [-Port 8011]
#>
param(
    [string]$SparkHost = "172.31.32.197",
    [int]$Port = 8011,
    [int]$Context = 32768,
    [int]$Output = 8192,
    [string]$ProjectDir = ""   # opzionale: scrive anche <ProjectDir>\opencode.json (precedenza massima, letto sempre, anche dalla Desktop app)
)
$ErrorActionPreference = "Stop"
$base = "http://${SparkHost}:${Port}/v1"

Write-Host "1) Verifica endpoint $base ..." -ForegroundColor Cyan
try {
    $models = Invoke-RestMethod -Uri "$base/models" -TimeoutSec 10
    $id = $models.data[0].id
    Write-Host "   OK: modello '$id', contesto $($models.data[0].context_length)" -ForegroundColor Green
} catch {
    Write-Host "   ERRORE: endpoint non raggiungibile ($($_.Exception.Message))." -ForegroundColor Red
    Write-Host "   Sul Spark: ~/serve-v41.sh --status   (e verifica ufw / rete)"
    exit 1
}

Write-Host "2) Configurazione OpenCode ..." -ForegroundColor Cyan
$cfgDir  = Join-Path $env:USERPROFILE ".config\opencode"
$cfgPath = Join-Path $cfgDir "opencode.json"
New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null

$provider = [ordered]@{
    name    = "DwarfStar V4.1 Flash (Spark)"
    npm     = "@ai-sdk/openai-compatible"
    options = [ordered]@{ baseURL = $base; apiKey = "dsv4-local" }
    models  = [ordered]@{
        "deepseek-v4.1-flash" = [ordered]@{
            name  = "DeepSeek V4.1 Flash Q2 pruned (Spark)"
            limit = [ordered]@{ context = $Context; output = $Output }
        }
    }
}

if (Test-Path $cfgPath) {
    $bak = "$cfgPath.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
    Copy-Item $cfgPath $bak
    Write-Host "   file esistente, backup in $bak"
    $raw = Get-Content $cfgPath -Raw
    $cfg = if ($raw.Trim()) { $raw | ConvertFrom-Json -AsHashtable } else { @{} }
} else {
    $cfg = @{}
    Write-Host "   creo $cfgPath"
}
if (-not $cfg.ContainsKey('$schema')) { $cfg['$schema'] = "https://opencode.ai/config.json" }
if (-not $cfg.ContainsKey('provider') -or $null -eq $cfg['provider']) { $cfg['provider'] = @{} }
$cfg['provider']['ds4'] = $provider
$cfg['model'] = "ds4/deepseek-v4.1-flash"
$cfg | ConvertTo-Json -Depth 10 | Set-Content -Path $cfgPath -Encoding UTF8
Write-Host "   OK: provider 'ds4' scritto, modello predefinito ds4/deepseek-v4.1-flash" -ForegroundColor Green

if ($ProjectDir) {
    $projCfg = Join-Path $ProjectDir "opencode.json"
    if (Test-Path $projCfg) { Copy-Item $projCfg "$projCfg.bak-$(Get-Date -Format yyyyMMdd-HHmmss)" }
    $pc = [ordered]@{ '$schema' = "https://opencode.ai/config.json"; provider = @{ ds4 = $provider }; model = "ds4/deepseek-v4.1-flash" }
    $pc | ConvertTo-Json -Depth 10 | Set-Content -Path $projCfg -Encoding UTF8
    Write-Host "   OK: scritto anche $projCfg (config di progetto)" -ForegroundColor Green
}

Write-Host "3) OpenCode installato? ..." -ForegroundColor Cyan
$oc = Get-Command opencode -ErrorAction SilentlyContinue
if ($oc) {
    Write-Host "   OK: $($oc.Source)" -ForegroundColor Green
} else {
    Write-Host "   OpenCode non trovato nel PATH. Installalo con uno di questi comandi:" -ForegroundColor Yellow
    Write-Host "     npm install -g opencode-ai"
    Write-Host "     (oppure) irm https://opencode.ai/install | iex"
}

Write-Host ""
Write-Host "4) Prova rapida dell'endpoint con una chat completion ..." -ForegroundColor Cyan
$body = @{ model = "deepseek-v4.1-flash"; max_tokens = 24; temperature = 0; think = $false
           messages = @(@{ role = "user"; content = "Rispondi con una sola parola: pronto?" }) } | ConvertTo-Json -Depth 5
try {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $r = Invoke-RestMethod -Uri "$base/chat/completions" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 300
    $sw.Stop()
    Write-Host ("   risposta in {0:n1}s: {1}" -f $sw.Elapsed.TotalSeconds, $r.choices[0].message.content.Trim()) -ForegroundColor Green
} catch {
    Write-Host "   la richiesta è fallita: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "Fatto. Riavvia OpenCode (anche la Desktop app: legge la configurazione all'avvio) e seleziona" -ForegroundColor Cyan
Write-Host "il modello con /models -> 'DwarfStar V4.1 Flash (Spark)'. Se la Desktop app non mostra il provider," -ForegroundColor Cyan
Write-Host "rilancia con -ProjectDir <cartella del progetto> per scrivere un opencode.json di progetto." -ForegroundColor Cyan
Write-Host "Il modello predefinito è ds4/deepseek-v4.1-flash (cambialo con /models). La prima richiesta paga il prefill"
Write-Host "del system prompt (~40 token/s, poi resta in cache sul server)."
