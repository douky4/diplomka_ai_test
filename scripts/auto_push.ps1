param(
    [string]$Message = "Auto commit by assistant"
)

$branch = git rev-parse --abbrev-ref HEAD
git add -A
git commit -m $Message
git push origin $branch

Write-Host "Committed and pushed to branch: $branch"
