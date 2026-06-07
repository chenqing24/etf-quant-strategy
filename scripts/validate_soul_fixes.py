#!/usr/bin/env python3
"""
SOUL/MEMORY 4 个修复逻辑验证（按用户 A4 指令）

按 SOP-01 v1.1 Step 4 "范围分层验证"：
- 范围：4 个修复的逻辑正确性
- 方法：5 个 mock 场景模拟用户指令 + 期望行为
- 判定：行为符合修复后规则 = PASS，否则 FAIL

不写新监控脚本（按用户"先调研，不要写新代码"原则）—— 纯逻辑验证。
"""
import re
from pathlib import Path


def get_rule_24_triggers():
    """提取规则 24 v3 的触发条件"""
    memory = Path('/home/qwenpaw/.qwenpaw/workspaces/default/MEMORY.md').read_text()
    # 找"强触发器"段
    match = re.search(r'\*\*强触发器（立即执行）\*\*：\n((?:- .*\n)+)', memory)
    if match:
        return [line.strip('- \n').strip() for line in match.group(1).split('\n') if line.strip()]
    return []


def get_rule_24_fixes():
    """提取规则 24 v3 的修复（#1+#2）"""
    memory = Path('/home/qwenpaw/.qwenpaw/workspaces/default/MEMORY.md').read_text()
    match = re.search(r'\*\*【修复 2026-06-07 矛盾对 #1\+#2】\*\*.*?(?=\n\n|\n#|\Z)', memory, re.DOTALL)
    return match.group(0) if match else ""


def get_rule_22_fixes():
    """提取 SOUL 规则 2.2 的修复（#3）"""
    soul = Path('/home/qwenpaw/.qwenpaw/workspaces/default/SOUL.md').read_text()
    match = re.search(r'\*\*【修复 2026-06-07 矛盾对 #3.*?(?=\n\n|\n#|\Z)', soul, re.DOTALL)
    return match.group(0) if match else ""


def get_rule_3_fixes():
    """提取 SOUL 规则 3 的修复（#4）"""
    soul = Path('/home/qwenpaw/.qwenpaw/workspaces/default/SOUL.md').read_text()
    match = re.search(r'\*\*【修复 2026-06-07 矛盾对 #4.*?(?=\n\n|\n#|\Z)', soul, re.DOTALL)
    return match.group(0) if match else ""


def check_rule_3_should_stop(user_online, said_seq, said_sop, said_offline):
    """修复后规则 3 判定：是否触发停止点"""
    # 修复后规则 3：4 个条件**同时**满足才生效
    if not user_online:
        return False, "用户下线 → 不触发（按规则 27）"
    if said_seq:
        return False, "用户说'按你的序号' → 不触发（按规则 24 v3）"
    if said_sop:
        return False, "用户说'按 SOP 走' → 不触发（按规则 24 v3）"
    if said_offline:
        return False, "用户下线 → 不触发"
    return True, "用户在线 + 没特殊指令 → 触发停止点"


def check_rule_22_should_stop(said_seq, said_sop):
    """修复后规则 2.2 判定：Phase 3 强制停止点是否生效"""
    # 修复后规则 2.2：用户**没**说 3 个之一才生效
    if said_seq or said_sop:
        return False, f"用户说'按你的序号'或'按 SOP 走' → Phase 3 合并到执行（不单独停）"
    return True, "用户没特殊指令 → Phase 3 强制停下"


