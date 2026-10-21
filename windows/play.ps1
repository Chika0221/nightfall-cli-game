param([string]$Name = 'NIGHTFALL')
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Wsl
Assert-Game $Name
$bundle = Split-Path $PSScriptRoot -Parent
while ($true) {
    Invoke-WslChecked @('--distribution', $Name, '--user', 'root', '--exec', 'systemctl', 'start', 'nightfall.service')
    & wsl.exe --distribution $Name --user contractor --cd /home/contractor --exec /usr/local/bin/nightfall-shell
    # A normal exit or Ctrl+C leaves all game data intact.
    $stageText = @(Invoke-GameAdmin $Name @('take-replay-request'))
    $stage = ($stageText -join '').Trim()
    if (-not $stage) { break }
    if ($stage -notmatch '^(?:[1-9]|10)$') { throw 'Invalid practice request.' }
    $practice = "$Name-practice-S$stage-$([guid]::NewGuid().ToString('N').Substring(0,8))"
    Install-Game $practice $bundle
    Invoke-WslChecked @('--distribution', $practice, '--user', 'root', '--exec', 'systemctl', 'stop', 'nightfall.service')
    try {
        Invoke-GameAdmin $practice @('init', '--stage', $stage)
    } finally {
        Invoke-WslChecked @('--distribution', $practice, '--user', 'root', '--exec', 'systemctl', 'start', 'nightfall.service')
    }
    Write-Host "Practice environment: $practice . Type exit to return to the main game."
    & wsl.exe --distribution $practice --user contractor --cd /home/contractor --exec /usr/local/bin/nightfall-shell
    Write-Host 'Returning to the main game.'
}
