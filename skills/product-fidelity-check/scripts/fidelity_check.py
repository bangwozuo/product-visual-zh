# -*- coding: utf-8 -*-
"""
产品保真校验 —— 生成图与实物图的一致性比对（6 维度）。

职责边界：本脚本做**像素级客观比对**（维度 1-5）。
维度 6（Logo 字形 / 纹理工艺 / 材质）必须由模型或人工完成，脚本给不出结论就写「待人工确认」。

用法：
  python fidelity_check.py --input examples/input.json --outdir out
  python fidelity_check.py --real 实物.jpg --gen 生成.png --outdir out
  python fidelity_check.py --demo          # 内置样例（PIL 现场生成两张图）

产物：
  out/保真校验对比图.png    左右并排对比图（含判定标注）
  out/保真校验报告.xlsx     指标明细 + 判定（不合格行标红）
  out/保真校验报告.md       人读报告（与 examples/output.md 同构）
  out/fidelity.json         机器可读结果
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

at.need("openpyxl", "matplotlib")

THRESHOLDS = {
    "aspect_ratio_diff_pct": (3.0, 1.0),   # >3% 不合格，1-3% 警告
    "delta_e": (6.0, 2.0),                 # >6 不合格（视为不同色），2-6 警告
    "edge_spread_px": (0.2, 0.5),          # <0.2 不合格（硬边），0.2-0.5 警告
    "structure_diff_pct": (8.0, 2.0),      # >8% 不合格，2-8% 警告
    "subject_area_pct": (5.0, 1.0),        # >5% 不合格，1-5% 警告
}


# ---------------------------------------------------------------- 色彩空间


def rgb_to_lab(arr):
    """sRGB(D65) → CIELAB。arr: (...,3) 0-255 float。向量化。"""
    c = arr / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    x = lin @ np.array([[0.4124564, 0.3575761, 0.1804375],
                        [0.2126729, 0.7151522, 0.0721750],
                        [0.0193339, 0.1191920, 0.9503041]], dtype=float)
    xyz_n = np.array([0.95047, 1.0, 1.08883])
    t = x / xyz_n
    delta = 6 / 29
    f = np.where(t > delta ** 3, np.cbrt(t), t / (3 * delta ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16,
                     500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], axis=-1)


def ciede2000(lab1, lab2):
    """CIEDE2000 色差（CIE 142-2001）。lab1/lab2: (...,3)。"""
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cbar = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cbar ** 7 / (Cbar ** 7 + 25.0 ** 7)))
    ap1, ap2 = (1 + G) * a1, (1 + G) * a2
    Cp1, Cp2 = np.hypot(ap1, b1), np.hypot(ap2, b2)
    hp1 = np.degrees(np.arctan2(b1, ap1)) % 360
    hp2 = np.degrees(np.arctan2(b2, ap2)) % 360

    dLp = L2 - L1
    dCp = Cp2 - Cp1
    dhp = hp2 - hp1
    dhp = np.where(Cp1 * Cp2 == 0, 0.0, dhp)
    dhp = np.where(dhp > 180, dhp - 360, dhp)
    dhp = np.where(dhp < -180, dhp + 360, dhp)
    dHp = 2 * np.sqrt(Cp1 * Cp2) * np.sin(np.radians(dhp) / 2)

    Lbp = (L1 + L2) / 2
    Cbp = (Cp1 + Cp2) / 2
    hsum = hp1 + hp2
    hdiff = np.abs(hp1 - hp2)
    hbp = np.where(Cp1 * Cp2 == 0, hsum,
                   np.where(hdiff <= 180, hsum / 2,
                            np.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2)))
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dtheta = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    RC = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7))
    SL = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    SC = 1 + 0.045 * Cbp
    SH = 1 + 0.015 * Cbp * T
    RT = -np.sin(np.radians(2 * dtheta)) * RC
    return np.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2
                   + RT * (dCp / SC) * (dHp / SH))


# ---------------------------------------------------------------- 基础指标


def load_rgb(path):
    return Image.open(path).convert("RGB")


def foreground_mask(arr):
    """前景掩膜：与纯白的最大通道距离 > 30（白底图约定）。"""
    return (255 - arr).max(axis=-1) > 30


def dominant_colors(arr, mask, k=3, levels=16):
    """前景区域内 4bit/通道 量化直方图的 top-k 主色（均值色 + 占比）。"""
    px = arr[mask]
    if len(px) == 0:
        return []
    q = (px // (256 // levels)).astype(int)
    keys = q[:, 0] * levels * levels + q[:, 1] * levels + q[:, 2]
    uniq, counts = np.unique(keys, return_counts=True)
    order = np.argsort(-counts)[:k]
    out = []
    total = len(px)
    for i in order:
        sel = keys == uniq[i]
        mean = px[sel].mean(axis=0)
        out.append({"rgb": tuple(int(round(v)) for v in mean),
                    "pct": round(counts[i] / total * 100, 2)})
    return out


def edge_spread_width(arr):
    """边缘扩散宽度：白底轮廓处「白 → 主体」之间过渡带（抗锯齿带）的平均像素数。
    只统计 4 步内能碰到主体色的方向；走满 4 步还是中间色说明是近白色块，不计。"""
    g = arr.max(axis=-1)  # 白底图上主体通常较暗，用最大通道近似
    spreads = []
    for row in g:
        _scan_line(row, spreads)
    for col in g.T:
        _scan_line(col, spreads)
    return (float(np.mean(spreads)) if spreads else None), len(spreads)


def _scan_line(line, spreads):
    n = len(line)
    white = line >= 245
    body = line < 185  # 距白 >60 的主体色
    i = 0
    while i < n - 1:
        if white[i] and not white[i + 1]:
            j = i + 1
            mid = 0
            # 数「既非纯白也非主体」的中间过渡像素，直到碰到主体色 / 白 / 4 步上限
            while j < n and not white[j] and not body[j] and mid < 4:
                j += 1
                mid += 1
            if j < n and body[j] and mid <= 4:
                spreads.append(mid)  # 硬边=0，超采样/羽化=1-4
            # 走满 4 步仍未到主体 → 近白色块（如白标签），跳过不计
            i = j if j > i else i + 1
        else:
            i += 1


# ---------------------------------------------------------------- 六维比对


def compare(real_img, gen_img, product=""):
    real, gen = np.asarray(real_img, float), np.asarray(gen_img, float)
    rw, rh = real_img.size
    gw, gh = gen_img.size
    ar_real, ar_gen = rw / rh, gw / gh
    ar_diff = abs(ar_real - ar_gen) / ar_real * 100

    # 维度 2：主色 ΔE00（前景掩膜内 top-3 主色配对取最大）
    m_real, m_gen = foreground_mask(real), foreground_mask(gen)
    cols_real, cols_gen = dominant_colors(real, m_real), dominant_colors(gen, m_gen)
    lab_gen = rgb_to_lab(np.array([c["rgb"] for c in cols_gen], float)) if cols_gen else None
    pairs = []
    for cr in cols_real:
        if lab_gen is None or not len(lab_gen):
            break
        lr = rgb_to_lab(np.array([cr["rgb"]], float))
        des = ciede2000(np.repeat(lr, len(lab_gen), axis=0), lab_gen)
        bi = int(np.argmin(des))
        pairs.append({**cr, "gen_rgb": cols_gen[bi]["rgb"], "gen_pct": cols_gen[bi]["pct"],
                      "de": round(float(des[bi]), 2)})
    de_max = max((p["de"] for p in pairs), default=None)

    # 维度 3：边缘扩散宽度（两图各自测，报告以生成图为准）
    es_gen, n_dir_gen = edge_spread_width(gen)
    es_real, _ = edge_spread_width(real)

    # 维度 4：结构差异块（对齐到基准网格，16×16 块）
    gen_aligned = np.asarray(gen_img.resize(real_img.size), float)
    diff_map = np.linalg.norm(real - gen_aligned, axis=-1)  # 0-441
    H, W = diff_map.shape
    bs = 16
    hb, wb = H // bs, W // bs
    blocks = diff_map[:hb * bs, :wb * bs].reshape(hb, bs, wb, bs).mean(axis=(1, 3))
    fg_blocks = (m_real[:hb * bs, :wb * bs].reshape(hb, bs, wb, bs).mean(axis=(1, 3)) > 0.5) | \
                (foreground_mask(gen_aligned)[:hb * bs, :wb * bs].reshape(hb, bs, wb, bs).mean(axis=(1, 3)) > 0.5)
    valid = blocks[fg_blocks]
    n_diff = int((valid > 40).sum())
    sd_pct = n_diff / max(len(valid), 1) * 100
    hot = np.argsort(-blocks.ravel())
    hotspots = []
    for idx in hot[:8]:
        by, bx = divmod(int(idx), wb)
        if blocks[by, bx] <= 40:
            break
        hotspots.append({"block": (bx * bs, by * bs),
                         "center": (bx * bs + bs // 2, by * bs + bs // 2),
                         "fg_px": int(fg_blocks[by, bx]) * bs * bs,
                         "diff": round(float(blocks[by, bx]), 2)})

    # 维度 5：主体面积变化
    area_real = m_real.mean() * 100
    area_gen = m_gen.mean() * 100
    area_diff = abs(area_gen - area_real) / max(area_real, 1e-9) * 100

    def grade(name, val):
        hi, lo = THRESHOLDS[name]
        if name == "edge_spread_px":  # 越大越好
            if val is None:
                return "待人工确认"
            if val < hi:
                return "🔴 不合格"
            if val < lo:
                return "🟡 警告"
            return "✅ 合格"
        if val > hi:
            return "🔴 不合格"
        if val > lo:
            return "🟡 警告"
        return "✅ 合格"

    checks = [
        {"指标": "长宽比偏差", "实测值": f"{ar_diff:.2f}%", "判定": grade("aspect_ratio_diff_pct", ar_diff),
         "度量口径": f"{rw}×{rh} ({ar_real:.4f}) vs {gw}×{gh} ({ar_gen:.4f})"},
        {"指标": "主色 ΔE00（最大）", "实测值": "—" if de_max is None else f"{de_max:.2f}",
         "判定": "待人工确认" if de_max is None else grade("delta_e", de_max),
         "度量口径": f"比对 {len(pairs)} 组主导色（前景掩膜内）"},
        {"指标": "边缘扩散宽度", "实测值": "—" if es_gen is None else f"{es_gen:.4f}px",
         "判定": grade("edge_spread_px", es_gen),
         "度量口径": f"生成图 {n_dir_gen} 个白底轮廓方向均值（基准图 {es_real:.4f}）"},
        {"指标": "结构差异块占比", "实测值": f"{sd_pct:.2f}%", "判定": grade("structure_diff_pct", sd_pct),
         "度量口径": f"{n_diff}/{len(valid)} 前景块平均色差 > 40（16×16 块）"},
        {"指标": "主体面积变化", "实测值": f"{area_diff:.2f}%", "判定": grade("subject_area_pct", area_diff),
         "度量口径": f"前景占比 {area_real:.2f}% → {area_gen:.2f}%"},
        {"指标": "语义级比对", "实测值": "待人工确认", "判定": "—",
         "度量口径": "Logo 字形 / 纹理密度 / 工艺细节需人眼核对，脚本无法判定"},
    ]
    failed = [c["指标"] for c in checks if c["判定"].startswith("🔴")]
    warned = [c["指标"] for c in checks if c["判定"].startswith("🟡")]
    verdict = "🔴 需返工" if failed else ("🟡 有条件通过" if warned else "✅ 通过")
    return {"checks": checks, "verdict": verdict, "failed": failed, "warned": warned,
            "pairs": pairs, "hotspots": hotspots,
            "sizes": {"real": (rw, rh), "gen": (gw, gh)}, "product": product}


# ---------------------------------------------------------------- 产物


def side_by_side(real_img, gen_img, path, verdict):
    plt = at._mpl()
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 4.4))
    for ax, im, tag in zip(axes, (real_img, gen_img), ("基准图（实物）", "待校验生成图")):
        ax.imshow(im)
        ax.set_title(tag, fontsize=12, fontweight="bold")
        ax.axis("off")
    # Emoji（🔴 等）在雅黑无字形会变豆腐块，图内只保留文字
    verdict_txt = verdict.split(" ", 1)[-1] if " " in verdict else verdict
    color = "#548235" if verdict.startswith("✅") else ("#BF8F00" if verdict.startswith("🟡") else "#C00000")
    fig.suptitle(f"产品保真校验 —— 判定：{verdict_txt}", fontsize=13, fontweight="bold", color=color)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(path)


def report_md(r, files, gen_time):
    L = ["# 产品保真校验报告（脚本实跑）", "",
         "> 由 `scripts/fidelity_check.py` 真实产出，非手写。",
         f"> 生成时间：{gen_time}　对比图：`{os.path.basename(files[0])}`", "",
         "## 校验结论", "", "| 项 | 内容 |", "|---|---|",
         f"| 商品 | {r['product'] or '（未命名）'} |",
         f"| 基准图 | {r['sizes']['real'][0]}×{r['sizes']['real'][1]} |",
         f"| 生成图 | {r['sizes']['gen'][0]}×{r['sizes']['gen'][1]} |",
         f"| 整体判定 | {r['verdict']} |",
         f"| 不合格项 | {'、'.join(r['failed']) or '无'} |",
         f"| 警告项 | {'、'.join(r['warned']) or '无'} |", "",
         "## 指标明细", "", "| # | 指标 | 实测值 | 判定 | 度量口径 |", "|---|---|---|---|---|"]
    for i, c in enumerate(r["checks"], 1):
        L.append(f"| {i} | {c['指标']} | {c['实测值']} | {c['判定']} | {c['度量口径']} |")
    if r["pairs"]:
        L += ["", "## 主色比对（CIEDE2000）", "",
              "| 基准主色 | 基准占比 | 生成图最近主色 | 生成占比 | ΔE00 |", "|---|---|---|---|---|"]
        for p in r["pairs"]:
            L.append(f"| RGB{p['rgb']} | {p['pct']}% | RGB{p['gen_rgb']} | {p['gen_pct']}% | **{p['de']}** |")
    if r["hotspots"]:
        L += ["", "## 结构差异热点（Top 8，按平均色差降序）", "",
              "| 区块坐标 | 块中心 | 块内前景像素 | 平均色差(0-441) |", "|---|---|---|---|"]
        for h in r["hotspots"]:
            L.append(f"| {h['block']} | x={h['center'][0]}, y={h['center'][1]} | {h['fg_px']} | {h['diff']} |")
    L += ["", "## 返工指令", "",
          "| # | 问题 | 改法 |", "|---|---|---|"]
    n = 0
    for c in r["checks"]:
        if c["判定"].startswith("🔴"):
            n += 1
            fix = {"长宽比偏差": "画布改回基准图比例，主体等比缩放后重新导出",
                   "边缘扩散宽度": "4× 超采样后降采样，或对抠图蒙版做 0.5–1px 羽化",
                   "结构差异块占比": "按热点坐标定位，对照实物重绘该区域",
                   "主色 ΔE00（最大）": "以实物主色校色后重出",
                   "主体面积变化": "按基准图重新构图 / 等比缩放主体"}.get(c["指标"], "按度量口径整改后复测")
            L.append(f"| {n} | {c['指标']} = {c['实测值']} | {fix} |")
    if n == 0:
        L.append("| — | 无不合格项 | — |")
    L += ["", "## 需人工确认", "",
          "1. Logo / 文字的字形与笔画是否与实物一致",
          "2. 纹理、织法、缝线等工艺细节是否被 AI 改写",
          "3. 材质表现（哑面 / 亮面 / 磨砂 / 透明）是否与实物一致", "",
          "---", "",
          "*本报告由 AI 生成，像素指标来自脚本实测；语义级保真须人工复核后方可上架。*"]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- demo 与主流程


def make_demo_assets():
    """按 examples/input.json 的描述现场生成 demo_ref / demo_gen。"""
    adir = os.path.join(SKILL_DIR, "examples", "assets")
    os.makedirs(adir, exist_ok=True)
    ref_p, gen_p = os.path.join(adir, "demo_ref.png"), os.path.join(adir, "demo_gen.png")
    if os.path.exists(ref_p) and os.path.exists(gen_p):
        return ref_p, gen_p

    base = Image.new("RGB", (800, 800), (255, 255, 255))
    d = ImageDraw.Draw(base)
    d.rounded_rectangle([320, 180, 480, 620], radius=40, fill=(58, 92, 158))   # 瓶身
    d.rectangle([355, 130, 445, 185], fill=(70, 70, 78))                        # 瓶盖
    d.ellipse([385, 300, 415, 330], fill=(200, 40, 40))                         # 红色 Logo 圆点
    for i in range(4):                                                          # 4 条纹理条
        y = 420 + i * 40
        d.rectangle([340, y, 460, y + 12], fill=(149, 147, 141))
    base.save(ref_p)

    gen = base.resize((800, 760), Image.NEAREST)                                # 拉伸 + 无抗锯齿
    d2 = ImageDraw.Draw(gen)
    d2.rounded_rectangle([320, 173, 480, 590], radius=38, outline=(74, 96, 142), width=3)
    gen = gen.point(lambda p: p)  # 保持结构
    # 偏青：整体往 (74,96,142) 方向拉（只调瓶身区域色相较复杂，这里整图轻移）
    arr = np.asarray(gen, np.int16)
    arr[..., 0] = np.clip(arr[..., 0] + 4, 0, 255)
    arr[..., 2] = np.clip(arr[..., 2] - 4, 0, 255)
    gen = Image.fromarray(arr.astype(np.uint8))
    d3 = ImageDraw.Draw(gen)
    d3.ellipse([387, 285, 413, 311], fill=(40, 160, 60))                        # Logo 被画成绿色
    gen.save(gen_p)
    return ref_p, gen_p


def main():
    ap = argparse.ArgumentParser(description="产品保真校验 —— 生成图 vs 实物图（6 维度）")
    ap.add_argument("--input", help="输入 JSON（product/reference_image/target_image）")
    ap.add_argument("--real", help="实物图路径")
    ap.add_argument("--gen", help="生成图路径")
    ap.add_argument("--product", default="", help="商品名 / SKU")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true", help="用内置样例（examples/assets）")
    a = ap.parse_args()

    if a.demo or (a.input and "demo" in a.input):
        ref_p, gen_p = make_demo_assets()
        product = "玻璃瓶装精华液 30ml（SKU: SERUM-30ML-001）"
    elif a.input:
        cfg = at.read_json(a.input)
        ref_p = os.path.join(SKILL_DIR, cfg["reference_image"])
        gen_p = os.path.join(SKILL_DIR, cfg["target_image"])
        product = cfg.get("product", "")
    else:
        ref_p, gen_p, product = a.real, a.gen, a.product
    for p in (ref_p, gen_p):
        if not os.path.exists(p):
            print(f"[错误] 找不到图片: {p}", file=sys.stderr)
            sys.exit(1)

    real_img, gen_img = load_rgb(ref_p), load_rgb(gen_p)
    r = compare(real_img, gen_img, product)
    outdir = at.ensure_outdir(a.outdir)
    png = side_by_side(real_img, gen_img, os.path.join(outdir, "保真校验对比图.png"), r["verdict"])
    xlsx = at.write_excel(
        os.path.join(outdir, "保真校验报告.xlsx"),
        {"指标明细": r["checks"],
         "结论": [{"判定": r["verdict"], "不合格项": "、".join(r["failed"]) or "无",
                   "警告项": "、".join(r["warned"]) or "无",
                   "说明": "像素级比对；语义级校验（Logo/工艺/材质）须人工复核"}]},
        highlights={"指标明细": {"判定": "contains:不合格"}},
    )
    md_path = os.path.join(outdir, "保真校验报告.md")
    gen_time = at.stamp()
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report_md(r, [png, xlsx], gen_time))
    js = at.write_json({**r, "files": [png, xlsx, md_path], "generated_at": gen_time},
                       os.path.join(outdir, "fidelity.json"))
    files = [png, xlsx, md_path, js]
    print(f"判定：{r['verdict']}  不合格 {len(r['failed'])} 项 / 警告 {len(r['warned'])} 项")
    for fp in files:
        print(" 产物:", fp)
    at.emit({"verdict": r["verdict"], "files": files})


if __name__ == "__main__":
    main()
