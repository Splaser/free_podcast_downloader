# batch_download_resume.ps1
# 自动批量下载 Listen Notes podcast，并支持中断续批

# 配置
$logFile = "last_offset.txt"     # 保存最后完成 offset
$batchSize = 5                   # 每批下载数量
$maxOffset = 1000                # 停止下载的最大 offset
$podcastUrl = "https://www.listennotes.com/zh-hans/podcasts/%E5%8F%8D%E6%B4%BE%E5%BD%B1%E8%AF%84-lamesbond-4VyasWUmn0T/"

# Python 执行路径
$pythonExe = "py"

# 从 log 文件读取上次 offset，如果不存在就用初始值
if (Test-Path $logFile) {
    $baseOffset = Get-Content $logFile | Select-Object -Last 1
    $baseOffset = [int]$baseOffset
    Write-Host "[INFO] Resuming from offset $baseOffset"
} else {
    $baseOffset = 290   # 初始 offset
    Write-Host "[INFO] Starting from initial offset $baseOffset"
}

# 循环批次下载
for ($offset = $baseOffset; $offset -lt $maxOffset; $offset += $batchSize) {

    Write-Host "=== Batch download: offset=$offset, latest=$batchSize ==="

    $args = @(
        "main.py",
        "--url", $podcastUrl,
        "--offset", $offset,
        "--latest", $batchSize
    )

    try {
        # 调用 Python 执行下载
        & $pythonExe @args

        # 下载成功，记录完成 offset
        $completedOffset = $offset + $batchSize
        Set-Content -Path $logFile -Value $completedOffset -Encoding UTF8
        Write-Host "[INFO] Batch completed, updated last_offset to $completedOffset"

    } catch {
        Write-Warning "[WARN] Batch at offset $offset failed or interrupted: $_"
        Write-Warning "[INFO] You can rerun the script, it will resume from $offset"
        break
    }

    # 可选：暂停 2 秒，避免服务器压力
    Start-Sleep -Seconds 2
}

Write-Host "[INFO] Script finished. Last completed offset stored in $logFile"