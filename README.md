# Free Podcast Downloader

一个自用优先的播客 / 音频归档工具。

核心目标很简单：给一个 URL，尽量自动解析音频、下载文件、写入 metadata，并按播客或专辑目录保存。

支持来源：

- RSS feed
- Listen Notes
- Typlog
- 爱发电 `ifdian.net / afdian.com`
- 微信公众号文章音频

> 本项目只用于归档公开可访问，或你本人账号已有权限正常访问的音频资源。  
> 不用于绕过付费墙、会员权限、DRM、加密或其他访问控制。

---

## 安装

```shell
git clone <本项目>
cd free_podcast_downloader
pip install -r requirements.txt
```

可选安装 `aria2c`。如果系统检测到 aria2，下载时会优先使用；没有也可以正常用 Python requests 下载。

---

## 基本用法

推荐统一使用 `--url`：

```shell
python main.py --url "URL"
```

先解析不下载：

```shell
python main.py --url "URL" --list
```

下载最新 5 条：

```shell
python main.py --url "URL" --latest 5
```

指定输出目录：

```shell
python main.py --url "URL" --output "E:/Podcasts"
```

---

## 常用示例

### RSS

```shell
python main.py --url "https://siji.typlog.io/feed.xml" --latest 5 --list
python main.py --url "https://siji.typlog.io/feed.xml" --latest 5
python main.py --url "https://siji.typlog.io/feed.xml" --all
```

RSS 会自动识别，不一定要单独使用 `--rss`。

如果系统安装了 aria2，RSS 批量下载会优先走 aria2 batch。下载完成后，程序会统一写入 metadata。

如果中途 `Ctrl+C` 停止任务，可以直接重跑同一条命令。已存在的文件会跳过下载；缺少 tag 或封面的文件可以继续补写。

### 爱发电

专辑：

```shell
python main.py --url "https://ifdian.net/album/你的album_id" --latest 3 --list
python main.py --url "https://ifdian.net/album/你的album_id" --latest 3
```

全量归档：

```shell
python main.py --url "https://ifdian.net/album/你的album_id"
```

单条 post：

```shell
python main.py --url "https://ifdian.net/p/你的post_id" --list
python main.py --url "https://ifdian.net/p/你的post_id"
```

爱发电通常需要登录态。建议先在浏览器中打开目标页面，确认账号能正常访问，再运行：

```shell
python main.py --url "https://ifdian.net/album/你的album_id" --browser firefox --latest 3
```

也可以使用 Chrome：

```shell
python main.py --url "https://ifdian.net/album/你的album_id" --browser chrome --latest 3
```

### Listen Notes

单集或列表页都走 `--url`：

```shell
python main.py --url "https://www.listennotes.com/zh-hans/podcasts/..." --list
python main.py --url "https://www.listennotes.com/zh-hans/podcasts/..." --latest 10
```

如果遇到 403，先用浏览器打开页面，通过检查后再运行：

```shell
python main.py --url "LISTEN_NOTES_URL" --browser firefox
```

### Typlog

```shell
python main.py --url "https://siji.typlog.io/episodes/xxxx"
python main.py --url "https://siji.typlog.io/archive/2024"
```

如果站点提供 RSS，优先建议走 RSS：

```shell
python main.py --url "https://siji.typlog.io/feed.xml" --latest 10
```

### 微信公众号音频

```shell
python main.py --url "https://mp.weixin.qq.com/s/xxxx" --list
python main.py --url "https://mp.weixin.qq.com/s/xxxx"
```

---

## 常用参数

| 参数 | 作用 |
| --- | --- |
| `--url URL` | 统一 URL 入口 |
| `--rss URL` | 兼容旧用法，直接指定 RSS feed |
| `--list` | 只解析，不下载 |
| `--latest n` | 取最新 n 条 |
| `--offset n` | 跳过前 n 条 |
| `--all` | 全量归档，RSS / Listen Notes 常用 |
| `--output DIR` | 指定输出目录 |
| `--browser firefox/chrome` | 读取指定浏览器 cookie |
| `--no-tag` | 只下载，不写 metadata |
| `--retag-existing` | 文件已存在时重新写 metadata |
| `--fix-cover` | 只给缺少内嵌封面的已存在文件补 cover |

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

---

## Metadata

当前支持给 `.mp3` / `.m4a` 写入基础信息：

- title
- artist
- album
- description / comment
- cover

如果文件已存在且已有基础 tag，默认会跳过。需要强制重写时使用：

```shell
python main.py --url "URL" --retag-existing
```

如果只想补缺失封面，可以使用：

```shell
python main.py --url "URL" --fix-cover
```

`--fix-cover` 会检查已存在文件是否带有内嵌封面；已有封面的文件会跳过，缺少封面的文件会尝试补写。

封面处理顺序：

1. 优先使用 RSS / API 提供的远程封面；
2. 如果远程封面失效或返回 403，尝试从同目录、同标题前缀的已有文件中复用封面；
3. 如果仍然找不到，则只保留基础 metadata，不阻断任务。

这对一些旧 RSS 中已经失效的封面链接比较有用。

---

## 简单排错

遇到解析失败，先用：

```shell
python main.py --url "URL" --list
```

爱发电返回空列表时，优先检查：

- 浏览器是否已登录；
- 当前账号是否有权限访问；
- 是否需要在浏览器中刷新一次目标页面；
- 是否指定了正确浏览器，例如 `--browser firefox`。

Listen Notes 403 时，先在浏览器里打开页面，通过 Cloudflare 检查后再运行。

RSS 一般不需要翻页，工具会一次拉取 feed 内容，然后在本地做 `--latest / --offset / --all` 切片。

如果 RSS 全量下载中途停止，可以重跑同一条命令。已下载文件会跳过，未完成文件会继续处理。对于已下载但缺少封面的文件，可以使用：

```shell
python main.py --url "RSS_URL" --all --fix-cover
```

---

## 使用边界

本工具只处理公开可访问，或你本人账号已有权限正常访问的音频资源。

请勿用于：

- 绕过付费内容权限；
- 绕过会员限制；
- 绕过 DRM 或加密；
- 伪造 token 或绕过登录态；
- 大规模高频抓取；
- 违反目标站点服务条款的用途。
