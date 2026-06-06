#!/usr/bin/env python3
"""
批量创建"分时段多源采集"进度检查 cron

时间范围：2026-06-06 18:00 → 2026-06-07 06:00（13 个）
每个 cron 检查 3 件事：完成 + SOP + 笔记
最后 1 个 = 复盘小结

参考 qwenpaw cron 备份格式：etf_backups/cron/cron_etf_eval_pre_us024_fix.json
"""
import json
import subprocess
import sys
from pathlib import Path


# 13 个 cron 时间点
CRON_SCHEDULE = [
    ("18", "启动 + 写笔记 + 任务基线"),
    ("19", "Step 1 完成检查（constants.py）"),
    ("20", "Step 2 完成检查（router.py）"),
    ("21", "Step 3-4 完成检查（测试 + 工具脚本）"),
    ("22", "V1 验证检查（单只 ETF 5 年）"),
    ("23", "V2 验证检查（多源回退）"),
    ("00", "15 只全量跑检查"),
    ("01", "数据完整性报告检查 + git commit"),
    ("02", "兜底检查 1"),
    ("03", "兜底检查 2"),
    ("04", "兜底检查 3"),
    ("05", "兜底检查 4"),
    ("06", "复盘小结（最后）"),
]


def build_cron_text(hour: str, description: str) -> str:
    """生成 cron text（agent 会自动执行）"""
    is_last = (hour == "06")

    if is_last:
        return f"""📋 **复盘小结任务（最后一次 cron）**

请按以下步骤做复盘：
1. 完整复盘整个任务（Phase 1-6 + 13 个 cron 进度）
2. 总结完成度（X/6 步骤 + Y/4 验证）
3. 记录所有诚实标记（不美化）
4. 写到 memory/2026-06-07.md
5. 跑 git status 看是否有未提交
6. 给用户最终交付报告
7. 如有未完成项，**诚实标记** + 后续 TODO

⚠️ 这是最后 1 个 cron，必须出复盘报告
"""

    return f"""⏰ **进度检查 {hour}:00**

检查分时段多源采集任务（fetch_core_etf_5year）的进度。

按 3 件事检查：
1. ✅ **完成度** — Phase 4 实施到了哪一步？
   - Step 1: constants.py（+5 常量）？
   - Step 2: router.py（+AKTools 路由 + fetch_daily_range）？
   - Step 3: tests/unit/test_router_aktools.py（4 测试）？
   - Step 4: scripts/data/fetch_core_etf_5year.py（主工具）？
   - Step 5: 单只验证（512660 跑 5 年）？
   - Step 6: 15 只全量 + 报告？

2. ✅ **SOP 执行** — 是否按 SOP-02 6 Phase 走？
   - Phase 4 实施是否按"小步提交"？
   - 每个 Step 后是否 git commit？
   - pre-commit 检查是否通过？

3. ✅ **笔记记录** — memory/2026-06-06.md 是否更新？
   - 实施进度段是否写到笔记？
   - 任何问题/诚实标记是否记录？

🎯 当前任务：{description}

**重要**：如果任务已完成，写"✅ 完成"，等最后 1 个 cron 06:00 做复盘。
如果未完成，**催促** + 列出下一步动作。
如果跑出 bug，**诚实标记** + 写修复计划。
"""


def build_cron_spec(hour: str, description: str) -> dict:
    """构建 cron spec JSON（参考 ETF 评估 cron 备份格式）"""
    return {
        "name": f"进度检查-{hour}:00",
        "enabled": True,
        "schedule": {
            "type": "cron",
            "cron": f"0 {hour} * * *",
            "run_at": None,
            "timezone": "Asia/Shanghai",
            "repeat_every_days": None,
            "repeat_end_type": None,
            "repeat_until": None,
            "repeat_count": None,
        },
        "task_type": "agent",
        "text": None,
        "request": {
            "input": [
                {
                    "content": [
                        {
                            "text": build_cron_text(hour, description),
                            "type": "text",
                        }
                    ],
                    "role": "user",
                    "type": "message",
                }
            ],
            "session_id": "TukxwR4=",
            "user_id": "陈庆#3g==",
        },
        "dispatch": {
            "type": "channel",
            "channel": "dingtalk",
            "target": {
                "user_id": "陈庆#3g==",
                "session_id": "TukxwR4=",
            },
            "mode": "final",
            "meta": {},
        },
        "save_result_to_inbox": False,
        "runtime": {
            "max_concurrency": 1,
            "timeout_seconds": 600,
            "misfire_grace_seconds": 60,
            "share_session": True,
        },
    }


def main():
    # 输出目录
    output_dir = Path("etf_backups/cron/progress_crons_20260606")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 备份现有 cron 列表
    print("📋 备份现有 cron 列表...")
    result = subprocess.run(
        ["qwenpaw", "cron", "list"],
        capture_output=True, text=True
    )
    backup_path = output_dir / "before_create.json"
    backup_path.write_text(result.stdout, encoding="utf-8")
    print(f"  ✅ 备份: {backup_path}")

    # 批量创建
    print(f"\n📋 创建 {len(CRON_SCHEDULE)} 个进度检查 cron...")
    created_ids = []

    for hour, desc in CRON_SCHEDULE:
        spec = build_cron_spec(hour, desc)

        # 写 spec JSON
        spec_path = output_dir / f"cron_{hour}.json"
        spec_path.write_text(
            json.dumps(spec, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # 创建 cron
        result = subprocess.run(
            ["qwenpaw", "cron", "create", "-f", str(spec_path)],
            capture_output=True, text=True
        )

        if result.returncode == 0:
            try:
                resp = json.loads(result.stdout)
                new_id = resp.get("id", "?")
                created_ids.append((hour, new_id, desc))
                print(f"  ✅ {hour}:00 → {new_id[:8]} ({desc[:30]})")
            except Exception:
                print(f"  ⚠️ {hour}:00 创建成功但解析失败: {result.stdout[:100]}")
        else:
            print(f"  ❌ {hour}:00 失败: {result.stderr[:200]}")

    # 汇总
    print(f"\n✅ 成功创建 {len(created_ids)}/{len(CRON_SCHEDULE)} 个 cron")
    print(f"\n📋 任务表：")
    for hour, cid, desc in created_ids:
        marker = "🏁 复盘" if hour == "06" else "⏰"
        print(f"  {marker} {hour}:00 → {cid[:8]} | {desc}")

    # 写索引
    index_path = output_dir / "index.md"
    lines = [
        "# 进度检查 cron 索引（2026-06-06 18:00 → 2026-06-07 06:00）",
        "",
        "## 任务表",
        "",
        "| 时间 | cron ID | 任务 |",
        "|------|---------|------|",
    ]
    for hour, cid, desc in created_ids:
        marker = "🏁 复盘" if hour == "06" else ""
        lines.append(f"| {hour}:00 | `{cid}` | {desc} {marker}|")
    lines.append("")
    lines.append("## 重要约定")
    lines.append("")
    lines.append("- 每个 cron 检查 3 件事：完成 + SOP + 笔记")
    lines.append("- 任务完成 = 跳过中间 cron，等 06:00 复盘")
    lines.append("- 任务未完成 = 列出下一步 + 诚实标记")
    lines.append("- 最后 1 个 cron（06:00）= 复盘小结")
    index_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n📄 索引: {index_path}")


if __name__ == "__main__":
    main()
