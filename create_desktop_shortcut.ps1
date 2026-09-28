param(
    [string]$TargetFolder = $PSScriptRoot,
    [string]$TargetPath = ""
)

if (-not $TargetFolder) {
    $TargetFolder = (Get-Location).Path
}

if (-not $TargetPath) {
    $exe = Get-ChildItem -Path $TargetFolder -Filter "Meraby_Block_Exchanger*.exe" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $exe) {
        # Builds published before the MBX rename.
        $exe = Get-ChildItem -Path $TargetFolder -Filter "SE_Tactical_Command*.exe" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
    }
    if ($exe) {
        $TargetPath = $exe.FullName
    }
    else {
        $Launcher = Join-Path $TargetFolder "launch.bat"
        if (-not (Test-Path $Launcher)) {
            $Launcher = Join-Path $TargetFolder "launch_gui.bat"
        }
        $TargetPath = $Launcher
    }
}

$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $DesktopPath "Meraby Block Exchanger.lnk"

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetPath
$Shortcut.WorkingDirectory = $TargetFolder
if ([IO.Path]::GetExtension($TargetPath) -ieq ".exe") {
    $Shortcut.IconLocation = "$TargetPath,0"
}
else {
    $iconFile = Join-Path $TargetFolder "app_icon.ico"
    if (Test-Path $iconFile) {
        $Shortcut.IconLocation = "$iconFile,0"
    }
}
$Shortcut.Description = "Meraby Block Exchanger - Offline blueprint toolkit"
$Shortcut.Save()

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   Meraby Block Exchanger Desktop Shortcut Created!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Shortcut location: $ShortcutPath"
Write-Host "Target: $TargetPath"
Write-Host ""
