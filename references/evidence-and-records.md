# 证据、获取与记录

## 记录层级

把发现、访问、材料、结论分开。发现的 URL 可以永远打不开；打开主页也可能只得到导航壳；同一个来源可以有多次失败和后来成功的访问，旧记录不覆盖。

| 项目 | 最少记录 |
|---|---|
| 检索 | 查询原文、搜索工具/索引、实际时间、范围/筛选、返回原始结果的本地路径 |
| 访问 | 请求 URL/点击所来自的页面、方法、实际时间、重定向终点（若知道）、结果层级、具体错误/限制、原始输出位置 |
| 来源 | 稳定编号、标题、作者/发布者、URL、本人/他者/混合、原文/转载/引用/编目/节目说明/机构记录、日期、获取层级、身份依据、同源组、支持范围与限制 |
| 结论 | 原子化陈述、属于事实/有人如此声称/争议/推断、证据编号、正文/页码/时间点定位、相反证据与不确定性 |
| 线索 | 从哪里发现、待解问题、下一步、优先级、开放/受阻/已解决/暂停及原因 |
| 覆盖 | 适用来源家族和时段、实际检索及读取范围、未查/已搜/部分取得/受阻/暂停/不适用、遗漏原因及下一步 |

保留工具返回原文于案例工作目录；面向读者提供摘要、短引文和定位，不批量复制整本书或完整节目字幕。日志中不保存登录凭据或无关私人联系方式。

保存网页时同时保留正文与链接表：锚文本、完整 `href`、所在标题或段落。只做纯文本抽取会丢掉原文、附件和旧域名地址。交付前用 `scripts/extract_links.py` 回扫每个保存的 HTML，把结果与台账、来源目录和线索队列对照；页面里有而台账里没有的地址，补成线索或写明为何不用。

案头核读时没有检索和访问记录，不要为凑结构补假记录；若台账需要覆盖记录，写一条「按提供材料核读」，材料清单保留原始取得层级。案头核读仍可用 `records.jsonl` 记来源、结论、事件、线索和覆盖，或用事件的 `sources` 文件定位；没有检索/访问记录不等于不能记事件。合并总卷时，按交付格式逐段标注继承、重读、新增与修正。

## 身份与来源独立性

对账号归属分为：confirmed（强公开关联，如组织原始公告指向本人账号）、supported（同期可核对的资料支持）、unresolved（仅同名或未经核对）、not_applicable（无需绑定人物的编目/机构记录）。记录实际依据，等级只是摘要。更名/转让/仿冒风险按相关日期检查，不能把2011年的归属推广到所有时期。姓名异体、同音形近字和语音转录错字分别检索，引用时保留原始页面用字。

对同一篇稿件的几十个转载设置同源组；同一采访的中英文版、剪辑与全文也不算独立目击。本人网站与其新闻稿不构成两份独立认证。AI 汇总中链接再多，也须逐个打开；反过来，古老论坛的准确原帖可能比今天的权威媒体转述更接近现场。

## 获取层级与表述

- 搜索摘要：写“检索命中”，只建线索。摘要可能拼接、过期或来自别处。
- 摘要引语：摘要里的直接引语必须回链到已打开页面；打开后找不到该句，整条引语作废，不能保留半句，也不能改写成间接引语。摘要与原文冲突时以原文为准，并记下差异。
- 编目/节目介绍：写“读到书目/目录/节目说明”，只能支持作者字段、页面记载日期、题目及话题安排等可见信息。
- 部分正文：标明节选、预览、登录截断、只读某章节、字符异常或只取得部分工具窗口。不能称全文。
- 全文：确认实际正文可见并已读相关内容；分页、附件和续篇另核。不是因为工具标记 total lines 就默认完整。
- 字幕/录音/视频：写明来源、自动/人工、语言和核验时间范围。只有节目时间轴时不能重构受访者回答。无法播放应明确未核听；未运行字幕工具不能写“字幕提取失败”。
- OCR/转写：保存原件定位，关键人名、数字、否定词回看/核听。乱码、字体映射异常不能凭语感修成直接引语。

来源访问状态与证据类型不能混在一个“可信度”分数里。机构公告证明公告内容，未必证明公告中转述的业绩；原始指控证明有人提出指控，未必证明指控属实。

## 结论状态

`claim.status` 不是可信度分数，而是这条陈述目前的证据关系。标 `corroborated` 前逐条回答：

