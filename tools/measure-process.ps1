<#
.SYNOPSIS
Samples one already-running process without launching it or changing its state.

.DESCRIPTION
Reports CPU-time deltas over a monotonic interval, one-core and logical-host
normalized CPU percentages, sampled working/private memory, handles and threads.
Only the supplied PID is queried; process command lines and other processes are
not enumerated. An existing output file is never overwritten.

This measures the process during the selected interval. It is not a cold-start
measurement, does not measure UI readiness, excludes browser/child processes,
and cannot prove the absence of a memory leak. Sampled peaks can miss brief
spikes. The collector itself also has a small, separate measurement overhead.

.EXAMPLE
.\tools\measure-process.ps1 -ProcessId 1234 -Seconds 30 -OutputPath .\qa\idle.json
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 2147483647)]
    [int]$ProcessId,

    [ValidateRange(1, 60)]
    [int]$Seconds = 30,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$OutputPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$resolvedOutput = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath)
$outputDirectory = [System.IO.Path]::GetDirectoryName($resolvedOutput)
if (-not [System.IO.Directory]::Exists($outputDirectory)) {
    throw "Output directory does not exist: $outputDirectory"
}
if ([System.IO.File]::Exists($resolvedOutput) -or [System.IO.Directory]::Exists($resolvedOutput)) {
    throw "Output path already exists; choose a new JSON filename: $resolvedOutput"
}

$logicalProcessorCount = [Environment]::ProcessorCount
$logicalProcessorSource = 'Environment.ProcessorCount (collector-visible logical processors)'
try {
    # Host hardware metadata only: this does not enumerate running processes.
    $computer = Get-CimInstance -ClassName Win32_ComputerSystem -Property NumberOfLogicalProcessors
    if ([int]$computer.NumberOfLogicalProcessors -gt 0) {
        $logicalProcessorCount = [int]$computer.NumberOfLogicalProcessors
        $logicalProcessorSource = 'Win32_ComputerSystem.NumberOfLogicalProcessors'
    }
}
catch {
    # Restricted CIM access must not prevent exact-PID collection. The source
    # records that host normalization uses the collector-visible CPU count.
}

function Read-TargetSample {
    param([System.Diagnostics.Process]$Target)

    $Target.Refresh()
    if ($Target.HasExited) {
        throw 'The target process exited during measurement.'
    }
    $cpuSeconds = $Target.TotalProcessorTime.TotalSeconds
    $monotonicTicks = [System.Diagnostics.Stopwatch]::GetTimestamp()
    [pscustomobject]@{
        monotonic_ticks = $monotonicTicks
        captured_at_utc = [DateTime]::UtcNow.ToString('o')
        cpu_total_seconds = $cpuSeconds
        working_set_bytes = [long]$Target.WorkingSet64
        private_bytes = [long]$Target.PrivateMemorySize64
        handle_count = [int]$Target.HandleCount
        thread_count = [int]$Target.Threads.Count
    }
}

function Get-SampledMetric {
    param(
        [object[]]$Samples,
        [string]$Property
    )

    $peak = [long]0
    foreach ($sample in $Samples) {
        $value = [long]$sample.$Property
        if ($value -gt $peak) { $peak = $value }
    }
    [ordered]@{
        start = [long]$Samples[0].$Property
        end = [long]$Samples[-1].$Property
        peak_sampled = $peak
    }
}

