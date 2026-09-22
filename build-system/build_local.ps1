# Builds the branded Telegram Desktop locally (Debug by default).
#
# Prerequisites follow docs/building-win.md: Visual Studio 2026 with the
# v145 toolset, Python 3.10 and Git. First prepare the libraries from a
# BuildPath terminal:
#
#     tdesktop\Telegram\build\prepare\win.bat
#
# Then run from the standard x64 Native Tools prompt for VS 2026:
#
#     build-system\build_local.ps1
#
# The script generates icons from Telegram/Resources/art/logo.png (when
# present), rebrands the sources, configures a Debug build and runs the
# build. The API credentials come from -D TDESKTOP_API_ID=... -D
# TDESKTOP_API_HASH=... arguments when given; otherwise the open test
# credentials are used.
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Config = 'Debug'
$configureArgs = @()
foreach ($arg in $args) {
    if ($arg -eq '-Release') {
        $Config = 'Release'
    } else {
        $configureArgs += $arg
    }
}

Push-Location $RepoRoot
try {
    python (Join-Path $RepoRoot 'build-system\generate_icons.py') --root $RepoRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Push-Location (Join-Path $RepoRoot 'Telegram')
    try {
        $apiCreds = $configureArgs | Where-Object { $_ -like '-D TDESKTOP_API_ID=*' -or $_ -like '-D TDESKTOP_API_HASH=*' }
        if (-not $apiCreds) {
            $configureArgs += '-D TDESKTOP_API_TEST=ON'
        }
        & .\configure.bat x64 `
            -D CMAKE_CONFIGURATION_TYPES=$Config `
            -D CMAKE_COMPILE_WARNING_AS_ERROR=OFF `
            -D CMAKE_MSVC_DEBUG_INFORMATION_FORMAT= `
            -D DESKTOP_APP_DISABLE_AUTOUPDATE=ON `
            -D DESKTOP_APP_DISABLE_CRASH_REPORTS=ON `
            @configureArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

        python (Join-Path $RepoRoot 'build-system\apply_branding.py') --root $RepoRoot
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

        cmake --build ..\out --config $Config --target Telegram --parallel
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
} finally {
    Pop-Location
}

Write-Host "Built out\$Config\Telegram.exe"