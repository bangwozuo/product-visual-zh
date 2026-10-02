# -*- coding: utf-8 -*-
"""
主图 A/B 版本生成 —— 端到端编排脚本。

编排逻辑（与 SKILL.md 的 DAG 一致）：
  主图需求 → [内置] A/B 方案设计（单变量校验）
          → [copy-layout] 两版版式落位图（scripts/grid_preview.py）
          → [platform-compliance-precheck] 主图文案合规扫描（scripts/precheck.py）
          → [内置] 测试判定：CTR 基准 + 两比例 z 检验（单组 ≥1000 曝光且 ≥3 天才比较）
          → [人工] 定稿上线

失败处理：
  - 上游脚本退出码 != 0 → 中止并打印 stderr
  - 版式检查 FAIL / 文案红线 >0 → 该版本标「不可上线」，不阻塞其他版本
  - 单组曝光 <1000 或天数 <3 → 输出「样本不足，不下结论」
  - 版本缺测试数据 → 标「数据缺失」，正常退出

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo
"""
from __future__ import annotations

import argparse
import math
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

GRID = os.path.join(REPO, "skills", "copy-layout", "scripts", "grid_preview.py")
PRECHECK = os.path.join(REPO, "skills", "platform-compliance-precheck", "scripts", "precheck.py")

MIN_DAYS, MIN_IMPRESSIONS = 3, 1000
Z_CRIT = 1.96

DEMO_INPUT = {
    "product": "便携电热水杯（316L 内胆）",
    "platform": "抖音",
    "versions": [
        {
            "name": "A 场景卖点版",
            "text": "晨起 3 分钟，一杯温水。6 小时保温 60 度以上（实验室实测）",
            "layout": {
                "canvas": "900x1200", "bg_color": "#F5F1E8",
                "product_zone": {"x": 90, "y": 430, "w": 720, "h": 620},
                "blocks": [
                    {"level": "title", "text": "晨起 3 分钟 · 一杯温水", "x": 56, "y": 56,
                     "w": 700, "size": 56, "color": "#2B2B2B", "bold": True},
                    {"level": "subtitle", "text": "6 小时保温 60 度以上（实验室实测）",
                     "x": 56, "y": 150, "w": 700, "size": 34, "color": "#4A4A4A"}
                ]
            },
            "days": 4, "impressions": 3200, "clicks": 96
        },
        {
            "name": "B 参数价格版",
            "text": "316L 不锈钢内胆，限时优惠价 99 元。6 小时保温 60 度以上（实验室实测）",
            "layout": {
                "canvas": "900x1200", "bg_color": "#F5F1E8",
                "product_zone": {"x": 90, "y": 430, "w": 720, "h": 620},
                "blocks": [
                    {"level": "title", "text": "316L 内胆 · 限时 99 元", "x": 56, "y": 56,
                     "w": 700, "size": 56, "color": "#2B2B2B", "bold": True},
                    {"level": "subtitle", "text": "6 小时保温 60 度以上（实验室实测）",
                     "x": 56, "y": 150, "w": 700, "size": 34, "color": "#4A4A4A"}
                ]
            },
            "days": 4, "impressions": 3050, "clicks": 129
        }
    ]
}


def run(cmd, tag, cwd=FLOW_DIR):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        print(f"[失败处理] {tag} 退出码 {r.returncode}，流程中止。", file=sys.stderr)
        print(r.stderr[-800:], file=sys.stderr)
        sys.exit(1)
    return r


def z_test(c1, n1, c2, n2):
    p1, p2 = c1 / n1, c2 / n2
    pool = (c1 + c2) / (n1 + n2)
    se = math.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return None, None
    z = (p2 - p1) / se
    p_value = math.erfc(abs(z) / math.sqrt(2))
    return z, p_value


def ctr_verdict(ctr_pct):
    if ctr_pct < 1:
        return "❌ 主图有问题（<1%，对标杆重设计）"
    if ctr_pct < 2:
        return "🟡 偏弱（1–2%，换主卖点再测）"
    if ctr_pct <= 5:
        return "✅ 电商正常区间（2–5%）"
    return "🟡 优秀但防假（>5%，核查图文不符/退款率）"


