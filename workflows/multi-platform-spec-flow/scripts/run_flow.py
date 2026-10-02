# -*- coding: utf-8 -*-
"""
多平台规格一键适配 —— 端到端编排脚本。

编排逻辑（与 SKILL.md 的 DAG 一致）：
  主素材 → [white-bg-image-generate] 白底归一 800×800 + 五项质检
         → [内置] 平台规格计算（画布/适配模式/缩放比/商品占比/留白区）
         → [内置] 适配示意图 PNG + 逐平台上传检查项
         → [人工] 逐平台上传确认

失败处理：
  - white_bg.py 退出码 != 0 或白底主图缺失 → 中止并打印 stderr
  - 白底质检不合格（whitebg.json 判定）→ 中止，质检报告路径写进错误信息
  - 平台不在基线表 → 该平台行标「自定平台，需人工给规格」，不阻塞其他平台
  - 示意图绘制失败 → 标「示意图缺失」，不阻塞规格表

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo
"""
from __future__ import annotations

import argparse
import glob
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

at.need("matplotlib")  # 环境确认；绘制用 PIL
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

WHITE_BG = os.path.join(REPO, "skills", "white-bg-image-generate", "scripts", "white_bg.py")

# 平台规格基线（2026-09 整理，以上传页实时提示为准）
BASELINE = {
    "淘宝": {"canvas": (800, 800), "ratio": "1:1", "rule": "≥800px 支持放大镜；除品牌 Logo 外禁文字/边框"},
    "天猫": {"canvas": (800, 800), "ratio": "1:1", "rule": "同淘宝主图规范；禁牛皮癣"},
    "拼多多": {"canvas": (750, 750), "ratio": "1:1", "rule": "白底；商品占比 ≥80% 更易过审"},
    "抖音": {"canvas": (900, 1200), "ratio": "3:4", "rule": "主图文字 ≤画面 20%；商品完整可见"},
    "小红书": {"canvas": (1080, 1440), "ratio": "3:4", "rule": "贴边内容被圆角裁切，安全边距 8%"},
}

DEMO_INPUT = {
    "product": "便携电热水杯（316L 内胆）",
    "platforms": ["淘宝", "拼多多", "抖音", "小红书"],
}


def _font(size):
    for name in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def step1_whitebg(payload, outdir):
    """白底归一：调 white-bg-image-generate/scripts/white_bg.py。"""
    sub = os.path.join(outdir, "step1_白底归一")
    if payload.get("source_image"):
        src = payload["source_image"]
        if not os.path.exists(src):
            print(f"[失败处理] 源图不存在：{src}", file=sys.stderr)
            sys.exit(1)
        cmd = [sys.executable, WHITE_BG, "--src", src, "--size", "800x800", "--outdir", sub]
    else:
        cmd = [sys.executable, WHITE_BG, "--demo", "--size", "800x800", "--outdir", sub]
    r = subprocess.run(cmd, cwd=FLOW_DIR, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"[失败处理] white_bg.py 退出码 {r.returncode}，流程中止。", file=sys.stderr)
        print(r.stderr[-800:], file=sys.stderr)
        sys.exit(1)
    mains = glob.glob(os.path.join(sub, "白底主图_*.png"))
    if not mains:
        print("[失败处理] 白底主图产物缺失，流程中止。", file=sys.stderr)
        sys.exit(1)
    main_png = os.path.abspath(mains[0])
    js = os.path.join(sub, "whitebg.json")
    qc_ok = True
    if os.path.exists(js):
        qc = at.read_json(js)
        bad = [c for c in qc.get("checks", []) if "不合格" in str(c.get("判定", ""))]
        qc_ok = not bad
        if not qc_ok:
            print("[失败处理] 白底质检不合格项：" +
                  "；".join(f"{c['指标']}={c['实测值']}" for c in bad), file=sys.stderr)
    if not qc_ok:
        print(f"[失败处理] 白底质检不合格：{os.path.join(sub, '白底化质检报告.xlsx')}，"
              f"不合格图不进入适配环节。", file=sys.stderr)
        sys.exit(1)
    return main_png, sub


