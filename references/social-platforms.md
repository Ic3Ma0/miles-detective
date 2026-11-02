# 社交平台取材

社交媒体上的本人发言、时间线和同期反应，常常只在登录后才可见。这一页说明怎样把平台公开内容读成可引用正文，以及读不到时怎样记录。它是方法说明，不是“所有平台都能抓”的承诺；平台策略会变，运行时核验。

## 先分清取回层级

| 实际看到 | visit.outcome | source.access |
|---|---|---|
| 登录页、安全验证、只有页头页脚 | `shell` | 不建来源，或 `unretrieved` |
| 摘要、预览、截断正文 | `partial` | `partial_text` |
| 实际读到帖子正文 | `content` | `full_text` |

未登录返回的导航壳和验证页不是正文，不能记成 `content`；“没登录”也不能写成“平台封禁”。同一 URL 的失败与后来成功的访问分别记录，旧记录不覆盖。

## 三条通路

### 1. 公开接口（优先，成本最低）

- 微博：`https://m.weibo.cn/u/<uid>` 由服务端渲染，未登录可读公开时间线与正文。连续请求会返回 432，降低频率、单轮少页。
- B 站：`https://api.bilibili.com/x/web-interface/view?bvid=<BV>` 返回标题、UP 主、发布时间、播放量；用户粉丝数用 `x/relation/stat?vmid=`。字幕需要登录 cookie。
- 页面内嵌数据（如 `__INITIAL_STATE__`）可用来判断是否有正文，不默认等于完整。

### 2. 登录态浏览器（知乎、小红书、X、抖音）

一次人工登录，profile 长期复用；之后无头读取。脚本 `scripts/social_fetch.py`：

```bash
python3 scripts/social_fetch.py login zhihu
python3 scripts/social_fetch.py status
python3 scripts/social_fetch.py fetch "https://www.zhihu.com/question/xxxx"
```

登录态保存在 `~/.config/miles-detective/browser-profile`；失效时抓取输出 `LOGIN_REQUIRED`，重跑对应 `login`。遇到滑块时给 `fetch` 加 `--headed` 人工过一次。X 在部分网络环境无法直连，需要可用的系统代理。

### 3. 批量采集（MediaCrawler）

覆盖小红书、抖音、快手、B 站、微博、贴吧、知乎；**不含 X**。许可证为 NON-COMMERCIAL LEARNING LICENSE 1.1：仅限个人学习研究，不得用于商业交付；装之前先确认用途。

它通过 CDP 连接已登录的 Chrome，复用现有登录态。前提：Chrome 打开 `chrome://inspect/#remote-debugging`，勾选允许远程调试；运行时浏览器弹确认框，点接受。

```bash
python3 scripts/mediacrawler.py --root <MediaCrawler 目录> xhs search "人物名" --limit 20
python3 scripts/mediacrawler.py --root <MediaCrawler 目录> zhihu detail "<回答或文章 URL>"
```

输出 JSONL 到 `--data-dir`（默认 `~/.config/miles-detective/mc-data`），按平台分目录。

### 4. 写入案例台账

```bash
python3 scripts/mc_to_records.py --case research/R011-人物 --platform zhihu --data-dir <数据目录>
python3 scripts/research_log.py check research/R011-人物
```

每条内容生成一条 `visit` 和一条 `source`，原始 JSONL 复制到案例 `raw/`，按 URL 去重，重复运行不会重复写入。

## 记录要点

- 昵称、ID 可能被平台打码（如“半\*\*\*书”），按原样记录，不补全。
- 时间戳可能是秒或毫秒；转换脚本按数值大小判断，写库前抽查年份。
- 互动数（点赞、评论、转发）是抓取时刻的快照，引用时注明抓取日期。
- 搜索命中只算发现；正文必须实际取回才能升级为来源。
- 账号归属要单独核验：认证、组织官网外链、同期采访互链；认证不能证明旧帖未改。

## 失败对照

| 现象 | 判定 | 处理 |
|---|---|---|
| 跳登录页、安全验证 | 登录墙，未取回 | 先登录；或换登录态浏览器 |
| 只有页脚/导航 | 壳页面 | 换移动版、公开接口或登录态 |
| 432 / 429 | 频率限制 | 降频、暂停该支线一轮 |
| 403 + 空页面 | 浏览器指纹或风控 | 用真实浏览器登录态重试 |
| 日期变成 1970 | 时间戳单位误判 | 按秒/毫秒修正后记录 |

## 边界

只取公开内容；不碰私信、付费内容、私密账号；不绕过访问控制；平台条款与频率限制自行遵守。登录态是本人账号，profile 目录不外传、不提交到仓库。