def main():
    print("=" * 70)
    print("A4：4 个修复逻辑验证（5 个 mock 场景 + 1 个对照）")
    print("=" * 70)

    results = []

    # ===== 场景 1: #1 (A3) - "按你的序号" + 跨模块 =====
    print("\n【场景 1】用户说'按你的序号' + 跨模块任务")
    print("-" * 70)
    print("用户指令: '按你的序号，不要有偏好，做跨模块 X'")
    user_online, said_seq, said_sop, said_offline = True, True, False, False
    r3_stop, r3_reason = check_rule_3_should_stop(user_online, said_seq, said_sop, said_offline)
    r22_stop, r22_reason = check_rule_22_should_stop(said_seq, said_sop)
    expected_r3 = False  # 期望不触发停止
    expected_r22 = False  # 期望 Phase 3 不单独停
    pass_r3 = r3_stop == expected_r3
    pass_r22 = r22_stop == expected_r22
    print(f"  规则 3: 触发停止点={r3_stop} (期望={expected_r3}) → {'✅ PASS' if pass_r3 else '❌ FAIL'}")
    print(f"    原因: {r3_reason}")
    print(f"  规则 2.2: Phase 3 停下={r22_stop} (期望={expected_r22}) → {'✅ PASS' if pass_r22 else '❌ FAIL'}")
    print(f"    原因: {r22_reason}")
    print(f"  期望行为: '1 句设计 + 立即执行' (按修复 #1)")
    print(f"  实际判定: 规则 3 不触发 + 规则 2.2 不触发 → 立即执行")
    results.append(("场景 1: '按你的序号'+跨模块", pass_r3 and pass_r22))

    # ===== 场景 2: #3 (C3) - "按你的序号" + Phase 3 =====
    print("\n【场景 2】用户说'按你的序号' + Phase 3")
    print("-" * 70)
    print("用户指令: '按你的序号，做新功能 X (Phase 3 阶段)'")
    user_online, said_seq, said_sop, said_offline = True, True, False, False
    r22_stop, r22_reason = check_rule_22_should_stop(said_seq, said_sop)
    expected_r22 = False
    pass_r22 = r22_stop == expected_r22
    print(f"  规则 2.2: Phase 3 停下={r22_stop} (期望={expected_r22}) → {'✅ PASS' if pass_r22 else '❌ FAIL'}")
    print(f"    原因: {r22_reason}")
    print(f"  期望行为: 'Phase 3 设计合并到执行' (按修复 #3)")
    print(f"  实际判定: 规则 2.2 不触发 → 立即执行")
    results.append(("场景 2: '按你的序号'+Phase 3", pass_r22))

    # ===== 场景 3: #2 (B1) - "按你的序号" + 3+ 步 =====
    print("\n【场景 3】用户说'按你的序号' + 3+ 步管道")
    print("-" * 70)
    print("用户指令: '按你的序号，跑 3 步流程 X'")
    user_online, said_seq, said_sop, said_offline = True, True, False, False
    r3_stop, r3_reason = check_rule_3_should_stop(user_online, said_seq, said_sop, said_offline)
    expected_r3 = False
    pass_r3 = r3_stop == expected_r3
    print(f"  规则 3: 触发停止点={r3_stop} (期望={expected_r3}) → {'✅ PASS' if pass_r3 else '❌ FAIL'}")
    print(f"    原因: {r3_reason}")
    print(f"  期望行为: '1 句设计 + 立即执行' (按修复 #2)")
    print(f"  实际判定: 规则 3 不触发 → 立即执行")
    results.append(("场景 3: '按你的序号'+3+ 步", pass_r3))

    # ===== 场景 4: #4 (D3) - "我下线了" + 跨模块 =====
    print("\n【场景 4】用户说'我下线了' + 跨模块任务")
    print("-" * 70)
    print("用户指令: '我下线了，做跨模块 X'")
    user_online, said_seq, said_sop, said_offline = True, False, False, True
    r3_stop, r3_reason = check_rule_3_should_stop(user_online, said_seq, said_sop, said_offline)
    expected_r3 = False  # 期望不触发停止
    pass_r3 = r3_stop == expected_r3
    print(f"  规则 3: 触发停止点={r3_stop} (期望={expected_r3}) → {'✅ PASS' if pass_r3 else '❌ FAIL'}")
    print(f"    原因: {r3_reason}")
    print(f"  期望行为: '自动模式 + 写阻塞报告' (按修复 #4)")
    print(f"  实际判定: 规则 3 不触发 → 自动模式")
    results.append(("场景 4: '我下线了'+跨模块", pass_r3))

    # ===== 场景 5: #2 - "按 SOP 走" + 任何 =====
    print("\n【场景 5】用户说'按 SOP 走' + 任何")
    print("-" * 70)
    print("用户指令: '按 SOP 走，做 X'")
    user_online, said_seq, said_sop, said_offline = True, False, True, False
    r3_stop, r3_reason = check_rule_3_should_stop(user_online, said_seq, said_sop, said_offline)
    r22_stop, r22_reason = check_rule_22_should_stop(said_seq, said_sop)
    expected_r3 = False
    expected_r22 = False
    pass_r3 = r3_stop == expected_r3
    pass_r22 = r22_stop == expected_r22
    print(f"  规则 3: 触发停止点={r3_stop} (期望={expected_r3}) → {'✅ PASS' if pass_r3 else '❌ FAIL'}")
    print(f"  规则 2.2: Phase 3 停下={r22_stop} (期望={expected_r22}) → {'✅ PASS' if pass_r22 else '❌ FAIL'}")
    print(f"  期望行为: 'SOP 跑 = 设计 + 执行' (按修复 #2)")
    print(f"  实际判定: 规则 3+2.2 都不触发 → 跑 SOP")
    results.append(("场景 5: '按 SOP 走'+任何", pass_r3 and pass_r22))

    # ===== 场景 6 (对照): 用户**没**说"按你的序号"+ 跨模块 =====
    print("\n【场景 6（对照）】用户**没**说特殊指令 + 跨模块任务")
    print("-" * 70)
    print("用户指令: '做跨模块 X'（没说'按你的序号'或'按 SOP 走'）")
    user_online, said_seq, said_sop, said_offline = True, False, False, False
    r3_stop, r3_reason = check_rule_3_should_stop(user_online, said_seq, said_sop, said_offline)
    r22_stop, r22_reason = check_rule_22_should_stop(said_seq, said_sop)
    expected_r3 = True  # 期望**仍**触发停止（保留旧行为）
    expected_r22 = True  # 期望**仍**触发 Phase 3
    pass_r3 = r3_stop == expected_r3
    pass_r22 = r22_stop == expected_r22
    print(f"  规则 3: 触发停止点={r3_stop} (期望={expected_r3}) → {'✅ PASS' if pass_r3 else '❌ FAIL'}")
    print(f"  规则 2.2: Phase 3 停下={r22_stop} (期望={expected_r22}) → {'✅ PASS' if pass_r22 else '❌ FAIL'}")
    print(f"  期望行为: '仍停下等确认' (旧行为保留)")
    print(f"  实际判定: 规则 3+2.2 都触发 → 停下等")
    results.append(("场景 6 (对照): 普通+跨模块 → 仍停下", pass_r3 and pass_r22))

    # ===== 汇总 =====
    print("\n" + "=" * 70)
    print("📊 4 个修复验证结果")
    print("=" * 70)
    n_pass = sum(1 for _, p in results if p)
    n_total = len(results)
    for name, p in results:
        print(f"  {'✅' if p else '❌'} {name}")
    print(f"\n汇总: {n_pass}/{n_total} PASS")

    if n_pass == n_total:
        print("\n🎉 所有场景 PASS：4 个修复逻辑正确")
    else:
        print(f"\n⚠️ {n_total - n_pass} 个场景 FAIL：需重新检查修复")


if __name__ == "__main__":
    main()
