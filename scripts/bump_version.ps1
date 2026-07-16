# Bumps or sets VERSION and prints the new version to stdout.
# Usage: bump_version.ps1 -VersionFile path -Mode patch|minor|major|X.Y.Z|--no-bump
param(
    [Parameter(Mandatory = $true)]
    [string]$VersionFile,

    [Parameter(Mandatory = $true)]
    [string]$Mode
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $VersionFile)) {
    Write-Output "ERROR: VERSION file not found: $VersionFile"
    exit 1
}

$current = (Get-Content -LiteralPath $VersionFile -Raw).Trim()

if ($Mode -eq '--no-bump') {
    if ($current -notmatch '^\d+\.\d+\.\d+$') {
        Write-Output "ERROR: Invalid VERSION contents: $current"
        exit 1
    }
    Write-Output $current
    exit 0
}

if ($Mode -match '^\d+\.\d+\.\d+$') {
    $newVersion = $Mode
}
else {
    if ($current -notmatch '^(\d+)\.(\d+)\.(\d+)$') {
        Write-Output "ERROR: Invalid VERSION contents: $current"
        exit 1
    }
    $maj = [int]$Matches[1]
    $min = [int]$Matches[2]
    $pat = [int]$Matches[3]

    switch ($Mode.ToLowerInvariant()) {
        'major' { $maj++; $min = 0; $pat = 0 }
        'minor' { $min++; $pat = 0 }
        'patch' { $pat++ }
        default {
            Write-Output "ERROR: Unknown mode '$Mode'. Use patch|minor|major|X.Y.Z|--no-bump"
            exit 1
        }
    }
    $newVersion = "$maj.$min.$pat"
}

# Write without BOM so Python/git read a plain version string
[System.IO.File]::WriteAllText($VersionFile, $newVersion)
Write-Output $newVersion
