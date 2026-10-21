param([string]$Name = 'NIGHTFALL')
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Wsl
Install-Game $Name (Split-Path $PSScriptRoot -Parent)
Write-Host 'Run the game launcher to start or resume. No internet is needed during play.'
