# Free Podcast Downloader

一个用于归档公开播客单集音频的小工具。

当前版本主要支持从 **Listen Notes 单集页面**解析公开音频地址，下载 `.m4a` 文件，并尝试写入基础 metadata。

> 本项目只用于下载页面中已经公开暴露、可正常访问的免费播客音频资源。  
> 不用于绕过付费墙、会员权限、DRM 或其他访问控制。

## 当前功能

- 支持 Listen Notes 单集 URL
- 自动读取 Firefox / Chrome 浏览器 cookies
- 支持通过登录态降低 Cloudflare 403 概率
- 自动解析单集标题、播客名、封面、音频 URL
- 下载公开 `.m4a` 音频文件
- 自动按播客名建立目录
- 自动清理 Windows / macOS / Linux 文件名非法字符
- 使用 `mutagen` 写入 m4a metadata
- 支持只解析不下载
- 支持关闭 tag 写入
- 支持自定义输出目录

## 项目结构

```text
free_podcast_downloader/
├── main.py
├── probe.py
├── test_parse.py
├── test_download.py
├── requirements.txt
├── README.md
└── podcast_archiver/
    ├── __init__.py
    ├── session_utils.py
    ├── listen_notes.py
    ├── downloader.py
    ├── tagging.py
    └── filename.py
```

其中：

- `main.py`：正式 CLI 入口
- `probe.py`：调试页面结构、探测音频 URL 用
- `test_parse.py`：临时解析测试脚本
- `test_download.py`：临时下载测试脚本
- `podcast_archiver/session_utils.py`：浏览器 cookie/session 处理
- `podcast_archiver/listen_notes.py`：Listen Notes 页面解析
- `podcast_archiver/downloader.py`：音频下载逻辑
- `podcast_archiver/tagging.py`：m4a metadata 写入
- `podcast_archiver/filename.py`：文件名清理

## 安装

```shell
git clone <YOUR_REPO_URL>
cd free_podcast_downloader
pip install -r requirements.txt
```

如果还没有 `requirements.txt`，可以先写入：

```text
requests
beautifulsoup4
browser-cookie3
mutagen
```

然后执行：

```shell
pip install -r requirements.txt
```

## 使用前准备

Listen Notes 偶尔会触发 Cloudflare 403。

如果命令行请求返回 403，建议先在浏览器中打开目标 Listen Notes 页面，等待 Cloudflare checking 通过，确认页面可以正常访问，然后再运行工具。

推荐使用 Firefox：

```shell
python main.py --url "LISTEN_NOTES_EPISODE_URL" --browser firefox
```

也支持 Chrome：

```shell
python main.py --url "LISTEN_NOTES_EPISODE_URL" --browser chrome
```

工具会自动读取浏览器 cookie。成功时通常会看到类似输出：

```text
[INFO] firefox cookies loaded for listennotes.com
[INFO] cookie names: _ga, cf_clearance, csrftoken, g_state, sessionid
```

其中 `cf_clearance` 与 `sessionid` 通常有助于降低 403 概率。

## 基本用法

下载 Listen Notes 单集页面中的公开音频：

```shell
python main.py --url "https://www.listennotes.com/zh-hans/podcasts/..."
```

默认会保存到：

```text
downloads/<播客名>/<单集标题>.m4a
```

例如：

```text
downloads/反派影评/236《首尔之春》我会牢牢记住你的脸.m4a
```

## 指定输出目录

```shell
python main.py --url "https://www.listennotes.com/zh-hans/podcasts/..." --output "downloads"
```

也可以指定其他目录：

```shell
python main.py --url "https://www.listennotes.com/zh-hans/podcasts/..." --output "E:/Podcasts"
```

## 只解析，不下载

```shell
python main.py --url "https://www.listennotes.com/zh-hans/podcasts/..." --list
```

输出示例：

```text
title: 236《首尔之春》我会牢牢记住你的脸
podcast: 反派影评
author: 反派影评
cover: https://cdn-images-3.listennotes.com/...
audio: https://anchor.fm/...m4a
ext: .m4a
```

## 不写入 metadata

默认会尝试给 `.m4a` 文件写入 metadata。

如果只想下载原始文件，不写 tag：

```shell
python main.py --url "https://www.listennotes.com/zh-hans/podcasts/..." --no-tag
```

当前写入的 m4a metadata 包括：

- title
- artist
- album
- description
- cover

## 调试页面结构

如果某个页面解析失败，可以使用 `probe.py`：

```shell
python probe.py --url "https://www.listennotes.com/zh-hans/podcasts/..." --browser firefox
```

`probe.py` 会尝试输出：

- 页面标题
- 相关 `<a href>`
- HTML 中直接出现的 `.mp3` / `.m4a` 链接
- JSON script 中的音频 URL
- cover / image / play_url 等字段

这主要用于适配 Listen Notes 页面结构变化或其他公开播客页面。

## 常见问题

### 1. 为什么会 403？

Listen Notes 可能会启用 Cloudflare 风控。

解决方法：

1. 在 Firefox / Chrome 中打开目标页面；
2. 等待 Cloudflare checking 通过；
3. 确认网页可以正常显示；
4. 再运行命令，并指定同一个浏览器：

```shell
python main.py --url "URL" --browser firefox
```

如果仍然 403，可以重新刷新网页，或者登录 Listen Notes 账号后再试。

### 2. 为什么需要浏览器 cookies？

因为部分请求需要复用浏览器中已经通过 Cloudflare checking 的状态，例如：

- `cf_clearance`
- `sessionid`
- `csrftoken`

工具不会要求手动复制 cookie，而是通过 `browser-cookie3` 自动读取。

### 3. m4a 能不能写 tag？

可以。本项目使用 `mutagen.mp4.MP4` 写入 m4a metadata。

MP3 的 ID3 tag 工具如 `eyed3` 不适合直接用于 m4a。

### 4. 下载按钮弹出播放器而不是直接保存怎么办？

Listen Notes 页面中的下载按钮可能会打开 `.m4a` 播放器，而不是浏览器下载。

本工具会直接解析页面中的公开音频 URL，然后用 Python 下载到本地，因此不依赖浏览器的“打开/保存”行为。

### 5. 为什么标题解析错了？

Listen Notes 页面中可能存在多个 JSON script，里面既有播客名，也有单集名。

当前逻辑优先从页面 `<title>` 中解析单集标题，再用 JSON 作为补充。如果遇到特殊页面，可以用 `probe.py` 查看页面结构。

## 开发状态

当前版本定位：

```text
v0.1.0
支持 Listen Notes 单集页面下载公开 m4a，并写入基础 metadata。
```

已完成：

- Listen Notes 单集解析
- 浏览器 cookie/session 支持
- Cloudflare 通过后的 cookie 复用
- m4a 下载
- m4a metadata 写入
- 标准文件名保存
- CLI 入口

后续可选增强：

- RSS feed 解析
- 下载最新 n 期
- 批量下载播客全集
- 支持更多公开播客站点
- 支持 sidecar metadata.json
- 支持 `--convert-mp3`
- 支持断点续传
- 支持重写已有文件 metadata

## 使用边界

本工具只处理公开可访问的免费播客音频资源。

请勿用于：

- 绕过付费内容权限
- 绕过会员限制
- 绕过 DRM 或加密
- 大规模高频抓取
- 违反目标站点服务条款的用途

建议合理控制请求频率，并仅归档自己有权访问和保存的公开内容。
