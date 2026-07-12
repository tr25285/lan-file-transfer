$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Version = "1.0.0"
$ExeName = "LANFileTransfer.exe"
$ZipName = "lan-file-transfer-v$Version-windows.zip"
$ReleaseAssets = Join-Path $Root "release-assets"

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

if (!(Test-Path ".venv")) {
    py -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "py -m venv failed with exit code $LASTEXITCODE"
    }
}

Invoke-Native ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
Invoke-Native ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
Invoke-Native ".\.venv\Scripts\python.exe" -m pytest
Invoke-Native ".\.venv\Scripts\pyinstaller.exe" LANFileTransfer.spec --clean --noconfirm

if (Test-Path $ReleaseAssets) {
    Remove-Item -LiteralPath $ReleaseAssets -Recurse -Force
}
New-Item -ItemType Directory -Path $ReleaseAssets | Out-Null

$BuiltExe = Join-Path $Root "dist\$ExeName"
$ReleaseExe = Join-Path $ReleaseAssets $ExeName
$ReleaseZip = Join-Path $ReleaseAssets $ZipName
$ShaFile = Join-Path $ReleaseAssets "SHA256SUMS.txt"

Copy-Item -LiteralPath $BuiltExe -Destination $ReleaseExe
Compress-Archive -LiteralPath $ReleaseExe -DestinationPath $ReleaseZip -Force

$hashLines = Get-ChildItem -LiteralPath $ReleaseAssets -File |
    Where-Object { $_.Name -ne "SHA256SUMS.txt" } |
    Sort-Object Name |
    ForEach-Object {
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $($_.Name)"
    }
Set-Content -LiteralPath $ShaFile -Value $hashLines -Encoding ascii

Write-Host "Built: $BuiltExe"
Write-Host "Release assets: $ReleaseAssets"
