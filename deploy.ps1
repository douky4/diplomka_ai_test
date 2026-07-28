# Deploy the current repository to GitHub Pages
# Usage: .\deploy.ps1

function Get-GitRemoteInfo {
    $remoteUrl = git config --get remote.origin.url 2>$null
    if (-not $remoteUrl) { return $null }

    if ($remoteUrl -match 'github\.com[/:](?<owner>[^/]+)\/(?<repo>[^/.]+)(?:\.git)?$') {
        return @{ Owner = $matches.owner; Repo = $matches.repo }
    }
    return $null
}

Write-Host "Checking git repository..."
if (-not (git rev-parse --is-inside-work-tree 2>$null)) {
    Write-Error "This directory is not a git repository."
    exit 1
}

$currentBranch = git branch --show-current
if (-not $currentBranch) {
    Write-Error "Unable to determine current git branch."
    exit 1
}

Write-Host "Current branch: $currentBranch"

$changes = git status --short
if (-not [string]::IsNullOrWhiteSpace($changes)) {
    Write-Host "Staging all changes..."
    git add .

    $commitMessage = Read-Host "Enter commit message for deployment (or press Enter for default)"
    if ([string]::IsNullOrWhiteSpace($commitMessage)) {
        $commitMessage = "Deploy site"
    }

    git commit -m $commitMessage
} else {
    Write-Host "No local changes to commit."
}

Write-Host "Pushing branch '$currentBranch' to origin..."
git push origin $currentBranch
if ($LASTEXITCODE -ne 0) {
    Write-Error "Git push failed. Fix the error and try again."
    exit 1
}

$remoteInfo = Get-GitRemoteInfo
if (-not $remoteInfo) {
    Write-Warning "Could not parse GitHub remote URL; skipping GitHub Pages configuration."
    exit 0
}

if (Get-Command gh -ErrorAction SilentlyContinue) {
    Write-Host "GitHub CLI detected. Configuring GitHub Pages from branch '$currentBranch'..."
    $body = @{
        source = @{ branch = $currentBranch; path = "/" }
    } | ConvertTo-Json

    gh api -X PUT "/repos/$($remoteInfo.Owner)/$($remoteInfo.Repo)/pages" -f source.branch=$currentBranch -f source.path=/ | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "GitHub Pages configuration updated for branch '$currentBranch'."
        Write-Host "Your site should be available shortly at https://$($remoteInfo.Owner).github.io/$($remoteInfo.Repo)/"
    } else {
        Write-Warning "Failed to configure GitHub Pages via gh. You may need to enable it manually in repository settings."
    }
} else {
    Write-Host "GitHub CLI not installed, skipping automatic Pages setup."
    Write-Host "If you want, install gh and run this script again, or enable Pages manually in GitHub repository settings."
}