def compute_specs(img_size, platforms):
    w, h = img_size
    rows = []
    for p in platforms:
        b = BASELINE.get(p)
        if not b:
            rows.append({"平台": p, "画布": "—", "适配模式": "自定平台，需人工给规格",
                         "缩放比": "—", "商品占比": "—", "留白区": "—", "状态": "需人工"})
            continue
        W, H = b["canvas"]
        scale = min(W / w, H / h)
        pw, ph = round(w * scale), round(h * scale)
        pad_lr, pad_tb = (W - pw) // 2, (H - ph) // 2
        area = pw * ph / (W * H) * 100
        status = "✅" if area >= 50 else "❌ 占比过小"
        rows.append({
            "平台": p, "画布": f"{W}x{H}（{b['ratio']}）",
            "适配模式": "contain 等比留白" if pad_lr or pad_tb else "contain 直出（无留白）",
            "缩放比": f"{scale:.3f}", "商品占比": f"{area:.1f}%",
            "留白区": f"左右各 {pad_lr}px / 上下各 {pad_tb}px" if (pad_lr or pad_tb) else "无",
            "状态": status,
        })
    return rows


def draw_schematic(spec_rows, img_size, path):
    """各平台画布适配示意图：2 列排布，商品矩形 + 留白区标注。"""
    cell_w, cell_h, pad = 460, 560, 40
    n = max(len(spec_rows), 1)
    cols = 2
    rows_n = (n + cols - 1) // cols
    img = Image.new("RGB", (cols * cell_w + pad * (cols + 1),
                            rows_n * cell_h + pad * (rows_n + 1)), (250, 250, 248))
    d = ImageDraw.Draw(img)
    for i, row in enumerate(spec_rows):
        cx = pad + (i % cols) * (cell_w + pad)
        cy = pad + (i // cols) * (cell_h + pad)
        d.text((cx, cy), f"{row['平台']}  {row['画布']}", font=_font(20), fill=(47, 85, 151))
        b = BASELINE.get(row["平台"])
        if not b:
            d.text((cx, cy + 40), row["适配模式"], font=_font(18), fill=(192, 0, 0))
            continue
        W, H = b["canvas"]
        # 画布框按单元格等比缩放
        s = min((cell_w - 40) / W, (cell_h - 110) / H)
        cw, ch = W * s, H * s
        x0, y0 = cx + 20, cy + 50
        d.rectangle([x0, y0, x0 + cw, y0 + ch], outline=(120, 120, 120), width=2)
        # 商品矩形（contain 落位居中）
        pw_ratio = min(W / img_size[0], H / img_size[1])
        pw, ph = img_size[0] * pw_ratio * s, img_size[1] * pw_ratio * s
        px = x0 + (cw - pw) / 2
        py = y0 + (ch - ph) / 2
        d.rectangle([px, py, px + pw, py + ph], fill=(232, 225, 210), outline=(84, 130, 53), width=3)
        d.text((px + 4, py + 4), "商品", font=_font(16), fill=(84, 130, 53))
        if row["留白区"] not in ("无", "—"):
            d.text((x0 + 4, y0 + ch + 6), row["留白区"] + f"｜占比 {row['商品占比']}",
                   font=_font(15), fill=(112, 48, 160))
        else:
            d.text((x0 + 4, y0 + ch + 6), f"商品占比 {row['商品占比']}（无留白）",
                   font=_font(15), fill=(112, 48, 160))
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    img.save(path)
    return os.path.abspath(path)


def main():
    ap = argparse.ArgumentParser(description="多平台规格一键适配流程")
    ap.add_argument("--input", help="流程输入 JSON（product/source_image/platforms）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    at.ensure_outdir(a.outdir)
    payload = DEMO_INPUT if a.demo else at.read_json(a.input)
    platforms = payload.get("platforms") or list(BASELINE)

    # 步骤 1：白底归一
    main_png, step1_dir = step1_whitebg(payload, a.outdir)
    img_size = Image.open(main_png).size

    # 步骤 2：规格计算
    rows = compute_specs(img_size, platforms)

    # 步骤 3：示意图
    try:
        schematic = draw_schematic(rows, img_size, os.path.join(a.outdir, "各平台画布适配示意图.png"))
    except Exception as e:  # noqa: BLE001 —— 示意图失败不阻塞规格表
        schematic = ""
        print(f"[失败处理] 示意图绘制失败（不阻塞）：{e}", file=sys.stderr)

    # 步骤 4：上传检查项
    checks = [{"平台": p, "画布要求": f"{BASELINE[p]['canvas'][0]}x{BASELINE[p]['canvas'][1]}（{BASELINE[p]['ratio']}）",
               "上传检查": BASELINE[p]["rule"],
               "状态": "待人工上传确认"}
              for p in platforms if p in BASELINE]
    checks.append({"平台": "通用", "画布要求": "—",
                   "上传检查": "平台规格以上传页实时提示为准；基线表为 2026-09 整理",
                   "状态": "待人工上传确认"})

    summary = {
        "商品": payload.get("product", "未提供"),
        "白底主图": f"{img_size[0]}x{img_size[1]}（step1 质检通过）",
        "适配平台数": len(platforms),
        "自定平台数": sum(1 for r in rows if r["状态"] == "需人工"),
        "人工确认点": "step1 质检报告过目 + 逐平台上传结果回填；驳回原因回写规格表",
        "说明": "缩放比/占比/留白由脚本实测；商品本体零裁切、禁非等比拉伸",
    }

    xlsx = at.write_excel(
        os.path.join(a.outdir, "平台适配规格表.xlsx"),
        {"规格表": rows, "上传检查项": checks,
         "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()]},
        highlights={"规格表": {"状态": "contains:❌"}},
        widths={"规格表": {"适配模式": 24, "留白区": 30}, "上传检查项": {"上传检查": 46}},
    )

    md = [
        f"# 多平台规格适配报告 —— {summary['商品']}", "",
        f"白底主图：{summary['白底主图']}", "",
        "| 平台 | 画布 | 适配模式 | 缩放比 | 商品占比 | 留白区 | 状态 |",
        "|---|---|---|---|---|---|---|",
    ] + ["| {平台} | {画布} | {适配模式} | {缩放比} | {商品占比} | {留白区} | {状态} |".format(**r)
         for r in rows] + [
        "", "## 上传检查项", "",
        "| 平台 | 画布要求 | 上传检查 | 状态 |", "|---|---|---|---|",
    ] + ["| {平台} | {画布要求} | {上传检查} | {状态} |".format(**c) for c in checks] + [
        "",
        f"> 适配示意图：`各平台画布适配示意图.png`；白底归一产物：`step1_白底归一/`。",
        "> 本报告由 run_flow.py 实跑生成；逐平台上传由人工执行并回填结果（AI 生成内容）。",
    ]
    md_path = os.path.join(a.outdir, "平台适配规格报告.md")
    with open(md_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(md))

    result = {
        "flow": "multi-platform-spec-flow",
        "steps": [
            {"step": 1, "skill": "white-bg-image-generate", "status": "ok", "output": main_png, "dir": step1_dir},
            {"step": 2, "skill": "（内置）平台规格计算", "status": "ok", "platforms": len(rows)},
            {"step": 3, "skill": "（内置）适配示意图", "status": "ok" if schematic else "示意图缺失",
             "output": schematic},
            {"step": 4, "skill": "（内置）上传检查项", "status": "ok"},
            {"step": 5, "skill": "（人工）逐平台上传确认", "status": "pending"},
        ],
        "summary": summary,
        "files": [xlsx, md_path] + ([schematic] if schematic else []) + [main_png],
        "generated_at": at.stamp(),
    }
    at.write_json(result, os.path.join(a.outdir, "spec_flow_result.json"))
    print(f"白底主图 {img_size[0]}x{img_size[1]} → {len(rows)} 个平台方案")
    for f in result["files"]:
        print(" 产物:", f)
    at.emit(result)


if __name__ == "__main__":
    main()