1. **两个来源是否各自独立取得？** 同一稿件的转载、同一采访的全文/剪辑/翻译、同一机构的通稿与转载、同一作者改写，只算一组。
2. **两个来源是否都指向同一原始材料？** 如果是，仍是单源。台账里有两个编号，不等于两份独立证据。
3. **两个来源支持的是同一原子陈述吗？** 把“公司宣布收购”和“收购完成”拆开；不能用前者支持后者。
4. **两个来源是否有相同的利益关系，或由同一方提供？** 同一方声明经两家媒体转述，不构成独立证实。

只有两个独立来源都支持同一原子陈述，才用 `corroborated`；否则用 `documented_statement`（材料确实这样记载）或 `disputed`（有实质相反证据）。`documented_statement` 不表示叙述为真，`disputed` 也不表示双方各错一半。标 `corroborated` 时，在 `evidence` 里列出这两个来源，并在来源记录中写明同源组。

## 日期、版本和摘记

分别写事件时间、录制时间、原发时间、转载时间、存档抓取时间、当前访问时间。只知道一种就只填一种；有时区时保留，不自行补时区。旧网页底部当前年份、搜索引擎“几年前”不能替代文章日期。

每个重要摘记保留说话者、上下文、内容定位和适用范围。受访者回答、主持人追问、编辑导语、记者旁白与讽刺/虚构对白分开。本人公开小说中的第一人称不自动等于自传事实。

为了写人生故事，摘记还应保留能支撑场景的具体内容：时间、地点、在场者、行动、物件、原话、当时公开表达的愿望与后来解释，并与来源逐项对应。写作时读取 [人生叙事方法](life-story.md)，不从时代常识补出人物经历，不把事后回忆伪装成同期观察。缺少支持的细节返回调查队列或省略。

身份、学校、金额、公司控制权、任职和诉讼状态冲突时并列双方依据，不无声覆盖。必要时找版权页、公告附件、案号和后续裁定。提出解释时给出支持及替代解释，避免把言行差异写成已知心理动机。

## 访问障碍要具体、可解决

记录目标 URL、访问工具/层级、时间、返回的错误文字或可见现象、实际尝试过的替代入口、影响哪些问题、最小帮助。例：

> B站某 BV 链接，本次网页提取返回 412，视频未核听；制作方节目页有标题与时间轴。需要该集公开字幕导出或用户提供可读取的授权文本，才能核验 25:40 的回答。登录浏览器未试，不把它算作失败。

只在确实需要用户帮助时提出具体请求，不笼统说“接口爬不到”。超时、403、429、解析为空、付费预览、身份未明是不同问题；不要把工具解析失败断言为平台封禁，不为了凑尝试次数反复请求同一个失败入口。可用的替代途径包括制作方、正版试读、RSS、公开文稿、已授权浏览器；不绕过控制。用户暂缓则记暂停与原因，推进独立问题。

## 附带脚本与字段

案例目录与技能目录分开，按 `research/<案例编号>-<人物>/` 建立：`records.jsonl` 是脚本维护的主台账，`raw/` 按批次保存工具原始返回（如 `B01.json`），`outputs/` 放本轮交付物，文件名带案例编号与轮次。并行调查时，每个分片另写 `shards/<分片 ID>/records.jsonl`、`shards/<分片 ID>/raw/`、`shard.json` 与 `findings.md`，再由协调者合并；见 [并行调查](parallel-investigation.md)。打包技能时只含技能目录，不把案例卷进去，个案事实不写回本技能。

`scripts/research_log.py` 仅用 Python 标准库。日志是 UTF-8 JSONL，每条事件追加 `recorded_at` 和递增 `event_id`，同 kind/id 的后续事件是更新快照，前一事件仍保留。单个台账串行写入；并行调查时 worker 只写自己的分片台账，协调者用 `merge` 合成主台账，不能让多个 worker 并发写同一个 `records.jsonl`。

```bash
python3 <技能目录>/scripts/research_log.py init <案例目录> --person '人物名' --scope '本轮范围'
python3 <技能目录>/scripts/research_log.py append <案例目录> --input <记录.json>
python3 <技能目录>/scripts/research_log.py check <案例目录>
python3 <技能目录>/scripts/research_log.py report <案例目录> --output <摘要.md>
python3 <技能目录>/scripts/research_log.py merge <案例目录> [--report <路径>] [--dry-run]
```

