param(
    [string]$Message = "Sample task",
    [int]$Count = 3,
    [int]$DelayMs = 600
)

Write-Output "Script started: $Message"

for ($index = 1; $index -le $Count; $index++) {
    Write-Output "Processing step $index of $Count"
    Start-Sleep -Milliseconds $DelayMs
}

Write-Output "Script finished successfully."
