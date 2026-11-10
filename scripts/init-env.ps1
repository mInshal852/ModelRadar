# Generates .env from .env.example with random database credentials.
# Never overwrites an existing .env.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$example = Join-Path $root '.env.example'
$target = Join-Path $root '.env'

if (Test-Path $target) {
    Write-Host ".env already exists - leaving it unchanged."
    exit 0
}

function New-Secret {
    $bytes = New-Object byte[] 24
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    -join ($bytes | ForEach-Object { $_.ToString('x2') })
}

$lines = Get-Content $example | ForEach-Object {
    if ($_ -match '^(\w+)=CHANGE_ME$') { "$($Matches[1])=$(New-Secret)" } else { $_ }
}
Set-Content -Path $target -Value $lines -Encoding ascii
Write-Host "Created .env with generated credentials. It is git-ignored; do not commit it."
