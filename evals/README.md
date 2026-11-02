# 回归用例

这些用例验证方法改动没有退化。它们不进入技能包，也不含真实人物的私人材料。

## 1. 结构测试

```bash
python3 scripts/test_research_log.py
python3 scripts/test_extract_links.py
python3 scripts/test_check_events.py
python3 scripts/test_check_delivery.py
python3 scripts/test_package.py
python3 scripts/test_mc_to_records.py
```

其中 `test_research_log.py` 的 `MergeTests` 覆盖分片合并：编号重映射、引用与 `raw_path` 重写、同 URL 来源去重、跨分片事件合并、重复候选、冲突保留、非空主台账拒绝覆盖、`--dry-run` 不落盘。`test_check_delivery.py` 覆盖 `parallel` 段的 worker 上限、分片停止原因、合并报告与计数。

## 2. 读者锚点行为检查

用一份已完成的自然调查交付（如 R008）核对：

- 首次出现人物时有出生日期与全名/公开名；出生日期缺失时写已知年代并说明缺口；
- 各阶段入口能看出当时年龄，正文没有把年龄做成表或每句加括号；
- 重要年代有图片或明确图位；图注只写画面信息，作者、来源、许可、授权与是否本人放 `CREDITS.md` 与附卷配图表；
- 重大转折通常两到四个，有“处境—行动—回应—后果”链条，材料不足时不凑数；
- 正文没有「本轮未取得」「本文不采用」一类台账语言。

## 3. 交付头行为检查

- 报告开头有模式、事实截止日、调查日期、材料范围、广度/深度预算、停止原因；
- `delivery.json` 通过 `check_delivery.py`；
- 每条下一轮计划有缺口、查询、来源家族、成功标准与停止条件；
- 并行调查时 `parallel` 段有 worker 数、分片停止原因、合并报告路径与统计。

## 4. 并行 A/B（R008）

基线：R008 顺序版，161 条记录、11 个开放缺口、`delivery.json` 通过。

并行版按来源家族分成 3 个分片，用同一身份索引与同一事实截止日重跑。通过线：

- 墙钟时间下降 ≥30%；
- 事件与来源覆盖不低于基线；
- `research_log.py check`、`check_events.py`、`check_delivery.py` 全部通过；
- 合并后没有同源重复，也没有错误的 `corroborated`。

结果写进 `EVALUATION.md` 的并行调查一节；未达到通过线时，保留失败数据与原因，不调低阈值。