$targetProcess = $null
try {
    $targetProcess = [System.Diagnostics.Process]::GetProcessById($ProcessId)
    # Opening the process handle pins the original process identity. Do not
    # reacquire by PID during sampling: Windows can reuse a PID after exit.
    $null = $targetProcess.Handle
    $processName = $targetProcess.ProcessName
    $processStartedAt = $targetProcess.StartTime.ToUniversalTime().ToString('o')
    $samples = [System.Collections.Generic.List[object]]::new()
    $first = Read-TargetSample -Target $targetProcess
    $samples.Add($first)
    $frequency = [double][System.Diagnostics.Stopwatch]::Frequency
    $deadlineTicks = $first.monotonic_ticks + ([double]$Seconds * $frequency)
    $status = 'completed'
    $interruption = $null

    while ([System.Diagnostics.Stopwatch]::GetTimestamp() -lt $deadlineTicks) {
        $remainingMs = ($deadlineTicks - [System.Diagnostics.Stopwatch]::GetTimestamp()) * 1000.0 / $frequency
        if ($remainingMs -gt 0) {
            Start-Sleep -Milliseconds ([Math]::Max(1, [Math]::Min(250, [int][Math]::Ceiling($remainingMs))))
        }
        try {
            $samples.Add((Read-TargetSample -Target $targetProcess))
        }
        catch {
            $status = 'interrupted'
            $interruption = 'The original target exited or its counters became inaccessible; only successful samples are included.'
            break
        }
    }

    $last = $samples[$samples.Count - 1]
    $elapsedSeconds = ($last.monotonic_ticks - $first.monotonic_ticks) / $frequency
    $cpuDeltaSeconds = $last.cpu_total_seconds - $first.cpu_total_seconds
    $oneCorePercent = $null
    $hostPercent = $null
    if ($samples.Count -gt 1 -and $elapsedSeconds -gt 0 -and $cpuDeltaSeconds -ge 0) {
        $oneCorePercent = [Math]::Round(100.0 * $cpuDeltaSeconds / $elapsedSeconds, 4)
        $hostPercent = [Math]::Round(100.0 * $cpuDeltaSeconds / $elapsedSeconds / $logicalProcessorCount, 4)
    }

    $publicSamples = foreach ($sample in $samples) {
        [ordered]@{
            elapsed_seconds = [Math]::Round(($sample.monotonic_ticks - $first.monotonic_ticks) / $frequency, 6)
            captured_at_utc = $sample.captured_at_utc
            cpu_total_seconds = $sample.cpu_total_seconds
            working_set_bytes = $sample.working_set_bytes
            private_bytes = $sample.private_bytes
            handle_count = $sample.handle_count
            thread_count = $sample.thread_count
        }
    }
    $report = [ordered]@{
        format = 'nevision-process-sample-v1'
        status = $status
        interruption = $interruption
        process_id = $ProcessId
        process_name = $processName
        process_started_at_utc = $processStartedAt
        measurement_started_at_utc = $first.captured_at_utc
        measurement_last_sample_at_utc = $last.captured_at_utc
        requested_seconds = $Seconds
        elapsed_seconds = [Math]::Round($elapsedSeconds, 6)
        sample_interval_ms = 250
        sample_count = $samples.Count
        logical_processor_count = $logicalProcessorCount
        logical_processor_count_source = $logicalProcessorSource
        cpu = [ordered]@{
            start_total_seconds = $first.cpu_total_seconds
            end_total_seconds = $last.cpu_total_seconds
            delta_seconds = [Math]::Round($cpuDeltaSeconds, 6)
            average_percent_of_one_logical_core = $oneCorePercent
            average_percent_of_total_logical_host = $hostPercent
        }
        working_set_bytes = Get-SampledMetric -Samples $samples.ToArray() -Property 'working_set_bytes'
        private_bytes = Get-SampledMetric -Samples $samples.ToArray() -Property 'private_bytes'
        handles = Get-SampledMetric -Samples $samples.ToArray() -Property 'handle_count'
        threads = Get-SampledMetric -Samples $samples.ToArray() -Property 'thread_count'
        limitations = @(
            'Only this original PID is measured; browser and other child processes are excluded.'
            'This is interval sampling of an already-running process, not cold-start or UI-readiness timing.'
            'Peak values are observed sample maxima, not lifetime peaks; short spikes may be missed.'
            'Working set is resident physical memory; private bytes are private committed memory, not necessarily resident RAM.'
            'One-core CPU can exceed 100 percent for multithreaded work. Host CPU divides by the reported logical processor count.'
            'A short interval cannot prove the absence of memory leaks or guarantee performance on other machines.'
        )
        samples = @($publicSamples)
    }

    $json = $report | ConvertTo-Json -Depth 7
    $stream = [System.IO.FileStream]::new($resolvedOutput, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        $encoding = [System.Text.UTF8Encoding]::new($false)
        $bytes = $encoding.GetBytes($json + [Environment]::NewLine)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush()
    }
    finally {
        $stream.Dispose()
    }
    Write-Output $json
}
finally {
    if ($null -ne $targetProcess) { $targetProcess.Dispose() }
}
