# Free Podcast Downloader

一个偏个人归档取向的播客 / 音频下载工具。

当前项目已经从单一 Listen Notes 下载器，扩展成一个统一的 `--url` 入口工具。  
现在可以处理：

- RSS feed
- Listen Notes 单集页 / 播客列表页
- Typlog 单集页 / archive 页
- 微信公众号文章内音频
- 爱发电专辑 / 单条 post

> 本项目只用于归档页面中已经公开暴露、或你本人账号已有权限正常访问的音频资源。  
> 不用于绕过付费墙、会员权限、DRM、加密或其他访问控制。  
> 对需要登录态的网站，本项目只复用本机浏览器中已有 cookie，不提供破解、绕权或 token 伪造能力。

---

## 当前功能

- 统一 `--url` 入口，根据 URL 自动分发来源
- 支持 RSS feed 自动识别
- 支持 Listen Notes 单集 URL
- 支持 Listen Notes 播客列表页
- 支持 Listen Notes Load More API 翻页
- 支持 Typlog 单集页与 archive 批量下载
- 支持微信公众号 `mp.weixin.qq.com` 文章音频提取
- 支持爱发电 `ifdian.net / afdian.com`
  - `/album/{album_id}` 专辑批量归档
  - `/p/{post_id}` 单条音频归档
  - 浏览器 cookie 登录态复用
  - `--latest / --offset / --list`
- 自动读取 Firefox / Chrome 浏览器 cookies
- 支持通过登录态降低 Cloudflare 403 概率
- 自动解析标题、播客名 / 专辑名、作者、封面、音频 URL
- 自动按播客名 / 专辑名建立目录
- 自动清理 Windows / macOS / Linux 文件名非法字符
- 支持 `.mp3` / `.m4a` metadata 写入
- 支持只解析不下载
- 支持关闭 tag 写入
- 支持对已存在文件重新写 tag
- 支持自定义输出目录
- 支持 aria2 批量下载与多线程下载
- aria2 不可用时自动 fallback 到 requests
- 支持 HTTP Range 断点续传

---

## 项目结构

```text
free_podcast_downloader/
├── main.py
├── requirements.txt
├── README.md
└── podcast_archiver/
    ├── __init__.py
    ├── afdian.py
    ├── cli_handlers.py
    ├── downloader.py
    ├── filename.py
    ├── listen_notes.py
    ├── listen_notes_list.py
    ├── rss.py
    ├── session_utils.py
    ├── tagging.py
    ├── typlog.py
    └── wechat.py
```

主要模块说明：

- `main.py`：CLI 参数入口
- `podcast_archiver/cli_handlers.py`：URL 分发与各来源入口
- `podcast_archiver/afdian.py`：爱发电专辑 / post 解析
- `podcast_archiver/rss.py`：RSS feed 解析
- `podcast_archiver/listen_notes.py`：Listen Notes 单集页解析
- `podcast_archiver/listen_notes_list.py`：Listen Notes 播客列表页与 Load More API
- `podcast_archiver/typlog.py`：Typlog 页面解析
- `podcast_archiver/wechat.py`：微信公众号文章音频解析
- `podcast_archiver/downloader.py`：下载逻辑，含 aria2 / requests fallback
- `podcast_archiver/tagging.py`：mp3 / m4a metadata 写入
- `podcast_archiver/session_utils.py`：浏览器 cookie / session 处理
- `podcast_archiver/filename.py`：文件名清理

---

## 安装

```shell
git clone <YOUR_REPO_URL>
cd free_podcast_downloader
pip install -r requirements.txt
```

`requirements.txt` 至少应包含：

```text
requests
beautifulsoup4
browser-cookie3
mutagen
feedparser
```

如果需要用 Firefox / Chrome cookie，确保本机浏览器已经正常登录过目标站点。

---

## 可选依赖：aria2

如果系统安装了 `aria2c`，工具会自动启用 aria2 下载：

- 单文件多线程下载
- 批量任务下载
- 断点续传
- 大文件下载更稳定

检查是否可用：

```powershell
aria2c -v
```

如果未安装 aria2，工具会自动 fallback 到 Python requests 下载模式。

---

## 基本用法

### 统一 URL 入口

推荐后续统一使用：

```shell
python main.py --url "目标 URL"
```

工具会根据 URL 自动判断来源：

