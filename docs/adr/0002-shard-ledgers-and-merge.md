# 分片台账独立写入，由合并命令统一编号

并行调查中，多个 worker 直接追加同一份 `records.jsonl` 会撞编号、互相覆盖，也丢失“哪条材料由哪个范围找到”的 provenance。我们决定：每个 worker 只写自己的分片台账（`shards/<id>/records.jsonl`、`raw/`、`shard.json`、`findings.md`），由协调者运行 `research_log.py merge` 合成主台账。合并命令只做机械工作：统一编号并保留 `shard_id` 与原 ID 映射、按事件台账规则去重、把日期与在场者的分歧写进 `merge-report.json`、在合并后按同源组重新计算 `corroborated`。它不做真伪判断；冲突由协调者按证据层级裁决，不能静默选一个。

代价是新增合并命令与测试，并且并行模式的交付必须附带合并报告；收益是并发写入安全、来源可追溯、错误 `corroborated` 在合并后会被降级而不是被掩盖。
