param(
    [string]$Root = ".",
    [switch]$DryRun
)

<#
Batch regroup podcast files by filename prefix.

Examples:
  会员专享 第01期 为啥我只看没有女主角的战争电影？.mp3
=> 会员专享\01. 为啥我只看没有女主角的战争电影？.mp3

  会员专享 第82.5期 聊聊俄罗斯历史上的对外扩张.mp3
=> 会员专享\82.5. 聊聊俄罗斯历史上的对外扩张.mp3

  反攻欧陆 特辑：行动目标希特勒.m4a
=> 反攻欧陆\SP. 行动目标希特勒.m4a

  百战奇谋－海战 番外篇 腾飞聊海战.mp3
=> 百战奇谋－海战\SP. 腾飞聊海战.mp3

Usage:
  # preview only
  .\group_podcast_episodes_v2.ps1 -Root "downloads\袁腾飞频道" -DryRun

  # actually move
  .\group_podcast_episodes_v2.ps1 -Root "downloads\袁腾飞频道"
#>

$ErrorActionPreference = "Stop"

function Sanitize-PathPart {
    param([string]$Name)

    $invalid = [System.IO.Path]::GetInvalidFileNameChars()
    foreach ($ch in $invalid) {
        $Name = $Name.Replace($ch, "_")
    }

    $Name = $Name.Trim().TrimEnd(".", " ")

    if ([string]::IsNullOrWhiteSpace($Name)) {
        return "_"
    }

    return $Name
}

function Format-EpisodeNumber {
    param([string]$Raw)

    # 支持 82.5 这种半集
    if ($Raw -match '^(?<major>\d+)(?<minor>\.\d+)?$') {
        $majorRaw = $Matches["major"]
        $minor = $Matches["minor"]

        $major = ([int]$majorRaw).ToString(("0" * ([Math]::Max(2, $majorRaw.Length))))

        if ($minor) {
            return "$major$minor"
        }

        return $major
    }

    return $Raw
}

function Get-EpisodeRenameInfo {
    param([string]$BaseName)

    # 常规编号：
    # 会员专享 第01期 标题
    # 会员专享 第82.5期 标题
    # 百战奇谋 第35集 标题
    # 百战奇谋－海战 第13期 标题
    $numberedPatterns = @(
        '^(?<series>.+?)\s+第\s*(?<num>\d{1,4}(?:\.\d+)?)\s*(?<unit>集|期|回|话|讲|章)\s*(?<title>.+)$',
        '^(?<series>.+?)\s+EP\s*\.?\s*(?<num>\d{1,4}(?:\.\d+)?)\s*(?<title>.+)$',
        '^(?<series>.+?)\s+E\s*\.?\s*(?<num>\d{1,4}(?:\.\d+)?)\s*(?<title>.+)$',
        '^(?<series>.+?)\s+No\.?\s*(?<num>\d{1,4}(?:\.\d+)?)\s*(?<title>.+)$'
    )

    foreach ($pattern in $numberedPatterns) {
        $m = [regex]::Match($BaseName, $pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if ($m.Success) {
            $series = Sanitize-PathPart $m.Groups["series"].Value
            $num = Format-EpisodeNumber $m.Groups["num"].Value
            $title = Sanitize-PathPart $m.Groups["title"].Value

            return [pscustomobject]@{
                Matched = $true
                Series  = $series
                NewStem = "$num. $title"
            }
        }
    }

    # 特辑 / 番外篇：
    # 反攻欧陆 特辑：行动目标希特勒
    # 无风不起浪 特辑1：凡尔赛合约...
    # 百战奇谋－海战 番外篇 腾飞聊海战
    # 长子西征 番外篇 三个女人汗位戏
    $specialPatterns = @(
        '^(?<series>.+?)\s+特辑\s*(?<num>\d+)?\s*[：: ]\s*(?<title>.+)$',
        '^(?<series>.+?)\s+番外篇\s*(?<num>\d+)?\s*[：: ]?\s*(?<title>.+)$'
    )

    foreach ($pattern in $specialPatterns) {
        $m = [regex]::Match($BaseName, $pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if ($m.Success) {
            $series = Sanitize-PathPart $m.Groups["series"].Value
            $specialNum = $m.Groups["num"].Value
            $title = Sanitize-PathPart $m.Groups["title"].Value

            if ($specialNum) {
                $prefix = "SP" + (Format-EpisodeNumber $specialNum)
            } else {
                $prefix = "SP"
            }

            return [pscustomobject]@{
                Matched = $true
                Series  = $series
                NewStem = "$prefix. $title"
            }
        }
    }

    # 无编号但明显是同一栏目标题：
    # 一景一席谈 袁sir问你知道大阪城的秀吉吗？
    # 一景一席谈 还记得聪明一休吗？袁sir说金阁寺
    $namedSeriesPrefixes = @(
        "一景一席谈"
    )

    foreach ($prefixName in $namedSeriesPrefixes) {
        if ($BaseName.StartsWith($prefixName + " ")) {
            $title = $BaseName.Substring($prefixName.Length).Trim()
            $title = Sanitize-PathPart $title

            return [pscustomobject]@{
                Matched = $true
                Series  = Sanitize-PathPart $prefixName
                NewStem = $title
            }
        }
    }

    return [pscustomobject]@{
        Matched = $false
        Series  = $null
        NewStem = $null
    }
}

function Get-UniquePath {
    param([System.IO.FileInfo]$Target)

    if (-not (Test-Path -LiteralPath $Target.FullName)) {
        return $Target.FullName
    }

    $dir = $Target.DirectoryName
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($Target.Name)
    $ext = $Target.Extension

    $i = 1
    while ($true) {
        $candidate = Join-Path $dir ("{0} ({1}){2}" -f $stem, $i, $ext)
        if (-not (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
        $i++
    }
}

$rootPath = Resolve-Path -LiteralPath $Root
Write-Host "[INFO] root: $rootPath"
if ($DryRun) {
    Write-Host "[INFO] dry-run mode: no files will be moved"
}

$audioExts = @(".mp3", ".m4a", ".mp4")
$files = Get-ChildItem -LiteralPath $rootPath -File |
    Where-Object { $audioExts -contains $_.Extension.ToLowerInvariant() }

$moved = 0
$skipped = 0

foreach ($file in $files) {
    $info = Get-EpisodeRenameInfo -BaseName $file.BaseName

    if (-not $info.Matched) {
        Write-Host "[SKIP] no pattern: $($file.Name)"
        $skipped++
        continue
    }

    $seriesDir = Join-Path $rootPath $info.Series
    $newName = $info.NewStem + $file.Extension.ToLowerInvariant()
    $targetPath = Join-Path $seriesDir $newName

    if ($file.FullName -eq $targetPath) {
        Write-Host "[SKIP] already ok: $($file.Name)"
        $skipped++
        continue
    }

    $targetFile = New-Object System.IO.FileInfo($targetPath)
    $finalPath = Get-UniquePath -Target $targetFile

    Write-Host "[MOVE] $($file.Name)"
    Write-Host "   -> $($info.Series)\$(Split-Path $finalPath -Leaf)"

    if (-not $DryRun) {
        if (-not (Test-Path -LiteralPath $seriesDir)) {
            New-Item -ItemType Directory -Path $seriesDir | Out-Null
        }

        Move-Item -LiteralPath $file.FullName -Destination $finalPath
    }

    $moved++
}

Write-Host ""
Write-Host "[DONE] moved=$moved skipped=$skipped"
if ($DryRun) {
    Write-Host "[INFO] this was a dry run. Remove -DryRun to actually move files."
}