```shell
python main.py --url "https://siji.typlog.io/feed.xml" --latest 5
python main.py --url "https://www.listennotes.com/zh-hans/podcasts/..."
python main.py --url "https://ifdian.net/album/xxxx" --latest 5
python main.py --url "https://ifdian.net/p/xxxx"
python main.py --url "https://mp.weixin.qq.com/s/xxxx"
```

旧的 `--rss` 入口仍然可以保留使用：

```shell
python main.py --rss "RSS_URL" --latest 5
```

但日常使用建议统一走 `--url`。

---

## RSS feed

RSS URL 会自动识别，例如：

```shell
python main.py --url "https://siji.typlog.io/feed.xml" --latest 5 --list
```

下载最新 5 条：

```shell
python main.py --url "https://siji.typlog.io/feed.xml" --latest 5
```

全量归档：

```shell
python main.py --url "https://siji.typlog.io/feed.xml" --all
```

带 offset：

```shell
python main.py --url "https://siji.typlog.io/feed.xml" --offset 20 --latest 10
```

RSS 默认按发布时间从新到旧排序。

---

## Listen Notes

### 单集页面

```shell
python main.py --url "https://www.listennotes.com/zh-hans/podcasts/..."
```

只解析不下载：

```shell
python main.py --url "https://www.listennotes.com/zh-hans/podcasts/..." --list
```

### 播客列表页

```shell
python main.py --url "https://www.listennotes.com/zh-hans/podcasts/播客名-xxxx/" --latest 10
```

Listen Notes 列表页支持：

```shell
--latest n
--offset n
--max-pages n
--all
--list
```

例如：

```shell
python main.py --url "LISTEN_NOTES_PODCAST_URL" --latest 30 --max-pages 3
```

如果 Listen Notes 触发 Cloudflare 403，可以先在浏览器打开页面，通过检查后再运行：

```shell
python main.py --url "LISTEN_NOTES_URL" --browser firefox
```

也可以使用 Chrome：

```shell
python main.py --url "LISTEN_NOTES_URL" --browser chrome
```

---

## 爱发电

支持 `ifdian.net` 和 `afdian.com`。

### 专辑下载

先 list 测试：

```shell
python main.py --url "https://ifdian.net/album/你的album_id" --latest 3 --list
```

下载最新 3 条：

```shell
python main.py --url "https://ifdian.net/album/你的album_id" --latest 3
```

全量归档：

```shell
python main.py --url "https://ifdian.net/album/你的album_id"
```

带 offset：

```shell
python main.py --url "https://ifdian.net/album/你的album_id" --offset 20 --latest 10
```

### 单条 post

只解析：

```shell
python main.py --url "https://ifdian.net/p/你的post_id" --list
```

下载：

```shell
python main.py --url "https://ifdian.net/p/你的post_id"
```

### 爱发电 cookie

爱发电内容通常需要登录态。  
推荐先在 Firefox 中打开目标专辑或 post，确认浏览器里能正常访问，再运行：

```shell
python main.py --url "https://ifdian.net/album/你的album_id" --browser firefox --latest 3
```

也支持 Chrome：

```shell
python main.py --url "https://ifdian.net/album/你的album_id" --browser chrome --latest 3
```

工具会自动复用本机浏览器 cookie。  
如果出现空列表、`40100`、没有 audio 字段，通常优先检查 cookie 是否过期，或者先在浏览器中刷新对应页面。

---

## Typlog

### 单集页面

```shell
python main.py --url "https://siji.typlog.io/episodes/xxxx"
```

### archive 批量

```shell
python main.py --url "https://siji.typlog.io/archive/2024"
```

Typlog archive 会从页面中收集 `/episodes/` 链接并逐条下载。

如果站点提供 RSS，优先建议走 RSS：

```shell
python main.py --url "https://siji.typlog.io/feed.xml" --latest 10
```

---

## 微信公众号音频

支持从 `mp.weixin.qq.com` 文章中提取语音音频：

```shell
python main.py --url "https://mp.weixin.qq.com/s/xxxx" --list
```

下载：

```shell
python main.py --url "https://mp.weixin.qq.com/s/xxxx"
```

当前微信公众号音频暂不统一写入 MP3 tag，下载时会提示 skipped。

---

## 输出目录

默认保存到：

```text
downloads/<播客名或专辑名>/<单集标题>.<ext>
```

例如：

```text
downloads/反派影评/236《首尔之春》我会牢牢记住你的脸.m4a
downloads/某爱发电专辑/第001期 xxxx.mp3
```

指定输出目录：

```shell
python main.py --url "URL" --output "E:/Podcasts"
```