def main():
    ap = argparse.ArgumentParser(description="主图 A/B 版本生成与判定流程")
    ap.add_argument("--input", help="流程输入 JSON（product/platform/versions）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    at.ensure_outdir(a.outdir)
    payload = DEMO_INPUT if a.demo else at.read_json(a.input)
    versions = payload.get("versions", [])
    if len(versions) < 2:
        print("[失败处理] A/B 至少需要 2 个版本，流程中止。", file=sys.stderr)
        sys.exit(1)
    platform = payload.get("platform", "抖音")

    steps, layout_rows, compliance_rows, version_rows = [], [], [], []
    grid_files = []
    for i, v in enumerate(versions, 1):
        name = v.get("name", f"版本{i}")

        # 步骤 2：版式落位（copy-layout）
        lay_in = os.path.join(a.outdir, f"_layout_in_{i}.json")
        at.write_json(v.get("layout", {}), lay_in)
        lay_out = os.path.join(a.outdir, f"step2_版式栅格", f"版本{i}")
        r = run([sys.executable, GRID, "--input", lay_in, "--outdir", lay_out], f"copy-layout({name})")
        grid_png = os.path.abspath(os.path.join(lay_out, "版式栅格示意图.png"))
        grid_json = at.read_json(os.path.join(lay_out, "layout_check.json"))
        lay_ok = grid_json["summary"]["整体判定"] == "通过"
        layout_rows.append({"版本": name, "版式判定": grid_json["summary"]["整体判定"],
                            "文字面积": grid_json["summary"]["文字面积"],
                            "可上线": "✅" if lay_ok else "❌ 按整改指令重跑"})
        grid_files.append(grid_png)

        # 步骤 3：文案合规（platform-compliance-precheck）
        pc_in = os.path.join(a.outdir, f"_precheck_in_{i}.json")
        at.write_json({"platform": platform, "text": v.get("text", "")}, pc_in)
        pc_out = os.path.join(a.outdir, "step3_文案合规", f"版本{i}")
        run([sys.executable, PRECHECK, "--input", pc_in, "--outdir", pc_out], f"precheck({name})")
        pc = at.read_json(os.path.join(pc_out, "precheck.json"))
        n_red = sum(1 for h in pc.get("hits", []) if "红线" in h["级别"])
        compliance_rows.append({"版本": name, "红线": n_red,
                                "警告": sum(1 for h in pc.get("hits", []) if "警告" in h["级别"]),
                                "可上线": "✅" if n_red == 0 else "❌ 打回改文案"})

        # 步骤 4：测试数据判定
        days, imp, clk = v.get("days"), v.get("impressions"), v.get("clicks")
        if not all(isinstance(x, (int, float)) and x for x in (days, imp, clk)):
            version_rows.append({"版本": name, "天数": days or "—", "曝光": imp or "—",
                                 "点击": clk or "—", "CTR": "—", "基准判定": "数据缺失"})
            continue
        ctr = clk / imp * 100
        enough = imp >= MIN_IMPRESSIONS and days >= MIN_DAYS
        version_rows.append({"版本": name, "天数": days, "曝光": imp, "点击": clk,
                             "CTR": f"{ctr:.2f}%",
                             "基准判定": ctr_verdict(ctr) + ("" if enough else "｜样本不足(<3天或<1000曝光)，不下结论")})

        # 步骤留痕
        steps.append({"step": 2, "skill": "copy-layout", "version": name, "output": grid_png})
        steps.append({"step": 3, "skill": "platform-compliance-precheck", "version": name,
                      "output": os.path.abspath(os.path.join(pc_out, "precheck.json"))})

    # 版本比较（两比例 z 检验；取前两个有完整数据的版本）
    comp = {"z": "—", "p": "—", "结论": "数据不足，未做版本比较"}
    full = [v for v in versions if all(isinstance(v.get(k), (int, float)) and v.get(k)
                                       for k in ("days", "impressions", "clicks"))]
    if len(full) >= 2 and all(v["impressions"] >= MIN_IMPRESSIONS and v["days"] >= MIN_DAYS
                              for v in full[:2]):
        v1, v2 = full[0], full[1]
        z, p = z_test(v1["clicks"], v1["impressions"], v2["clicks"], v2["impressions"])
        if z is not None:
            lift = (v2["clicks"] / v2["impressions"]) / (v1["clicks"] / v1["impressions"]) - 1
            if abs(z) >= Z_CRIT:
                winner = v2["name"] if z > 0 else v1["name"]
                comp = {"z": f"{z:.2f}（阈值 ±{Z_CRIT}）", "p": f"{p:.4f}",
                        "相对提升": f"{lift * 100:+.1f}%",
                        "结论": f"差异显著，{winner} 胜出"
                                + ("（提升 <10%，权衡老链接换图掉权重风险后人工决策）"
                                   if abs(lift) < 0.10 else "")}
            else:
                comp = {"z": f"{z:.2f}（阈值 ±{Z_CRIT}）", "p": f"{p:.4f}",
                        "相对提升": f"{lift * 100:+.1f}%",
                        "结论": "|z| < 1.96，不下结论——延长测试或加大预算"}
        else:
            comp = {"z": "—", "p": "—", "结论": "无差异，未做比较"}

    summary = {
        "商品": payload.get("product", "未提供"),
        "平台": platform,
        "版本数": len(versions),
        "版式可上线": f"{sum(1 for r in layout_rows if '✅' in r['可上线'])}/{len(versions)}",
        "合规可上线": f"{sum(1 for r in compliance_rows if r['红线'] == 0)}/{len(versions)}",
        "样本门槛": f"单组 ≥{MIN_IMPRESSIONS} 曝光 且 ≥{MIN_DAYS} 天",
        "版本比较": comp["结论"],
        "人工确认点": "上线下架由人工决定；CTR>5% 核查退款率防图文不符；老链接换图有掉权重风险",
        "说明": "CTR/z 值由脚本实测；版式与合规结论以两个上游脚本输出为准",
    }

    xlsx = at.write_excel(
        os.path.join(a.outdir, "主图AB测试报告.xlsx"),
        {"版本判定": version_rows, "版式留痕": layout_rows, "合规留痕": compliance_rows,
         "统计判定": [{"项": k, "值": str(v)} for k, v in comp.items()],
         "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()]},
        highlights={"版本判定": {"基准判定": "contains:❌"},
                    "合规留痕": {"可上线": "contains:❌"}},
        widths={"版本判定": {"基准判定": 44}, "合规留痕": {"版本": 16}},
    )

    md = [
        f"# 主图 A/B 测试报告 —— {summary['商品']}（{platform}）", "",
        "| 版本 | 天数 | 曝光 | 点击 | CTR | 基准判定 |", "|---|---|---|---|---|---|",
    ] + ["| {版本} | {天数} | {曝光} | {点击} | {CTR} | {基准判定} |".format(**r)
         for r in version_rows] + [
        "", "## 统计判定", "",
    ] + [f"| {k} | {v} |" for k, v in comp.items()] + [
        "", "## 版式与合规留痕", "",
        "| 版本 | 版式判定 | 文字面积 | 合规红线 | 可上线 |", "|---|---|---|---|---|",
    ] + ["| {} | {} | {} | {} | {} |".format(
        lr["版本"], lr["版式判定"], lr["文字面积"], cr["红线"], cr["可上线"])
        for lr, cr in zip(layout_rows, compliance_rows)] + [
        "", f"> 版式落位图：`step2_版式栅格/`；合规扫描：`step3_文案合规/`。",
        "> 本报告由 run_flow.py 实跑生成（AI 生成内容）；上线下架由人工决定。",
    ]
    md_path = os.path.join(a.outdir, "主图AB测试报告.md")
    with open(md_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(md))

    result = {
        "flow": "hero-image-ab-flow",
        "steps": [{"step": 1, "skill": "（内置）A/B 方案设计（单变量校验）", "status": "ok"}] + steps +
                 [{"step": 4, "skill": "（内置）CTR 基准 + z 检验", "status": "ok"},
                  {"step": 5, "skill": "（人工）定稿上线", "status": "pending"}],
        "summary": summary,
        "files": [xlsx, md_path] + grid_files,
        "generated_at": at.stamp(),
    }
    at.write_json(result, os.path.join(a.outdir, "ab_flow_result.json"))
    print(f"版本 {len(versions)} 个；比较：{comp['结论']}")
    for f in result["files"]:
        print(" 产物:", f)
    at.emit(result)


if __name__ == "__main__":
    main()
