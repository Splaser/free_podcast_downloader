# batch_download.ps1
# 自动往后推进批量下载 Listen Notes podcast
# 使用方法: 直接修改 $baseOffset 即可从该 offset 开始

# 配置
$baseOffset = 285          # 当前起始 offset
$batchSize = 5             # 每批下载数量
$maxOffset = 1000           # 停止下载的最大 offset，可根据实际情况调整
$podcastUrl = "https://www.listennotes.com/zh-hans/podcasts/%E5%8F%8D%E6%B4%BE%E5%BD%B1%E8%AF%84-lamesbond-4VyasWUmn0T/"

# Python 执行路径，如果 py 可以直接使用则不用修改
$pythonExe = "py"

# 循环批次下载
for ($offset = $baseOffset; $offset -lt $maxOffset; $offset += $batchSize) {

    Write-Host "=== Batch download: offset=$offset, latest=$batchSize ==="

    $args = @(
        "main.py",
        "--url", $podcastUrl,
        "--offset", $offset,
        "--latest", $batchSize
    )

    # 调用 Python 执行下载
    & $pythonExe @args

    # 可选：暂停 2 秒，避免服务器压力
    Start-Sleep -Seconds 2
}