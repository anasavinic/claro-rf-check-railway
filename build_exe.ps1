# Build ClaroRFCheck-<tag>.exe the same way Vivo RF Check is packaged.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$tag = if ($env:CI_COMMIT_TAG) { $env:CI_COMMIT_TAG } else { "dev" }
$env:CI_COMMIT_TAG = $tag

if (Get-Command npm -ErrorAction SilentlyContinue) {
    Push-Location code\theme\static_src
    npm ci
    npm run build
    Pop-Location
} else {
    Write-Host "npm was not found. The exe will miss compiled Tailwind CSS."
}

python -m pip install --upgrade pip
python -m pip install -r requirements-desktop.txt
python -m PyInstaller main.spec --noconfirm --clean

$exe = Join-Path dist "ClaroRFCheck-$tag.exe"
if (-not (Test-Path $exe)) {
    throw "Build finished without $exe"
}
Write-Host "Built $exe"
