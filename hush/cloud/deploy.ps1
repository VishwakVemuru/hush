# Sets up (or updates) your own hush. sync Worker on Cloudflare. Needs Node.js and `npx wrangler login` done once.
# Everything account-specific (database id, Worker URL, sync key) is written OUTSIDE the repo:
#   %LOCALAPPDATA%\hush\cloud-deploy\wrangler.toml   and   %LOCALAPPDATA%\hush\cloud.json
$ErrorActionPreference = 'Stop'
$src  = $PSScriptRoot
$data = Join-Path $env:LOCALAPPDATA 'hush'
$dir  = Join-Path $data 'cloud-deploy'
$cfgFile = Join-Path $data 'cloud.json'
New-Item -ItemType Directory -Force $dir | Out-Null
Copy-Item "$src\worker.js", "$src\schema.sql" $dir -Force
Push-Location $dir
try {
    function W([string[]]$a) {
        $ErrorActionPreference = 'Continue'
        $out = & npx -y wrangler@4 @a 2>&1 | ForEach-Object { "$_" }
        if ($LASTEXITCODE -ne 0) { $out | Write-Host; throw "wrangler $($a -join ' ') failed" }
        return $out
    }

    # 1. database (reuse if it already exists)
    $list = (W @('d1', 'list', '--json')) -join "`n"
    $db = (ConvertFrom-Json $list) | Where-Object { $_.name -eq 'hush-sync' } | Select-Object -First 1
    if (-not $db) {
        W @('d1', 'create', 'hush-sync') | Out-Null
        $db = (ConvertFrom-Json ((W @('d1', 'list', '--json')) -join "`n")) | Where-Object { $_.name -eq 'hush-sync' } | Select-Object -First 1
    }
    $dbId = $db.uuid
    if (-not $dbId) { throw 'could not find the hush-sync database id' }

    @"
name = "hush-sync"
main = "worker.js"
compatibility_date = "2025-06-01"
workers_dev = true

[[d1_databases]]
binding = "DB"
database_name = "hush-sync"
database_id = "$dbId"
"@ | Set-Content -Encoding utf8 (Join-Path $dir 'wrangler.toml')

    # 2. tables
    W @('d1', 'execute', 'hush-sync', '--remote', '--file', 'schema.sql', '--yes') | Out-Null

    # 3. code
    $dep = (W @('deploy')) -join "`n"
    $url = ([regex]::Match($dep, 'https://hush-sync\.[a-z0-9-]+\.workers\.dev')).Value
    if (-not $url) { $dep | Write-Host; throw 'deployed, but could not read the workers.dev URL' }

    # 4. sync key (kept if it already exists, so paired phones keep working)
    $cfg = if (Test-Path $cfgFile) { Get-Content -Raw $cfgFile | ConvertFrom-Json } else { $null }
    $key = if ($cfg -and $cfg.key) { $cfg.key } else {
        $b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
        ([Convert]::ToBase64String($b) -replace '[+/=]', '').Substring(0, 40)
    }
    @{ url = $url; key = $key } | ConvertTo-Json | Set-Content -Encoding utf8 $cfgFile
    # pipe through cmd, not PowerShell: PowerShell's pipeline adds a newline/BOM and the key would not match
    $ErrorActionPreference = 'Continue'
    cmd /c "python -I -c ""import json,sys;sys.stdout.write(json.load(open(sys.argv[1],encoding='utf-8-sig'))['key'])"" ""$cfgFile"" | npx -y wrangler@4 secret put SYNC_KEY" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'could not set the SYNC_KEY secret' }
    $ErrorActionPreference = 'Stop'
    "hush. sync is live at $url"
    "Config saved to $cfgFile (keep it private; it is not in the repo)."
} finally { Pop-Location }
