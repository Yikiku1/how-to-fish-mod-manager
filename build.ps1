param([string]$Version = '1.2')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $dictionary = Join-Path $PSScriptRoot 'zh_CN.json'
    python -m PyInstaller --noconfirm --onefile --windowed --name "HowToFishModManager-v$Version" --add-data "$dictionary;." --distpath dist --workpath .build --specpath .build manager.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
} finally {
    Pop-Location
}
