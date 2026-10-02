# -*- coding: utf-8 -*-
"""
详情页排版生成 —— 端到端编排脚本。

编排逻辑（与 SKILL.md 的 DAG 一致）：
  商品信息 → [内置] 五屏结构编排（屏型/文案/高度预算）
           → [copy-layout] 关键屏（首屏+第一卖点屏）落位图
           → [platform-compliance-precheck] 全部屏文案合规扫描
           → [内置] 长图规格校验（总高 ≤8000px @750 宽）
           → [人工] 规格核对后交付制作

失败处理：
  - 上游脚本退出码 != 0 → 中止并打印 stderr
  - 屏高 ≤0 或屏型非法 → 中止（输入缺失/非法）
  - 合规红线 >0 → 红线屏标「打回改文案」，红线清零前不给「可交付」
  - 总高 >8000px → 不判失败，输出「超长 + 裁剪建议」（合并/删屏优先级）

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

MAX_TOTAL_HEIGHT = 8000
VALID_TYPES = {"hook": "首屏钩子", "benefit": "卖点", "spec": "规格参数", "trust": "信任背书", "faq": "FAQ"}
TYPE_HEIGHT = {"hook": (750, 1000), "benefit": (750, 950), "spec": (500, 700),
               "trust": (500, 700), "faq": (500, 900)}

DEMO_INPUT = {
    "product": "便携手冲咖啡壶套装",
    "width": 750,
    "screens": [
        {"type": "hook", "title": "出门前 1 分钟，咖啡馆的味道", "height": 950,
         "text": "痛点：便利店咖啡又贵又要等。核心利益：15Bar 恒压萃取，办公室手冲自由。"},
        {"type": "benefit", "title": "15Bar 恒压萃取", "height": 850,
         "text": "每杯油脂稳定，实测浓度 18%（SCAA 金杯准则区间）。"},
        {"type": "benefit", "title": "304 不锈钢随身杯", "height": 850,
         "text": "食品接触级 304 材质，杯身 320ml，单手开合。"},
        {"type": "spec", "title": "规格参数", "height": 650,
         "text": "壶高 18.5cm，净重 420g，滤网孔径 0.3mm，额定水容量 320ml。"},
        {"type": "trust", "title": "信任背书", "height": 650,
         "text": "提供材质检测报告（编号可查），12 个月质保，滤网 90 天可换新。"},
        {"type": "faq", "title": "常见问题", "height": 900,
         "text": "适用咖啡粉粗细？中度研磨。能否进洗碗机？壶身可以，木柄部件建议手洗。"}
    ]
}


def run(cmd, tag):
    r = subprocess.run(cmd, cwd=FLOW_DIR, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        print(f"[失败处理] {tag} 退出码 {r.returncode}，流程中止。", file=sys.stderr)
        print(r.stderr[-800:], file=sys.stderr)
        sys.exit(1)
    return r


def main():
    ap = argparse.ArgumentParser(description="详情页排版生成流程")
    ap.add_argument("--input", help="流程输入 JSON（product/width/screens）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    at.ensure_outdir(a.outdir)
    payload = DEMO_INPUT if a.demo else at.read_json(a.input)
    product = payload.get("product", "未提供")
    width = int(payload.get("width") or 750)
    screens = payload.get("screens", [])
    if not screens:
        print("[失败处理] screens 为空（输入缺失），流程中止。", file=sys.stderr)
        sys.exit(1)

    # 步骤 1：结构编排（屏型校验 + 高度预算）
    rows = []
    for i, s in enumerate(screens, 1):
        t = s.get("type", "")
        if t not in VALID_TYPES:
            print(f"[失败处理] 第 {i} 屏 type 非法：{t}（可用：{'/'.join(VALID_TYPES)}）", file=sys.stderr)
            sys.exit(1)
        h = int(s.get("height") or 0)
        if h <= 0:
            print(f"[失败处理] 第 {i} 屏高度非法：{h}", file=sys.stderr)
            sys.exit(1)
        lo, hi = TYPE_HEIGHT[t]
        note = "待补参数（不编造，人工核对后方可交付）" if t == "spec" and not (s.get("text") or "").strip() else ""
        rows.append({"#": i, "屏型": VALID_TYPES[t], "标题": s.get("title", ""),
                     "内容摘要": note or (s.get("text", "") or "")[:40], "高度px": h,
                     "高度建议": f"{lo}-{hi}px"})
    total = sum(r["高度px"] for r in rows)

    # 步骤 3：全文合规扫描（先扫全部文案，红线屏打回）
    full_text = " ".join(f"{s.get('title', '')} {s.get('text', '')}" for s in screens)
    pc_in = os.path.join(a.outdir, "_precheck_in.json")
    at.write_json({"platform": payload.get("platform", "通用"), "text": full_text}, pc_in)
    pc_out = os.path.join(a.outdir, "step3_合规扫描")
    run([sys.executable, PRECHECK, "--input", pc_in, "--outdir", pc_out], "precheck(全文)")
    pc = at.read_json(os.path.join(pc_out, "precheck.json"))
    hits = pc.get("hits", [])
    n_red = sum(1 for x in hits if "红线" in x["级别"])
    # 红线归属：按命中规则与片段在对应屏文案中定位
    per_screen = []
    for r in rows:
        s = screens[r["#"] - 1]
        txt = f"{s.get('title', '')} {s.get('text', '')}"
        red = [x for x in hits if x["原文片段"] and x["原文片段"] in txt and "红线" in x["级别"]]
        warn = [x for x in hits if x["原文片段"] and x["原文片段"] in txt and "警告" in x["级别"]]
        per_screen.append({"#": r["#"], "屏型": r["屏型"], "红线": len(red), "警告": len(warn),
                           "状态": "❌ 打回改文案" if red else "✅"})
        r["合规"] = "✅ 0 红线" if not red else f"❌ {len(red)} 红线"

    # 步骤 2：关键屏落位（首屏 + 第一个卖点屏）
    grid_files, layout_rows = [], []
    key_idx = [r["#"] for r in rows if r["屏型"] == "首屏钩子"][:1]
    key_idx += [r["#"] for r in rows if r["屏型"] == "卖点"][:1]
    for idx in key_idx:
        s = screens[idx - 1]
        h = int(s["height"])
        lay_in = os.path.join(a.outdir, f"_layout_in_{idx}.json")
        at.write_json({
            "product": f"{product} · 第{idx}屏",
            "platform": payload.get("platform", "通用"), "purpose": "详情模块",
            "canvas": f"{width}x{h}", "bg_color": "#F7F5F0",
            "blocks": [
                {"level": "title", "text": s.get("title", ""), "x": 56, "y": 56,
                 "w": width - 112, "size": math.ceil(width * 0.05), "color": "#2B2B2B", "bold": True},
                {"level": "subtitle", "text": (s.get("text", "") or "")[:18], "x": 56, "y": 150,
                 "w": width - 112, "size": math.ceil(width * 0.035), "color": "#4A4A4A"}
            ]
        }, lay_in)
        lay_out = os.path.join(a.outdir, "step2_关键屏栅格", f"第{idx}屏")
        run([sys.executable, GRID, "--input", lay_in, "--outdir", lay_out], f"grid(第{idx}屏)")
        gj = at.read_json(os.path.join(lay_out, "layout_check.json"))
        grid_files.append(os.path.abspath(os.path.join(lay_out, "版式栅格示意图.png")))
        layout_rows.append({"屏": f"第{idx}屏", "版式判定": gj["summary"]["整体判定"],
                            "文字面积": gj["summary"]["文字面积"]})

    # 步骤 4：长图规格校验
    layout_ok = all(r["版式判定"] == "通过" for r in layout_rows) if layout_rows else True
    if total > MAX_TOTAL_HEIGHT:
        height_verdict = (f"❌ 超长 {total - MAX_TOTAL_HEIGHT}px（裁剪建议：合并相近卖点屏 → "
                          f"删最弱卖点 → 压缩 FAQ 至 500px）")
        deliver = "❌ 不可交付（超长）"
    elif n_red > 0:
        deliver = "❌ 不可交付（存在红线屏，先清零）"
    elif not layout_ok:
        deliver = "❌ 不可交付（关键屏版式检查未过，按整改指令调整后重跑）"
    else:
        height_verdict = f"✅ {total}px / 上限 {MAX_TOTAL_HEIGHT}px"
        deliver = "✅ 可交付"

    summary = {
        "商品": product,
        "详情页宽度": f"{width}px",
        "屏数": len(rows),
        "总高度": f"{total}px / 上限 {MAX_TOTAL_HEIGHT}px",
        "长图校验": height_verdict,
        "合规红线": f"{n_red}（清零才可交付）",
        "整体判定": deliver,
        "人工确认点": "规格参数与实物核对；背书证据可出示；交付制作前人工过目",
        "说明": "高度/合规/版式均脚本实测；卖点排序与屏型归属逻辑见 prompt.txt 五屏方法论",
    }

    xlsx = at.write_excel(
        os.path.join(a.outdir, "详情页结构方案.xlsx"),
        {"结构表": rows, "逐屏合规": per_screen, "关键屏版式": layout_rows or [{"屏": "（无）"}],
         "违规命中": hits or [{"级别": "（无）", "原文片段": "", "命中规则": "", "建议改法": ""}],
         "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()]},
        highlights={"逐屏合规": {"状态": "contains:❌"},
                    "违规命中": {"级别": "contains:红线"}},
        widths={"结构表": {"内容摘要": 40}, "违规命中": {"建议改法": 40}},
    )

    lay_desc = "、".join(f"{r['屏']} {r['版式判定']}（文字面积 {r['文字面积']}）"
                         for r in layout_rows) or "未生成"
    md = [
        f"# 详情页结构方案 —— {product}（宽 {width}px）", "",
        "| # | 屏型 | 标题 | 高度px | 合规 |", "|---|---|---|---|---|",
    ] + ["| {#} | {屏型} | {标题} | {高度px} | {合规} |".format(**r) for r in rows] + [
        "", "## 长图与合规校验", "",
        f"- 总高度：{height_verdict}",
        f"- 合规红线：{n_red}（precheck 全文扫描，明细见 `step3_合规扫描/`）",
        f"- 关键屏落位：{lay_desc}",
        "",
        f"**整体判定：{deliver}**", "",
        "> 本方案由 run_flow.py 实跑生成（AI 生成内容）；交付制作前须人工核对规格参数与背书证据。",
    ]
    md_path = os.path.join(a.outdir, "详情页结构方案.md")
    with open(md_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(md))

    result = {
        "flow": "detail-page-layout-flow",
        "steps": [
            {"step": 1, "skill": "（内置）五屏结构编排", "status": "ok", "screens": len(rows), "total_height": total},
            {"step": 2, "skill": "copy-layout", "status": "ok", "screens": [f"第{i}屏" for i in key_idx]},
            {"step": 3, "skill": "platform-compliance-precheck", "status": "ok", "red_lines": n_red},
            {"step": 4, "skill": "（内置）长图规格校验", "status": "ok", "verdict": height_verdict},
            {"step": 5, "skill": "（人工）核对后交付制作", "status": "pending"},
        ],
        "summary": summary,
        "files": [xlsx, md_path] + grid_files,
        "generated_at": at.stamp(),
    }
    at.write_json(result, os.path.join(a.outdir, "detail_flow_result.json"))
    print(f"{len(rows)} 屏 · 总高 {total}px · 红线 {n_red} —— 判定：{deliver}")
    for f in result["files"]:
        print(" 产物:", f)
    at.emit(result)


if __name__ == "__main__":
    main()
