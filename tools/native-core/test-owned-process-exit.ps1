# Windows runtime regression for the guarded driver's cached-handle contract.
# Runs only new owned cmd children; no broad process kills or file deletion.
$ErrorActionPreference = 'Stop'
foreach ($expected in @(0,7)) {
    $process = Start-Process -FilePath $env:ComSpec -ArgumentList @('/d','/c',('exit ' + $expected)) -WindowStyle Hidden -PassThru
    $ownedHandle = $process.Handle
    if (-not $process.WaitForExit(10000)) { throw 'Exit probe timed out.' }
    $process.WaitForExit()
    $process.Refresh()
    if ($null -eq $process.ExitCode -or $process.ExitCode -ne $expected) { throw "Expected $expected, got $($process.ExitCode)." }
}
$killed = Start-Process -FilePath $env:ComSpec -ArgumentList @('/d','/c','ping -n 20 127.0.0.1 > nul') -WindowStyle Hidden -PassThru
$ownedHandle = $killed.Handle
& taskkill.exe /PID $killed.Id /T /F | Out-Null
if (-not $killed.WaitForExit(10000)) { throw 'Owned killed process did not exit.' }
$killed.WaitForExit()
$killed.Refresh()
if ($null -eq $killed.ExitCode -or $killed.ExitCode -eq 0) { throw 'An intentional kill must never be reported as success.' }
Write-Output 'OWNED_PROCESS_EXIT_REGRESSION_PASS: exit 0, exit 7, intentional kill nonzero.'
