<#
Watch project files and run scripts\auto_push.ps1 after changes (debounced).
Usage: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\watch_and_push.ps1
#>

param(
    [int]$DebounceSeconds = 2
)

Write-Host "Starting watcher (debounce ${DebounceSeconds}s). Press Ctrl+C to stop."

$root = Get-Location
$exclude = @('\.git\','\venv\','\node_modules\','.github\\workflows')

$timer = $null
$pending = $false

function ShouldIgnorePath($path) {
    foreach ($pattern in $exclude) {
        if ($path -match [regex]::Escape($pattern)) { return $true }
    }
    return $false
}

$watcher = New-Object System.IO.FileSystemWatcher $root.Path -Property @{ IncludeSubdirectories = $true; NotifyFilter = [System.IO.NotifyFilters]'FileName, LastWrite, DirectoryName'; Filter='*.*' }

$onEvent = {
    param($sender, $e)
    $full = $e.FullPath
    if (ShouldIgnorePath($full)) { return }
    $global:pending = $true
    if ($global:timer) { $global:timer.Stop() }
    $global:timer = New-Object Timers.Timer ($DebounceSeconds * 1000)
    $global:timer.AutoReset = $false
    $global:timer.add_Elapsed({
        if ($global:pending) {
            $global:pending = $false
            Write-Host "Changes detected. Running auto_push.ps1..."
            try {
                & .\scripts\auto_push.ps1 -Message "Auto commit: $(Get-Date -Format o)"
            } catch {
                Write-Warning "auto_push failed: $_"
            }
        }
    })
    $global:timer.Start()
}

$watcher.Changed.Add($onEvent)
$watcher.Created.Add($onEvent)
$watcher.Deleted.Add($onEvent)
$watcher.Renamed.Add($onEvent)

$watcher.EnableRaisingEvents = $true

try {
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    $watcher.Dispose()
    if ($timer) { $timer.Dispose() }
}
