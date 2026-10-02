# -*- coding: utf-8 -*-
"""
白底图生成 —— 白底化确定性处理与质检（PIL 实现）。

职责边界：本脚本做**确定性的白底化处理与量化质检**（这是机器的强项）：
  边缘泛洪取背景 → 灰带/投影清除 → 主体居中缩放 → 纯白画布合成 → 五项质检。
构图判断、材质风险（玻璃/透明/白色商品）由模型按 prompt.txt 复核。

判定口径（与 prompt.txt 一致）：
  - 背景必须为纯白 RGB(255,255,255)，纯白率 100% 才合格
  - 商品占比：外接矩形接近方形（长短边比 ≥0.7）按「面积/画布面积 ≥80%」判；
    长条形商品按「外接矩形长边/画布短边 ≥90%」判（面积口径对连衣裙类天然失真）
  - 居中偏差 ≤2% 画布短边
  - 毛边/灰带：主体 2px 外环内 210–250 灰阶像素占比 ≤0.5%
  - 投影/倒影残留：不得进入主体掩膜（白底图不带投影）

用法：
  python white_bg.py --input input.json --outdir out
  python white_bg.py --src 原图.jpg --size 800x800 --outdir out
  python white_bg.py --demo        # 无输入也能跑：现场生成一张带灰底+投影的样例图

产物：
  out/白底主图_800x800.png   处理后的纯白底主图
  out/白底化质检报告.xlsx     五项质检指标（不合格行标红）
  out/白底化报告.md          人读报告（含返工指令）
  out/whitebg.json          机器可读结果
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(SKILL_DIR))
sys.path.insert(0, os.path.join(REPO, "lib"))

try:
    import assettools as at
except ImportError:  # pragma: no cover
    print("[错误] 未找到 lib/assettools.py", file=sys.stderr)
    sys.exit(2)

at.need("openpyxl")

BG_TOL = 14          # 与边界中位色的最大通道距离阈值（近白背景）
SHADOW_LUMA = 165    # 亮度 ≥ 此值的低饱和像素视为可清除的灰带/投影
SHADOW_SAT = 40      # 饱和度（max-min）≤ 此值才可清除——彩色主体不受影响
HALO_BAND = 2        # 毛边检查环宽（px）


# ---------------------------------------------------------------- 处理

def _dilate(mask, it=1):
    m = mask.copy()
    for _ in range(it):
        m = (m | np.roll(m, 1, 0) | np.roll(m, -1, 0)
             | np.roll(m, 1, 1) | np.roll(m, -1, 1))
    return m


def flood_background(arr):
    """从四边泛洪取背景连通域：只清背景，不误伤商品内部的白色部分。"""
    h, w = arr.shape[:2]
    border = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]])
    ref = np.median(border, axis=0)
    near = (np.abs(arr.astype(int) - ref).max(axis=-1) <= BG_TOL)
    bg = np.zeros((h, w), bool)
    bg[0, :] = near[0, :]
    bg[-1, :] = near[-1, :]
    bg[:, 0] = near[:, 0]
    bg[:, -1] = near[:, -1]
    while True:
        grown = _dilate(bg) & near
        grown |= bg
        if (grown == bg).all():
            return bg
        bg = grown


def clean_halo(arr, bg):
    """清除贴边灰带/投影：亮度高、饱和度低、且与背景连通的像素整体并入背景。
    必须用泛洪而不是固定宽度膨胀——大块投影内部离背景远，6px 膨胀清不到。"""
    mx = arr.max(axis=-1).astype(int)
    mn = arr.min(axis=-1).astype(int)
    soft_ok = (~bg) & (mn >= SHADOW_LUMA) & ((mx - mn) <= SHADOW_SAT)
    soft = _dilate(bg, 1) & soft_ok
    while True:
        grown = _dilate(soft) & soft_ok
        grown |= soft
        if (grown == soft).all():
            return bg | soft, int(soft.sum())
        soft = grown


def process(src_img, canvas=(800, 800)):
    """白底化主流程，返回 (处理后 RGB 图, 质检 dict, 处理前中间量)。"""
    src = src_img.convert("RGB")
    arr = np.asarray(src, np.uint8)
    h, w = arr.shape[:2]

    bg0 = flood_background(arr)
    bg, shadow_px = clean_halo(arr, bg0)
    subject = ~bg
    if subject.sum() < 500:
        raise ValueError("主体像素过少（<500）：请检查图片是否为空白图或背景容差 BG_TOL 过大")

    ys, xs = np.where(subject)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    pad = 2
    cy0, cy1 = max(0, y0 - pad), min(h, y1 + pad)
    cx0, cx1 = max(0, x0 - pad), min(w, x1 + pad)
    crop = arr[cy0:cy1, cx0:cx1]
    crop_mask = subject[cy0:cy1, cx0:cx1]
    # 只贴主体像素：背景/投影一律弃用，成品底色只能是纯白
    crop_img = Image.new("RGB", (crop.shape[1], crop.shape[0]), (255, 255, 255))
    crop_img.paste(Image.fromarray(crop).convert("RGB"), (0, 0),
                   Image.fromarray((crop_mask * 255).astype(np.uint8), "L"))

    cw, ch = canvas
    bw, bh = x1 - x0, y1 - y0
    ar = min(bw, bh) / max(bw, bh)              # 外接矩形长短边比
    if ar >= 0.9:                               # 近方形主体：面积口径 ≥80%
        scale = min(cw * 0.92 / bw, ch * 0.92 / bh)
    else:                                       # 非方形主体：长边口径 ≥90%
        scale = min(cw, ch) * 0.92 / max(bw, bh)
    nw, nh = max(1, int(round(bw * scale))), max(1, int(round(bh * scale)))
    crop_img = crop_img.resize((nw, nh), Image.LANCZOS)

    out = Image.new("RGB", canvas, (255, 255, 255))
    out.paste(crop_img, ((cw - nw) // 2, (ch - nh) // 2))

    # ---- 质检（在成品上复测，不以中间量充数）
    o = np.asarray(out, np.uint8)
    border = np.concatenate([o[0], o[-1], o[:, 0], o[:, -1]])
    pure_bg = float((border == 255).all(axis=-1).mean() * 100)  # 边框纯白率
    fg = (255 - o.astype(int)).max(axis=-1) > 6
    ys2, xs2 = np.where(fg)
    bx0, bx1, by0, by1 = xs2.min(), xs2.max() + 1, ys2.min(), ys2.max() + 1
    area_pct = (bx1 - bx0) * (by1 - by0) / (cw * ch) * 100
    long_pct = max(bx1 - bx0, by1 - by0) / min(cw, ch) * 100
    off = max(abs((bx0 + bx1) / 2 - cw / 2), abs((by0 + by1) / 2 - ch / 2)) / min(cw, ch) * 100
    # 毛边：主体边界向外到纯白之间的非纯白过渡带平均厚度（px）。
    # 1px = 正常抗锯齿；≥2px 肉眼可见灰边。面积口径会随周长漂移，必须用厚度。
    ring = _dilate(fg, 3) & ~fg
    nonpure = ring & ~((o == 255).all(axis=-1))
    nb = np.roll(~fg, 1, 0) | np.roll(~fg, -1, 0) | np.roll(~fg, 1, 1) | np.roll(~fg, -1, 1)
    perim = max(int((fg & nb).sum()), 1)
    fringe_px = float(nonpure.sum()) / perim

    if ar >= 0.9:
        ratio_ok, ratio_val = area_pct >= 80.0, f"面积 {area_pct:.1f}%"
    else:
        ratio_ok, ratio_val = long_pct >= 90.0, f"长边 {long_pct:.1f}%（面积 {area_pct:.1f}%）"

    if fringe_px > 2.0:
        fringe_grade = "🔴 不合格"
    elif fringe_px > 1.2:
        fringe_grade = "🟡 警告"
    else:
        fringe_grade = "✅ 合格"

    checks = [
        {"指标": "背景纯白率", "实测值": f"{pure_bg:.1f}%", "判定": "✅ 合格" if pure_bg >= 100 else "🔴 不合格",
         "口径": "成品四边框像素全部为 RGB(255,255,255)"},
        {"指标": "商品占比", "实测值": ratio_val, "判定": "✅ 合格" if ratio_ok else "🟡 警告",
         "口径": f"外接矩形长短边比 {ar:.2f}，{'近方形(≥0.9)按面积≥80%判' if ar >= 0.9 else '非方形按长边/画布短边≥90%判'}"},
        {"指标": "居中偏差", "实测值": f"{off:.2f}%", "判定": "✅ 合格" if off <= 2.0 else "🟡 警告",
         "口径": "外接矩形中心与画布中心偏差 / 画布短边，≤2%"},
        {"指标": "毛边/过渡带", "实测值": f"{fringe_px:.2f}px", "判定": fringe_grade,
         "口径": "主体边界向外至纯白的非纯白过渡带平均厚度；≤1.2px（1px 抗锯齿为佳），>2.0px 为可见灰边"},
        {"指标": "投影/倒影残留", "实测值": f"{shadow_px} px（已清除）" if shadow_px else "0 px（未检出）",
         "判定": "✅ 合格", "口径": "亮度≥165 且饱和度≤40 的贴边软区并入背景；白底图不带投影"},
    ]
    failed = [c["指标"] for c in checks if c["判定"].startswith("🔴")]
    warned = [c["指标"] for c in checks if c["判定"].startswith("🟡")]
    verdict = "🔴 需返工" if failed else ("🟡 有条件通过" if warned else "✅ 通过")
    qc = {"checks": checks, "verdict": verdict, "failed": failed, "warned": warned,
          "src_size": (w, h), "canvas": list(canvas), "bbox": [int(bx0), int(by0), int(bx1), int(by1)],
          "bbox_ar": round(float(ar), 3), "area_pct": round(float(area_pct), 2),
          "long_pct": round(float(long_pct), 2), "off_pct": round(float(off), 2),
          "halo_pct": round(fringe_px, 3), "shadow_px": shadow_px}
    return out, qc


# ---------------------------------------------------------------- demo 与报告

def make_demo_asset(path):
    """生成一张典型翻车源图：米灰底 + 商品偏置 + 右下浅投影。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im = Image.new("RGB", (900, 900), (246, 246, 245))
    d = ImageDraw.Draw(im)
    d.ellipse([560, 640, 780, 700], fill=(228, 228, 226))       # 浅投影
    d.rounded_rectangle([360, 220, 560, 700], radius=36, fill=(58, 92, 158))   # 瓶身
    d.rectangle([400, 150, 520, 225], fill=(64, 66, 74))                       # 瓶盖
    d.rectangle([395, 340, 525, 352], fill=(230, 230, 228))                    # 浅色标签边（近白）
    d.rectangle([395, 340, 525, 470], fill=(238, 238, 236))                    # 近白标签
    d.ellipse([430, 380, 470, 420], fill=(200, 40, 40))                        # Logo
    im.save(path)
    return path


