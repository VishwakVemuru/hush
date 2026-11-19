# Builds dist\hush\hush.exe (PyInstaller) and dist\hush-setup.exe (Inno Setup 6).
# Needs: pip install pyinstaller pywebview psutil pystray Pillow   and   winget install JRSoftware.InnoSetup
param([string]$Version = "1.4.0")
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
Push-Location $root
try {
    Remove-Item build, dist -Recurse -Force -ErrorAction SilentlyContinue
    $ErrorActionPreference = 'Continue'
    python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\hush.spec 2>&1 | Select-String -Pattern 'ERROR|error:|Building COLLECT|completed successfully' | ForEach-Object { "$_" }
    $ErrorActionPreference = 'Stop'
    if (-not (Test-Path dist\hush\hush.exe)) { throw 'PyInstaller did not produce dist\hush\hush.exe' }

    $iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { throw 'Inno Setup 6 (ISCC.exe) not found' }
    $env:HUSH_VERSION = $Version
    & $iscc /Q packaging\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed ($LASTEXITCODE)" }
    $s = Get-Item dist\hush-setup.exe
    "Installer ready: $($s.FullName) ($([math]::Round($s.Length / 1MB, 1)) MB)"
} finally { Pop-Location }