---

## 常用参数

### `--list`

只解析，不下载：

```shell
python main.py --url "URL" --list
```

### `--latest n`

取最新 n 条：

```shell
python main.py --url "RSS_OR_ALBUM_OR_LIST_URL" --latest 5
```

### `--offset n`

跳过前 n 条：

```shell
python main.py --url "URL" --offset 20 --latest 10
```

### `--all`

全量归档。  
RSS 和 Listen Notes 列表页常用：

```shell
python main.py --url "RSS_URL" --all
```

爱发电 album 不传 `--latest` 时默认就是全量归档。

### `--no-tag`

只下载，不写 metadata：

```shell
python main.py --url "URL" --no-tag
```

### `--retag-existing`

文件已存在时重新写 metadata：

```shell
python main.py --url "URL" --retag-existing
```

### `--browser`

指定读取哪个浏览器 cookie：

```shell
python main.py --url "URL" --browser firefox
python main.py --url "URL" --browser chrome
```

---

## Metadata 写入

当前支持：

### m4a / mp4

- title
- artist
- album
- description
- cover

### mp3

- title
- artist
- album
- comment / description
- cover

如果文件已存在，并且已有基础 title / artist / album，默认跳过重新写 tag。  
需要强制重写时使用：

```shell
python main.py --url "URL" --retag-existing
```

---

## 常见问题

### 1. 为什么 Listen Notes 会 403？

Listen Notes 可能启用 Cloudflare 风控。

解决方法：

1. 在 Firefox / Chrome 中打开目标页面；
2. 等待 Cloudflare checking 通过；
3. 确认网页可以正常显示；
4. 再运行命令，并指定同一个浏览器：

```shell
python main.py --url "URL" --browser firefox
```

### 2. 为什么爱发电返回空列表？

常见原因：

- 浏览器 cookie 过期；
- 当前浏览器没有登录爱发电；
- 当前账号没有访问该专辑 / post 的权限；
- 请求过快触发风控；
- 页面结构或接口返回结构变化。

建议先在浏览器中打开目标 URL，确认能正常播放，再运行命令。

### 3. RSS 是否需要翻页？

通常不需要。  
标准 RSS feed 一般就是一次性返回当前 feed 内所有 item。  
本项目会一次拉取 feed 内容，然后在本地做 `--latest / --offset / --all` 切片。

### 4. 为什么下载按钮弹出播放器而不是直接保存？

很多站点的下载按钮实际只是打开音频 URL。  
本工具会直接解析页面或 feed 中的音频地址，然后用 Python / aria2 下载到本地，不依赖浏览器的“打开/保存”行为。

### 5. 为什么标题解析错了？

不同站点页面结构差异很大。  
如果发现标题、封面、作者错位，可以先用 `--list` 看解析结果，再针对对应 parser 微调。

---

## 开发状态

当前版本定位：

```text
v0.3.0
统一 URL 入口，支持 RSS / Listen Notes / Typlog / WeChat / Afdian，
并接入 aria2 下载、requests fallback、断点续传与 mp3/m4a metadata 写入。
```

已完成：

- 统一 `--url` 分发入口
- RSS feed 自动识别
- RSS feed 解析与批量归档
- Listen Notes 单集解析
- Listen Notes 播客列表页解析
- Listen Notes Load More API 翻页
- Typlog 单集与 archive 页面解析
- WeChat mp.weixin 音频提取
- 爱发电 album / post 解析
- 爱发电浏览器 cookie 登录态复用
- 浏览器 cookie/session 支持
- Cloudflare 通过后的 cookie 复用
- aria2 多线程下载
- aria2 批量下载
- requests fallback 下载
- HTTP Range 断点续传
- mp3 / m4a metadata 写入
- 标准文件名保存
- offset/latest/all 批量归档
- CLI 入口

后续可选增强：

- 支持更多公开播客站点
- 支持 sidecar `metadata.json`
- 支持下载记录数据库，避免重复扫描
- 支持更细的站点识别规则
- 支持 `--convert-mp3`
- 支持归档后自动生成本地 RSS feed

---

## 使用边界

本工具只处理公开可访问，或你本人账号已有权限正常访问的音频资源。

请勿用于：

- 绕过付费内容权限
- 绕过会员限制
- 绕过 DRM 或加密
- 伪造 token 或绕过登录态
- 大规模高频抓取
- 违反目标站点服务条款的用途

建议合理控制请求频率，并仅归档自己有权访问和保存的内容。
