# -*- coding: utf-8 -*-
"""
文案排版 —— 版式栅格示意图与四项量化检查（PIL 实现）。

职责边界：本脚本做**确定性的栅格绘制与量化检查**（这是机器的强项）：
  12 栏栅格绘制 → 文字块按坐标落位 → 字号/对比度/文字面积/安全边距/商品区重叠五项检查。
版式结构选型、删字、给生图工具的排版提示词由模型按 prompt.txt 完成（这是模型的强项）。

检查口径（与 prompt.txt 一致，以 800px 宽画布为基准按比例换算）：
  - 字号：主标题 ≥ 画布宽 5%，副标题 ≥ 3.5%，卖点条 ≥ 3%
  - 对比度：WCAG 相对亮度比，正文 ≥4.5:1，大标题（≥40px@800 粗体）≥3.0:1
  - 文字面积：抖音商品卡 ≤20%；淘宝/天猫主图除 Logo 外禁文字（出现任何文字块即 FAIL）
  - 安全边距：短边 6%（小红书 8%），文字块不得侵入
  - 商品区：文字块与 product_zone 不得重叠

用法：
  python grid_preview.py --input input.json --outdir out
  python grid_preview.py --demo              # 用内置样例跑一遍
产物：
  out/版式栅格示意图.png   栅格 + 文字块落位示意图（非成品图）
  out/版式检查报告.md      四项检查明细与整改指令
  out/layout_check.json    机器可读结果
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(SKILL_DIR))
sys.path.insert(0, os.path.join(REPO, "lib"))

try:
    import assettools as at
except ImportError:  # pragma: no cover
    print("[错误] 未找到 lib/assettools.py", file=sys.stderr)
    sys.exit(2)

at.need("matplotlib")  # 仅用于确认绘图环境；实际绘制用 PIL

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

# 平台文字面积上限（% 画布面积）；淘宝/天猫主图 = 0（除品牌 Logo 外禁文字）
AREA_LIMIT = {"淘宝": {"主图": 0, "默认": None}, "天猫": {"主图": 0, "默认": None},
              "抖音": {"默认": 20}, "拼多多": {"默认": 25}, "小红书": {"默认": None}}
MIN_CONTRAST_BODY = 4.5
MIN_CONTRAST_TITLE = 3.0

FONT_CANDIDATES = ["msyhbd.ttc", "msyh.ttc", "simhei.ttf", "Deng.ttf", "arial.ttf"]

DEMO = {
    "product": "便携电热水杯（316L 内胆）",
    "platform": "抖音",
    "purpose": "商品卡",
    "canvas": "900x1200",
    "bg_color": "#F5F1E8",
    "product_zone": {"x": 90, "y": 430, "w": 720, "h": 620},
    "blocks": [
        {"level": "title", "text": "316L 不锈钢内胆", "x": 48, "y": 56, "w": 700, "size": 56,
         "color": "#2B2B2B", "bold": True},
        {"level": "subtitle", "text": "6 小时保温 60 度以上（实验室实测）", "x": 48, "y": 150,
         "w": 700, "size": 34, "color": "#4A4A4A"},
        {"level": "bullet", "text": "一杯多用 · 车载直饮", "x": 48, "y": 1080, "w": 460,
         "size": 22, "color": "#9C8468"},
    ],
}


def _font(size: int, bold: bool = False):
    size = max(int(size), 8)
    names = ([FONT_CANDIDATES[0]] if bold else []) + FONT_CANDIDATES
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def hex_rgb(h):
    h = str(h).lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(rgb):
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg, bg):
    l1, l2 = _luminance(hex_rgb(fg)), _luminance(hex_rgb(bg))
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def check(payload):
    cw, ch = (int(x) for x in payload["canvas"].lower().split("x"))
    scale = cw / 800.0
    platform = payload.get("platform", "通用")
    purpose = payload.get("purpose", "默认")
    limit = AREA_LIMIT.get(platform, {}).get(purpose, AREA_LIMIT.get(platform, {}).get("默认"))
    margin = int(short_edge * 0.08 if platform == "小红书" else short_edge * 0.06) \
        if (short_edge := min(cw, ch)) else 48

    blocks, results = [], []
    area_sum = 0
    for b in payload.get("blocks", []):
        level = b.get("level", "bullet")
        area_sum += b.get("w", 0) * max(int(b.get("size", 0) * 1.5), 0)
        min_size = {"title": 0.05 * cw, "subtitle": 0.035 * cw}.get(level, 0.03 * cw)
        ok_size = b["size"] >= min_size - 1e-6
        ratio = contrast(b["color"], payload.get("bg_color", "#FFFFFF"))
        need_c = MIN_CONTRAST_TITLE if (level == "title" and b["size"] >= 40 * scale and b.get("bold")) else MIN_CONTRAST_BODY
        ok_c = ratio >= need_c - 1e-6
        in_margin = b["x"] >= margin and b["y"] >= margin and \
            b["x"] + b.get("w", 0) <= cw - margin and b["y"] + b["size"] <= ch - margin
        pz = payload.get("product_zone")
        overlap = False
        if pz:
            overlap = not (b["x"] + b.get("w", 0) <= pz["x"] or pz["x"] + pz["w"] <= b["x"] or
                           b["y"] + b["size"] * 1.5 <= pz["y"] or pz["y"] + pz["h"] <= b["y"])
        blocks.append({
            "层级": {"title": "主标题", "subtitle": "副标题"}.get(level, "卖点条"),
            "文案": b.get("text", ""),
            "字号px": b["size"], "字号达标": ok_size,
            "对比度": f"{ratio:.2f}:1", "对比达标": ok_c,
            "边距内": in_margin, "压商品区": overlap,
        })

    area_pct = area_sum / (cw * ch) * 100.0
    area_ok = True if limit is None else area_pct <= limit + 1e-6

    checks = {
        "字号": all(x["字号达标"] for x in blocks),
        "对比度": all(x["对比达标"] for x in blocks),
        "文字面积": area_ok,
        "安全边距": all(x["边距内"] for x in blocks),
        "商品区重叠": not any(x["压商品区"] for x in blocks),
    }
    summary = {
        "商品": payload.get("product", ""),
        "平台/用途": f"{platform} / {purpose}",
        "画布": f"{cw}x{ch}",
        "文字面积": f"{area_pct:.1f}%",
        "面积上限": "无硬性" if limit is None else f"{limit}%",
        "安全边距px": margin,
        "各项检查": {k: ("PASS" if v else "FAIL") for k, v in checks.items()},
        "整体判定": "通过" if all(checks.values()) else "需整改",
    }
    return summary, blocks, {"cw": cw, "ch": ch, "margin": margin, "scale": scale}


def draw_png(payload, info, blocks, path):
    from PIL import ImageDraw
    cw, ch, margin = info["cw"], info["ch"], info["margin"]
    img = Image.new("RGB", (cw, ch), hex_rgb(payload.get("bg_color", "#FFFFFF")))
    d = ImageDraw.Draw(img, "RGBA")

    # 12 栏栅格（栏线画在安全区内）
    cols, gutter = 12, int(16 * info["scale"])
    inner = cw - 2 * margin
    col_w = (inner - (cols - 1) * gutter) / cols
    for i in range(cols + 1):
        x = margin + i * (col_w + gutter) - (gutter if i else 0)
        d.line([(x, 0), (x, ch)], fill=(47, 85, 151, 36), width=2)
    for y in range(0, ch, int(8 * info["scale"] * 4)):  # 32px 基准横网格
        d.line([(0, y), (cw, y)], fill=(47, 85, 151, 18), width=1)

    # 安全边距（红）与商品区（绿）
    d.rectangle([margin, margin, cw - margin, ch - margin], outline=(192, 0, 0, 200), width=3)
    pz = payload.get("product_zone")
    if pz:
        d.rectangle([pz["x"], pz["y"], pz["x"] + pz["w"], pz["y"] + pz["h"]],
                    outline=(84, 130, 53, 255), width=3)
        d.text((pz["x"] + 8, pz["y"] + 6), "商品区", font=_font(20), fill=(84, 130, 53))

    # 文字块（浅底 + 实际字号试排）
    for b in payload.get("blocks", []):
        f = _font(b["size"], b.get("bold"))
        d.rectangle([b["x"], b["y"], b["x"] + b.get("w", 200), b["y"] + int(b["size"] * 1.5)],
                    fill=(255, 255, 255, 120), outline=(112, 48, 160, 255), width=2)
        d.text((b["x"] + 6, b["y"] + 4), b.get("text", ""), font=f, fill=hex_rgb(b["color"]))

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    img.save(path)
    return os.path.abspath(path)


def build(payload, outdir):
    at.ensure_outdir(outdir)
    summary, block_rows, info = check(payload)
    png = draw_png(payload, info, block_rows, os.path.join(outdir, "版式栅格示意图.png"))

    lines = [
        f"# 版式检查报告 —— {summary['商品']}",
        "",
        "| 项 | 内容 |", "|---|---|",
        f"| 平台/用途 | {summary['平台/用途']} |",
        f"| 画布 | {summary['画布']}（12 栏栅格，安全边距 {summary['安全边距px']}px） |",
        f"| 文字面积 | {summary['文字面积']}（上限 {summary['面积上限']}，脚本实测） |",
        f"| 整体判定 | **{summary['整体判定']}** |",
        "",
        "## 文字块明细",
        "",
        "| 层级 | 文案 | 字号px | 字号达标 | 对比度 | 对比达标 | 边距内 | 压商品区 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in block_rows:
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
            r["层级"], r["文案"], r["字号px"], "✅" if r["字号达标"] else "❌",
            r["对比度"], "✅" if r["对比达标"] else "❌",
            "✅" if r["边距内"] else "❌", "❌ 有" if r["压商品区"] else "✅ 无"))
    fails = [k for k, v in summary["各项检查"].items() if v == "FAIL"]
    lines += ["", "## 整改指令（如有）", ""]
    if not fails:
        lines.append("四项量化检查全部通过。栅格示意图仅供落位参考，成品图由设计工具按坐标制作。")
    else:
        for f in fails:
            if f == "字号":
                lines.append("- **字号**：主标题 ≥ 画布宽 5%、副标题 ≥3.5%、卖点条 ≥3%（800 基准），低于底线的文字块加大或删除")
            elif f == "对比度":
                lines.append("- **对比度**：正文 ≥4.5:1、大标题粗体 ≥3.0:1（WCAG 亮度比），换文字色或加深色底条")
            elif f == "文字面积":
                lines.append(f"- **文字面积**：{summary['文字面积']} 超出上限 {summary['面积上限']}，删辅助卖点或缩小文字块宽度")
            elif f == "安全边距":
                lines.append(f"- **安全边距**：文字块须整体位于边距 {summary['安全边距px']}px 内，防止平台圆角裁切")
            else:
                lines.append("- **商品区重叠**：文字块与商品区不得重叠，调整 y 坐标或缩短文字块宽度")
    lines += ["", "---", "*本报告由 grid_preview.py 实跑生成；版式结构选型与排版提示词见 prompt.txt。*"]
    md_path = os.path.join(outdir, "版式检查报告.md")
    with open(md_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines))

    js = at.write_json({"summary": summary, "blocks": block_rows, "generated_at": at.stamp()},
                       os.path.join(outdir, "layout_check.json"))
    return {"files": [png, md_path, js], "summary": summary}


def main():
    ap = argparse.ArgumentParser(description="文案排版 —— 栅格示意图与版式检查")
    ap.add_argument("--input", help="输入 JSON（product/platform/canvas/blocks…）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true", help="用内置样例跑一遍")
    a = ap.parse_args()

    payload = DEMO if a.demo else at.read_json(a.input) if a.input else ap.error("需要 --input / --demo 之一")
    r = build(payload, a.outdir)
    s = r["summary"]
    print(f"版式检查：{s['整体判定']}（文字面积 {s['文字面积']} / 上限 {s['面积上限']}）")
    for k, v in s["各项检查"].items():
        print(f"  {k}: {v}")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
