# -*- coding: utf-8 -*-
"""
平台合规预审流程 —— 端到端编排脚本（初检 → 整改 → 复检闭环）。

编排逻辑（与 SKILL.md 的 DAG 一致）：
  待检素材 → [内置] 文本采集确认
          → [platform-compliance-precheck] 词表初检（out/初检/合规预审清单.xlsx）
          → [内置] 整改对照表生成（改法取自初检命中记录）
          → [platform-compliance-precheck] 整改复检（out/复检/…，红线=0 才放行）
          → 人工确认（对照官方最新规范）

失败处理：
  - precheck.py 退出码 != 0 或产物缺失 → 中止并打印 stderr
  - 受检文本为空 → 中止（输入缺失）
  - 复检仍有红线 → 正常退出但判定「不建议上架」，供模型按 prompt.txt 再整改（≤3 轮）
  - 未提供 revised_text → 流程停在整改清单交付，复检标「未执行」

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FLOW_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(FLOW_DIR))
sys.path.insert(0, os.path.join(REPO, "lib"))

try:
    import assettools as at
except ImportError:  # pragma: no cover
    print("[错误] 未找到 lib/assettools.py", file=sys.stderr)
    sys.exit(2)

PRECHECK = os.path.join(REPO, "skills", "platform-compliance-precheck", "scripts", "precheck.py")

DEMO_INPUT = {
    "platform": "淘宝",
    "category": "化妆品",
    "text": ("【全网最低价】医美级精华液，100% 彻底淡化痘印，效果最好的抗敏修复神器！"
             "国家级实验室研发，独家配方，销量第一。加微信 xxx 领取试用装，扫码进群更优惠。"
             "本品适用于各类肌肤，无任何副作用。"),
    "revised_text": ("2026 年新款精华液，限时优惠价 99 元。配方含神经酰胺，主打舒缓保湿，"
                     "实测反馈良好（样本 30 人）。"),
}

MAX_ROUNDS = 3


def run_precheck(payload: dict, outdir: str, tag: str):
    """调 platform-compliance-precheck/scripts/precheck.py 跑一轮扫描。"""
    in_path = os.path.join(outdir, f"_precheck_in_{tag}.json")
    at.write_json(payload, in_path)
    sub_out = os.path.join(outdir, tag)
    r = subprocess.run(
        [sys.executable, PRECHECK, "--input", in_path, "--outdir", sub_out],
        cwd=FLOW_DIR, capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0:
        print(f"[失败处理] precheck.py（{tag}）退出码 {r.returncode}，流程中止。", file=sys.stderr)
        print(r.stderr[-800:], file=sys.stderr)
        sys.exit(1)
    js = os.path.join(sub_out, "precheck.json")
    if not os.path.exists(js):
        print(f"[失败处理] precheck 产物 {js} 缺失，流程中止。", file=sys.stderr)
        sys.exit(1)
    return at.read_json(js), os.path.abspath(os.path.join(sub_out, "合规预审清单.xlsx")), js


def counts(hits):
    n = {"R": 0, "W": 0, "I": 0}
    for h in hits:
        n[{"🔴": "R", "🟡": "W", "🔵": "I"}[h["级别"][0]]] += 1
    return n


def main():
    ap = argparse.ArgumentParser(description="平台合规预审流程（初检→整改→复检）")
    ap.add_argument("--input", help="流程输入 JSON（platform/category/text/revised_text）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    at.ensure_outdir(a.outdir)
    payload = DEMO_INPUT if a.demo else at.read_json(a.input)
    text = (payload.get("text") or "").strip()
    if not text:
        print("[失败处理] 受检文本为空（输入缺失），流程中止。", file=sys.stderr)
        sys.exit(1)
    platform, category = payload.get("platform", "通用"), payload.get("category", "")

    # 步骤 1-2：初检
    first, first_xlsx, first_js = run_precheck(
        {"platform": platform, "category": category, "text": text}, a.outdir, "初检")
    first_hits = first.get("hits", [])
    c1 = counts(first_hits)

    # 步骤 3：整改对照（改法来自初检记录；语境误报排除由模型按 prompt.txt 复核）
    fixes = [{"#": i, "级别": h["级别"], "原文片段": h["原文片段"], "命中规则": h["命中规则"],
              "依据": h["依据"], "建议改法": h["建议改法"]}
             for i, h in enumerate(first_hits, 1)]

    # 步骤 4：复检闭环（≤3 轮；复检输入由用户提供整改文案）
    revised = (payload.get("revised_text") or "").strip()
    rounds, final, final_xlsx, final_js = 0, None, "", ""
    if revised:
        cur = revised
        while rounds < MAX_ROUNDS:
            rounds += 1
            final, final_xlsx, final_js = run_precheck(
                {"platform": platform, "category": category, "text": cur}, a.outdir,
                "复检" if rounds == 1 else f"复检_第{rounds}轮")
            if counts(final.get("hits", []))["R"] == 0:
                break
            cur = revised  # 真实整改由模型按 prompt.txt 产出；此处复用用户文案并记录轮次
    c2 = counts(final.get("hits", [])) if final is not None else None

    if c2 is None:
        verdict = "整改清单已交付（复检未执行：未提供 revised_text）"
    elif c2["R"] == 0:
        verdict = "通过（修改后上架）" if c1["R"] else "通过"
        if c2["W"] > 2:
            verdict = "修改后上架（警告超 2 项，须逐条处置）"
    else:
        verdict = "不建议上架（复检红线未归零，移交人工）"

    summary = {
        "平台/类目": f"{platform} / {category or '未启用类目词表'}",
        "受检文本量": f"{len(text)} 字",
        "初检": f"红线 {c1['R']} / 警告 {c1['W']} / 提示 {c1['I']}（{first['summary']['整体判定']}）",
        "整改项数": len(fixes),
        "复检": "未执行" if c2 is None else
                f"红线 {c2['R']} / 警告 {c2['W']} / 提示 {c2['I']}（{rounds} 轮）",
        "整体判定": verdict,
        "整改轮次上限": f"{MAX_ROUNDS} 轮（超限移交人工）",
        "人工确认点": "上架前须人工对照平台官方最新规范复核；本流程不替代平台审核",
        "说明": "命中/级别/判定以 precheck.json 为准；语境误报排除与整改话术由模型按 prompt.txt 完成",
    }

    sheets = {
        "初检违规清单": first_hits or [{"级别": "（无）", "原文片段": "", "命中规则": "", "依据": "", "建议改法": ""}],
        "整改对照表": fixes or [{"#": "—", "级别": "（初检无命中）", "原文片段": "", "命中规则": "", "依据": "", "建议改法": ""}],
        "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()],
    }
    highlights = {}
    if first_hits:
        highlights["初检违规清单"] = {"级别": "contains:红线"}
    if final is not None:
        fh = final.get("hits", []) or [{"级别": "（无）", "原文片段": "", "命中规则": "", "依据": "", "建议改法": ""}]
        sheets["复检清单"] = fh
        highlights["复检清单"] = {"级别": "contains:红线"}
    xlsx = at.write_excel(os.path.join(a.outdir, "合规整改流程报告.xlsx"), sheets,
                          highlights=highlights,
                          widths={"初检违规清单": {"原文片段": 24, "建议改法": 38},
                                  "整改对照表": {"建议改法": 44}})

    md = [
        f"# 合规预审流程报告 —— {platform}{' / ' + category if category else ''}",
        "",
        "| 项 | 内容 |", "|---|---|",
    ] + [f"| {k} | {v} |" for k, v in summary.items()] + [
        "",
        "## 整改对照表", "",
        "| # | 级别 | 原文片段 | 命中规则 | 建议改法 |", "|---|---|---|---|---|",
    ] + [f"| {f['#']} | {f['级别']} | {f['原文片段']} | {f['命中规则']} | {f['建议改法']} |"
         for f in fixes] + [
        "",
        f"> 初检清单：`初检/合规预审清单.xlsx`；复检清单：`复检/合规预审清单.xlsx`。",
        "> 本报告由 run_flow.py 实跑生成；语境误报排除与整改话术由模型按 prompt.txt 复核，",
        "> 上架前须人工对照平台官方最新规范确认（AI 生成内容，不构成法律意见）。",
    ]
    md_path = os.path.join(a.outdir, "合规整改流程报告.md")
    with open(md_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(md))

    result = {
        "flow": "platform-compliance-flow",
        "steps": [
            {"step": 1, "skill": "（内置）文本采集确认", "status": "ok", "chars": len(text)},
            {"step": 2, "skill": "platform-compliance-precheck（初检）", "status": "ok", "output": first_js},
            {"step": 3, "skill": "（内置）整改对照表", "status": "ok", "fixes": len(fixes)},
            {"step": 4, "skill": "platform-compliance-precheck（复检）", "status": "ok" if c2 is not None else "skipped",
             "rounds": rounds, "output": final_js},
            {"step": 5, "skill": "（人工）对照官方规范确认", "status": "pending"},
        ],
        "summary": summary,
        "files": [xlsx, md_path, first_xlsx] + ([final_xlsx] if final_xlsx else []),
        "generated_at": at.stamp(),
    }
    at.write_json(result, os.path.join(a.outdir, "compliance_flow_result.json"))

    print(f"初检 红线 {c1['R']} / 警告 {c1['W']}；复检 "
          + ("未执行" if c2 is None else f"红线 {c2['R']}（{rounds} 轮）")
          + f" —— 判定：{verdict}")
    for f in result["files"]:
        print(" 产物:", f)
    at.emit(result)


if __name__ == "__main__":
    main()
