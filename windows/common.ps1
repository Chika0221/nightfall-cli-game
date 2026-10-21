Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-GameName([string]$Name) {
    if ($Name -notmatch '^NIGHTFALL(?:-[A-Za-z0-9-]+)?$') {
        throw 'The distro name must be NIGHTFALL or NIGHTFALL- followed by ASCII letters, digits and hyphens.'
    }
}

function Get-GameDistros {
    $output = & wsl.exe --list --quiet 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot list WSL distributions. Complete WSL 2 setup and restart Windows.' }
    @($output | ForEach-Object { ($_ -replace "`0", '').Trim() } | Where-Object { $_ })
}

function Invoke-WslChecked([string[]]$WslArgs) {
    & wsl.exe @WslArgs
    if ($LASTEXITCODE -ne 0) { throw "WSL command failed (exit $LASTEXITCODE)." }
}

function Assert-Wsl {
    if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
        throw 'WSL is missing. Ask your administrator to run: wsl --install --no-distribution ; then restart Windows.'
    }
    $build = [int](Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').CurrentBuildNumber
    if ($build -lt 22000) { throw 'This release supports Windows 11.' }
    & wsl.exe --version
    if ($LASTEXITCODE -ne 0) { throw 'A current WSL version with systemd support is required. Ask your administrator to run: wsl --update' }
}

function Assert-Rootfs([string]$Bundle) {
    $image = Join-Path $Bundle 'NIGHTFALL.rootfs.tar'
    $checksum = "$image.sha256"
    if (-not (Test-Path -LiteralPath $image -PathType Leaf) -or -not (Test-Path -LiteralPath $checksum -PathType Leaf)) {
        throw 'The prepared NIGHTFALL.rootfs.tar and its .sha256 file are missing. Obtain the complete release bundle from your organizer.'
    }
    $expected = ((Get-Content -LiteralPath $checksum -Raw).Trim() -split '\s+')[0]
    if ($expected -notmatch '^[0-9a-fA-F]{64}$' -or (Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash -ne $expected) {
        throw 'The game image checksum is invalid. Obtain the release bundle again.'
    }
    return $image
}

function Assert-Game([string]$Name) {
    Assert-GameName $Name
    if ($Name -notin @(Get-GameDistros)) { throw 'Game environment not installed. Run the initial setup first.' }
    $marker = & wsl.exe --distribution $Name --user root --exec cat /etc/nightfall/identity 2>$null
    if ($LASTEXITCODE -ne 0 -or (($marker -join "`n").Trim() -ne 'NIGHTFALL-WSL-1')) {
        throw 'This distro is not a NIGHTFALL environment. It will not be modified. Choose another game name.'
    }
}

function Install-Game([string]$Name, [string]$Bundle) {
    Assert-GameName $Name
    if ($Name -in @(Get-GameDistros)) {
        Assert-Game $Name
        Write-Host "Using existing game environment: $Name (progress preserved)."
        return
    }
    $image = Assert-Rootfs $Bundle
    $location = Join-Path $env:LOCALAPPDATA "NIGHTFALL\distros\$Name"
    if (Test-Path -LiteralPath $location) { throw "Install directory already exists: $location . Choose another name; no files were removed." }
    New-Item -ItemType Directory -Path $location -Force | Out-Null
    Invoke-WslChecked @('--import', $Name, $location, $image, '--version', '2')
    Assert-Game $Name
    Write-Host "Setup complete: $Name"
}

function Invoke-GameAdmin([string]$Name, [string[]]$AdminArgs) {
    Invoke-WslChecked (@('--distribution', $Name, '--user', 'root', '--exec', '/opt/nightfall/venv/bin/python', '-I', '-m', 'nightfall.admin') + $AdminArgs)
}
