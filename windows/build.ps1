# Organizer-only builder. Requires internet for Ubuntu packages; players do not run this.
param(
    [Parameter(Mandatory=$true)][string]$UbuntuRootfs,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$UbuntuSha256,
    [string]$OutputDirectory = (Join-Path (Split-Path $PSScriptRoot -Parent) 'dist'),
    [switch]$KeepBuildEnvironment
)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Wsl
$UbuntuRootfs = (Resolve-Path -LiteralPath $UbuntuRootfs).Path
if ((Get-FileHash -LiteralPath $UbuntuRootfs -Algorithm SHA256).Hash -ne $UbuntuSha256) {
    throw 'Ubuntu rootfs checksum mismatch.'
}
$repo = Split-Path $PSScriptRoot -Parent
$buildName = "NIGHTFALL-BUILD-$([guid]::NewGuid().ToString('N').Substring(0,8))"
$working = Join-Path $env:TEMP $buildName
New-Item -ItemType Directory -Path $working | Out-Null
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$OutputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
if (Test-Path -LiteralPath (Join-Path $OutputDirectory 'NIGHTFALL.rootfs.tar')) {
    throw 'Output already contains a release image. Use a fresh output directory.'
}
$imported = $false
try {
    $sourceTar = Join-Path $working 'source.tar'
    & tar.exe -cf $sourceTar -C $repo nightfall scripts
    if ($LASTEXITCODE -ne 0) { throw 'Source packaging failed.' }
    Invoke-WslChecked @('--import', $buildName, (Join-Path $working 'distro'), $UbuntuRootfs, '--version', '2')
    $imported = $true
    Invoke-WslChecked @('--distribution', $buildName, '--user', 'root', '--exec', 'mkdir', '-p', '/tmp/nightfall-source')
    # Stream bytes with .NET: Windows PowerShell 5.1 text pipelines corrupt binary tar data.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'wsl.exe'
    $psi.Arguments = "--distribution $buildName --user root --exec tar -xf - -C /tmp/nightfall-source"
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $process = [System.Diagnostics.Process]::Start($psi)
    $inputStream = [System.IO.File]::OpenRead($sourceTar)
    try { $inputStream.CopyTo($process.StandardInput.BaseStream) } finally { $inputStream.Dispose(); $process.StandardInput.Close() }
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw 'Copying source to the build environment failed.' }
    Invoke-WslChecked @('--distribution', $buildName, '--user', 'root', '--exec', 'bash', '/tmp/nightfall-source/scripts/provision.sh')
    Invoke-WslChecked @('--distribution', $buildName, '--user', 'root', '--exec', 'rm', '-rf', '/tmp/nightfall-source')
    Invoke-WslChecked @('--terminate', $buildName)
    $image = Join-Path $OutputDirectory 'NIGHTFALL.rootfs.tar'
    Invoke-WslChecked @('--export', $buildName, $image)
    (Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash.ToLowerInvariant() | Set-Content -LiteralPath "$image.sha256" -Encoding ASCII
    Copy-Item -LiteralPath (Join-Path $repo 'windows') -Destination $OutputDirectory -Recurse
    Get-ChildItem -LiteralPath $repo -Filter '*.cmd' | Copy-Item -Destination $OutputDirectory
    Copy-Item -LiteralPath (Join-Path $repo 'docs\player.md') -Destination (Join-Path $OutputDirectory 'START-HERE.md')
    Write-Host "Release bundle prepared: $OutputDirectory"
} finally {
    if ($imported -and -not $KeepBuildEnvironment) {
        # Only unregister the unique temporary distro this invocation created.
        & wsl.exe --unregister $buildName
        if ($LASTEXITCODE -eq 0) { Remove-Item -LiteralPath $working -Recurse -Force }
    }
}
