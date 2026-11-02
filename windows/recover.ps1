param([string]$Name = 'NIGHTFALL')
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Wsl
Assert-Game $Name
Write-Host "This restores /home/contractor and /srv/nightfall in $Name to the last saved checkpoint."
Write-Host 'File edits since that checkpoint will be lost. Acquired records and authentication state are preserved.'
if ((Read-Host 'Close the game first. Type RESTORE to continue') -cne 'RESTORE') { return }
Invoke-WslChecked @('--distribution', $Name, '--user', 'root', '--exec', 'systemctl', 'stop', 'nightfall.service')
try {
    Invoke-GameAdmin $Name @('rebuild')
} finally {
    Invoke-WslChecked @('--distribution', $Name, '--user', 'root', '--exec', 'systemctl', 'start', 'nightfall.service')
}
Write-Host 'Recovery complete. Start the game again.'
