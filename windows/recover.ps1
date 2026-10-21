param([string]$Name = 'NIGHTFALL')
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Wsl
Assert-Game $Name
Write-Host "This restores /home/contractor and /srv/nightfall in $Name to the current stage's starting snapshot."
Write-Host 'Edits made during the current stage will be lost. Earlier clear records are preserved.'
if ((Read-Host 'Close the game first. Type RESTORE to continue') -cne 'RESTORE') { return }
Invoke-WslChecked @('--distribution', $Name, '--user', 'root', '--exec', 'systemctl', 'stop', 'nightfall.service')
try {
    Invoke-GameAdmin $Name @('rebuild')
} finally {
    Invoke-WslChecked @('--distribution', $Name, '--user', 'root', '--exec', 'systemctl', 'start', 'nightfall.service')
}
Write-Host 'Recovery complete. Start the game again.'