`merge` 只用于并行调查：先逐个校验分片台账，再统一编号、重写引用与 `raw_path`、按完整 URL 去重来源、合并标了同一 `same_event_group` 的事件、把同源组加上分片前缀，并在合并后把不能证明两个独立同源组的 `corroborated` 降级。日期或地点冲突只记录、不裁决；主台账只保留每个 ID 的最新状态，完整历史留在分片。细节见 [并行调查](parallel-investigation.md)。

输入为一个记录或记录数组，可用 `--input -` 从标准输入读；同批引用的记录先于引用者。检索记录及访问请求事实不可改写，重试用新 ID。若核对原始输出后发现访问结果分类有误，可保留同一访问 ID，仅更正 outcome/detail，并加非空 correction_reason；旧分类仍保留在历史中，也不增加访问次数。常用字段：

```json
[
  {"kind":"search","id":"Q01","engine":"当前搜索工具","queries":["准确查询词"],"raw_path":"raw/B01.json"},
  {"kind":"visit","id":"V01","url":"https://example.org/post","method":"open","outcome":"error","detail":"实际返回的403；未读取正文","raw_path":"raw/B01.json"},
  {"kind":"source","id":"S01","title":"候选原帖","url":"https://example.org/post","voice":"unresolved","form":"unknown","access":"unretrieved","identity":"unresolved","visit_ids":["V01"],"limitation":"只有失败请求，不能证明帖子内容"},
  {"kind":"clue","id":"L01","question":"原帖能否从公开转载找到？","origin_ids":["S01"],"priority":"high","state":"blocked","next_step":"核查已经找到的公开引用链接"},
  {"kind":"coverage","id":"F01","family":"旧论坛","state":"blocked","scope":"本轮候选原帖","reason":"原站403，未取得正文","record_ids":["V01","S01","L01"]}
]
```

`visit.outcome`：content / partial / metadata / shell / error。
`source.voice`：self / other / mixed / unresolved；`form`：original / reprint / quote / catalog / program_notes / institution_record / unknown。
`source.access`：full_text / partial_text / metadata_only / search_only / unretrieved / transcript / audio_video_reviewed。
`claim.status`：documented_statement / corroborated / disputed / unverified / analysis。`documented_statement` 表示材料确实这样记载，不表示其叙述为真。
`event.status`：documented / corroborated / disputed / unverified；`event.date_precision`：day / month / year / range / unknown。
`clue.state`：open / blocked / resolved / deferred；`coverage.state`：unsearched / searched / partial / blocked / deferred / not_applicable。

事件记录用 `kind: event`，至少引用一个来源、结论或文件定位：

```json
{"kind":"event","id":"EV01","date":"2001-06-11","date_precision":"day","scope":"main","evidence_type":"journalist_report","title":"CNNIC 办公室会面","summary":"毛伟提出八条合作条件，双方开始六次面谈。","place":"北京中关村","people":["周鸿祎","毛伟"],"consequence":"","status":"documented","source_ids":["S03"],"claim_ids":["C11"],"sources":[{"source_id":"S03","lines":"11-30"}],"same_event_group":"cnnic-2001"}
```

`scope` 必填：`main` / `background` / `outside_window`；`evidence_type` 必填：`self_account` / `journalist_report` / `institution_record` / `mixed` / `unknown`。案头核读没有 `records.jsonl` 时，用 `sources: [{"file":"V01.txt","lines":"12"}]` 定位；不需要为凑结构补检索或访问记录。

来源记录可加 `same_source_group`。标 `corroborated` 的事件必须给每个来源写组，且至少两个不同组；脚本会拒绝同组来源、缺组来源和只有一个来源的 corroborated 事件。字段、去重和合并规则见 [事件台账](event-ledger.md)。转载不新建事件；同一事件的多篇报道共用一个 `same_event_group`。

来源有 `discovery_ids` 可指向检索；实际取得内容时须有相应访问记录。结论格式：

```json
{"kind":"claim","id":"C01","text":"节目页将该段标为监管讨论；尚未取得该段回答。","status":"documented_statement","evidence":[{"source_id":"S02","locator":"节目页时间轴25:40","relation":"supports"}]}
```

其他信息如原发/事件日期、作者、同源组、身份依据、录音核验区间可以增加字段。检索与访问记录的 `performed_at` 应填实际发生时间；若只知道批次时间，明确标为批次范围，不能把事后导入时间装成访问时间。

脚本检查必要字段、状态、引用和“失败访问不能支撑已读正文”等结构矛盾；不认证署名、不解析原文真假、不自动决定独立性、不衡量互联网覆盖率。人工核验仍是必要工作。