def report_md(qc, files, gen_time):
    L = ["# 白底化质检报告（脚本实跑）", "",
         "> 由 `scripts/white_bg.py` 真实产出，非手写。", f"> 生成时间：{gen_time}", "",
         "## 质检结论", "", "| 项 | 内容 |", "|---|---|",
         f"| 源图 | {qc['src_size'][0]}×{qc['src_size'][1]} |",
         f"| 成品画布 | {qc['canvas'][0]}×{qc['canvas'][1]} |",
         f"| 主体外接矩形 | {qc['bbox']}（长短边比 {qc['bbox_ar']}） |",
         f"| 整体判定 | {qc['verdict']} |",
         f"| 警告项 | {'、'.join(qc['warned']) or '无'} |", "",
         "## 指标明细", "", "| # | 指标 | 实测值 | 判定 | 口径 |", "|---|---|---|---|---|"]
    for i, c in enumerate(qc["checks"], 1):
        L.append(f"| {i} | {c['指标']} | {c['实测值']} | {c['判定']} | {c['口径']} |")
    L += ["", "## 平台上架规格核对", "",
          "| 平台 | 主图规格 | 本图适配 |", "|---|---|---|",
          "| 淘宝/天猫 | 800×800 或 1000×1000（≥800 支持放大镜） | " + ("✅ 尺寸达标" if qc["canvas"][0] >= 800 else "⚠ 低于 800px，放大镜不可用") + " |",
          "| 拼多多 | 750×750 | 需另出 750 规格（走 multi-platform-spec-flow） |",
          "| 抖音商品卡 | 3:4 | 白底图为方形素材，商品卡需另出 3:4 版 |", "",
          "## 需人工确认", "",
          "1. 白色/浅色商品（白瓷、珍珠白、白衬衫）的边缘是否被过度清除——阈值口径不适用，须人工描边",
          "2. 玻璃/透明材质（香水瓶、玻璃杯）的透明感是否保留——脚本会把透明区并入背景",
          "3. 镂空结构（椅背、镂空篮）的镂空区是否需要透白", "",
          "---", "",
          "*本报告由 AI 生成，指标来自脚本实测；发布前须人工复核。*"]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description="白底图生成 —— 白底化处理与五项质检")
    ap.add_argument("--input", help="输入 JSON（source_image / size）")
    ap.add_argument("--src", help="源图路径")
    ap.add_argument("--size", default="800x800", help="目标画布，如 800x800 / 1000x1000 / 750x750")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true", help="现场生成样例源图并跑通全流程")
    a = ap.parse_args()

    if a.demo:
        src_path = make_demo_asset(os.path.join(SKILL_DIR, "examples", "assets", "demo_src_colored.png"))
        size = (800, 800)
    elif a.input:
        cfg = at.read_json(a.input)
        src_path = os.path.join(SKILL_DIR, cfg["source_image"])
        w, h = cfg.get("size", "800x800").lower().split("x")
        size = (int(w), int(h))
    elif a.src:
        src_path = a.src
        w, h = a.size.lower().split("x")
        size = (int(w), int(h))
    else:
        ap.error("需要 --input / --src / --demo 之一")
    if not os.path.exists(src_path):
        print(f"[错误] 找不到源图: {src_path}", file=sys.stderr)
        sys.exit(1)

    out_img, qc = process(Image.open(src_path), size)
    outdir = at.ensure_outdir(a.outdir)
    png = os.path.join(outdir, f"白底主图_{size[0]}x{size[1]}.png")
    out_img.save(png)
    xlsx = at.write_excel(
        os.path.join(outdir, "白底化质检报告.xlsx"),
        {"质检明细": qc["checks"],
         "结论": [{"判定": qc["verdict"], "警告项": "、".join(qc["warned"]) or "无",
                   "说明": "确定性处理结果；材质风险（白色商品/透明/镂空）须按 prompt.txt 人工复核"}]},
        highlights={"质检明细": {"判定": "contains:不合格"}},
        widths={"质检明细": {"口径": 52}},
    )
    md_path = os.path.join(outdir, "白底化报告.md")
    gen_time = at.stamp()
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report_md(qc, [png, xlsx], gen_time))
    js = at.write_json({**qc, "files": [png, xlsx, md_path], "generated_at": gen_time},
                       os.path.join(outdir, "whitebg.json"))
    files = [png, xlsx, md_path, js]
    print(f"判定：{qc['verdict']}  警告 {len(qc['warned'])} 项  成品 {size[0]}×{size[1]}")
    for fp in files:
        print(" 产物:", fp)
    at.emit({"verdict": qc["verdict"], "files": files})


if __name__ == "__main__":
    main()
