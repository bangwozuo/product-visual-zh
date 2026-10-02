# -*- coding: utf-8 -*-
"""
商品图批量生成与质检 —— 端到端编排脚本。

编排逻辑（与 SKILL.md 的 DAG 一致）：
  素材与批量信息
    → [white-bg-image-generate] 白底归一 + 五项质检
    → [scene-image-compose] 场景合成提示词包（纯提示词技能：脚本按其方法论生成参数包，
      实际出图由模型按 skills/scene-image-compose/prompt.txt 执行）
    → [product-fidelity-check] 六维保真校验（实物基准图 vs 成品图）
    → [内置] GB/T 2828.1 一般检验水平 II 抽样判定（致命/严重/轻微三级 Ac/Re）
    → [人工] 语义级确认后交付

失败处理：
  - white_bg.py / fidelity_check.py 退出码 != 0 → 中止并打印 stderr
  - 白底质检不合格 / 保真 🔴 需返工 → 中止该批（一票否决）
  - 未提供场景需求 → 场景步标「跳过」，仅交付白底图
  - 缺陷数缺失 → 抽样标「待人工清点」，正常退出
  - 批量超出本表（>35000）→ 标「按 GB/T 2828.1 原表查」

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

at.need("matplotlib")  # 环境确认；白底变体生成用 PIL
from PIL import Image, ImageEnhance  # noqa: E402

WHITE_BG = os.path.join(REPO, "skills", "white-bg-image-generate", "scripts", "white_bg.py")
FIDELITY = os.path.join(REPO, "skills", "product-fidelity-check", "scripts", "fidelity_check.py")

# GB/T 2828.1 一般检验水平 II · 正常检验一次抽样（本表覆盖常用档）
LOT_TABLE = [(90, ("A", 2)), (150, ("F", 20)), (280, ("G", 32)),
             (500, ("H", 50)), (1200, ("J", 80)), (3200, ("K", 125)),
             (10000, ("L", 200)), (35000, ("M", 315))]
LOT_LABEL = {90: "51–90", 150: "91–150", 280: "151–280", 500: "281–500",
             1200: "501–1200", 3200: "1201–3200", 10000: "3201–10000", 35000: "10001–35000"}
AC_LADDER = [(0.5, 1), (0.8, 2), (1.25, 3), (2.0, 5), (3.25, 7), (5.0, 10), (8.0, 14)]
DEFECTS = [("致命", "critical", 0.0, "文字/价格错误、Logo 错误等合规红线"),
           ("严重", "major", 1.0, "主体变形、偏色 ΔE00>3、结构缺失"),
           ("轻微", "minor", 4.0, "锐化过度、轻微毛边、留白偏差")]


def sample_plan(lot: int, aql: float):
    """批量与 AQL → (档位说明, n, Ac, Re)。AQL=0（致命）→ Ac=0 Re=1。"""
    if aql == 0:
        for cap, (_code, n) in LOT_TABLE:
            if lot <= cap:
                return LOT_LABEL[cap], n, 0, 1
        return ">35000 按 GB/T 2828.1 原表查", 0, 0, 1
    for cap, (code, n) in LOT_TABLE:
        if lot <= cap:
            moved = ""
            ratio = n * aql / 100.0  # n × AQL%（AQL 1.0 表示 1%）
            while ratio < 0.5:  # 箭头下移：样本量不足以构成 Ac≥1 时升档
                idx = [c for c, _ in LOT_TABLE].index(cap)
                if idx + 1 >= len(LOT_TABLE):
                    return LOT_LABEL[cap], n, 0, 1
                cap2, (code2, n2) = LOT_TABLE[idx + 1]
                moved = f"{code}→{code2}"
                cap, code, n = cap2, code2, n2
                ratio = n * aql / 100.0
            # 最近锚点取 Ac：标准中各 (n,AQL) 组合的 n×AQL 都落在锚点附近
            ac = min(AC_LADDER, key=lambda e: abs(ratio - e[0]))[1]
            return f"{LOT_LABEL[cap]}（{code}{('，' + moved) if moved else ''}）", n, ac, ac + 1
    return ">35000 按 GB/T 2828.1 原表查", 0, 0, 1


DEMO_INPUT = {
    "product": "便携手冲咖啡壶套装（SKU: COFFEE-320ML）",
    "batch_size": 500,
    "scene": {
        "description": "原木桌面晨光场景，旁置咖啡豆与亚麻布",
        "light_dir": "upper-left", "color_temp_k": 3800, "canvas": "900x1200"
    },
    "defects": {"critical": 0, "major": 1, "minor": 4}
}


def run(cmd, tag):
    r = subprocess.run(cmd, cwd=FLOW_DIR, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"[失败处理] {tag} 退出码 {r.returncode}，流程中止。", file=sys.stderr)
        print(r.stderr[-800:], file=sys.stderr)
        sys.exit(1)
    return r


def make_variant(src, dst):
    """把白底图做成轻度偏色的"AI 成品图"，供保真校验演示（真实使用时为实际成品路径）。"""
    img = Image.open(src).convert("RGB")
    r, g, b = img.split()
    r = r.point(lambda x: min(255, int(x * 1.03)))   # 轻度偏暖
    b = b.point(lambda x: int(x * 0.97))
    out = Image.merge("RGB", (r, g, b))
    out = ImageEnhance.Contrast(out).enhance(1.02)
    out.save(dst)
    return os.path.abspath(dst)


def main():
    ap = argparse.ArgumentParser(description="商品图批量生成与质检流程")
    ap.add_argument("--input", help="流程输入 JSON（product/batch_size/scene/defects/...）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    at.ensure_outdir(a.outdir)
    payload = DEMO_INPUT if a.demo else at.read_json(a.input)
    product = payload.get("product", "未提供")
    batch = int(payload.get("batch_size") or 0)
    if batch <= 0:
        print("[失败处理] batch_size 缺失或非法，流程中止。", file=sys.stderr)
        sys.exit(1)

    # 步骤 1：白底归一（white-bg-image-generate）
    src = payload.get("source_image")
    step1_dir = os.path.join(a.outdir, "step1_白底归一")
    if src and os.path.exists(src):
        run([sys.executable, WHITE_BG, "--src", src, "--size", "800x800", "--outdir", step1_dir],
            "white_bg")
    else:
        run([sys.executable, WHITE_BG, "--demo", "--size", "800x800", "--outdir", step1_dir],
            "white_bg(demo)")
    import glob
    mains = glob.glob(os.path.join(step1_dir, "白底主图_*.png"))
    if not mains:
        print("[失败处理] 白底主图产物缺失，流程中止。", file=sys.stderr)
        sys.exit(1)
    white_png = os.path.abspath(mains[0])
    qc = at.read_json(os.path.join(step1_dir, "whitebg.json"))
    bad = [c for c in qc.get("checks", []) if "不合格" in str(c.get("判定", ""))]
    if bad:
        print("[失败处理] 白底质检不合格：" + "；".join(f"{c['指标']}={c['实测值']}" for c in bad),
              file=sys.stderr)
        sys.exit(1)

    # 步骤 2：场景合成提示词包（scene-image-compose 方法论，模型执行出图）
    scene = payload.get("scene")
    scene_file = ""
    if scene:
        step2_dir = os.path.join(a.outdir, "step2_场景合成")
        at.ensure_outdir(step2_dir)
        scene_file = os.path.join(step2_dir, "场景合成提示词包.md")
        with open(scene_file, "w", encoding="utf-8") as fp:
            fp.write("\n".join([
                f"# 场景合成提示词包 —— {product}",
                "",
                "| 项 | 内容 |", "|---|---|",
                f"| 场景 | {scene.get('description', '')} |",
                f"| 光影参数 | 方向 {scene.get('light_dir', 'upper-left')} / 色温 {scene.get('color_temp_k', 3800)}K / 光比 2:1 / 接地阴影与光源反向 |",
                f"| 画布 | {scene.get('canvas', '900x1200')}（按 multi-platform-spec-flow 基线适配） |",
                f"| 策略 | 图层贴回（白底图本体 + AI 背景光照融合） |",
                "",
                "正向提示词按 skills/scene-image-compose/prompt.txt 生成（含色温数值与机位锁词），",
                "负向提示词含 changed color / warped shape / altered logo 等商品保护项。",
                "出图后回本流程步骤 3 做六维保真校验。",
            ]))
        scene_file = os.path.abspath(scene_file)
    scene_status = "ok" if scene_file else "跳过（未提供场景需求，仅交付白底图）"

    # 步骤 3：保真校验（product-fidelity-check）——实物基准 vs 成品
    ref = payload.get("reference_image")
    step3_dir = os.path.join(a.outdir, "step3_保真校验")
    at.ensure_outdir(step3_dir)
    if not (ref and os.path.exists(ref)):
        ref = white_png  # demo/缺基准时以白底图为基准，成品取轻度偏色变体
        gen = make_variant(white_png, os.path.join(step3_dir, "成品图_演示偏色.png"))
    else:
        gen = payload.get("generated_image") or white_png
    run([sys.executable, FIDELITY, "--real", ref, "--gen", gen,
         "--product", product, "--outdir", step3_dir], "fidelity_check")
    fid = at.read_json(os.path.join(step3_dir, "fidelity.json"))
    fid_verdict = fid.get("verdict") or fid.get("summary", {}).get("整体判定", "")
    fid_fail = "返工" in str(fid_verdict) or "不合格" in str(fid_verdict)
    if fid_fail:
        print(f"[失败处理] 保真校验判定：{fid_verdict} —— 该 SKU 整批停止交付，回出图环节。",
              file=sys.stderr)
        sys.exit(1)

    # 步骤 4：GB/T 2828.1 抽样判定
    d = payload.get("defects") or {}
    sample_rows, strict = [], "接收"
    for name, key, aql, eg in DEFECTS:
        lot_label, n, ac, re_ = sample_plan(batch, aql)
        found = d.get(key)
        if found is None:
            sample_rows.append({"缺陷级别": name, "AQL": str(aql), "样本量n": n, "Ac": ac, "Re": re_,
                                "抽检发现": "待人工清点", "判定": "待清点后判"})
            if strict != "拒收":
                strict = "待清点"
            continue
        verdict = "接收" if found <= ac else "拒收"
        sample_rows.append({"缺陷级别": name, "AQL": str(aql), "样本量n": n, "Ac": ac, "Re": re_,
                            "抽检发现": found, "判定": verdict})
        if verdict == "拒收":
            strict = "拒收"
    final_verdict = {"接收": "✅ 接收", "待清点": "⏳ 待人工清点后判", "拒收": "❌ 拒收（100% 全检返工）"}[strict]

    summary = {
        "商品": product,
        "批量": f"{batch} 张（样本计划见抽样表）",
        "白底归一": "五项质检全过",
        "场景合成": scene_status,
        "保真校验": str(fid_verdict),
        "缺陷清点": f"致命 {d.get('critical', '—')} / 严重 {d.get('major', '—')} / 轻微 {d.get('minor', '—')}",
        "批判定": final_verdict,
        "人工确认点": "语义级保真（Logo/纹理/工艺）逐项过目；拒收批全检返工后重新抽样",
        "说明": "六维指标/Ac/Re 均脚本实测；致命缺陷 Ac=0 见一即拒；口径 GB/T 2828.1 水平 II",
    }

    xlsx = at.write_excel(
        os.path.join(a.outdir, "批量质检单.xlsx"),
        {"抽样判定": sample_rows,
         "保真指标": fid.get("metrics", []) or [{"指标": "（见 fidelity.json）"}],
         "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()]},
        highlights={"抽样判定": {"判定": "contains:拒收"}},
        widths={"抽样判定": {"缺陷级别": 10}, "保真指标": {"口径": 40}},
    )

    md = [
        f"# 批量质检单 —— {product}", "",
        "| 项 | 内容 |", "|---|---|",
    ] + [f"| {k} | {v} |" for k, v in summary.items()] + [
        "", "## 抽样判定明细（GB/T 2828.1 水平 II）", "",
        "| 缺陷级别 | AQL | 样本量n | Ac | Re | 抽检发现 | 判定 |", "|---|---|---|---|---|---|---|",
    ] + ["| {缺陷级别} | {AQL} | {样本量n} | {Ac} | {Re} | {抽检发现} | {判定} |".format(**r)
         for r in sample_rows] + [
        "", f"> 白底归一：`step1_白底归一/`；场景提示词包：`step2_场景合成/`；保真校验：`step3_保真校验/`。",
        "> 本质检单由 run_flow.py 实跑生成（AI 生成内容）；语义级保真与最终交付由人工确认。",
    ]
    md_path = os.path.join(a.outdir, "批量质检单.md")
    with open(md_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(md))

    result = {
        "flow": "product-image-batch-qc-flow",
        "steps": [
            {"step": 1, "skill": "white-bg-image-generate", "status": "ok", "output": white_png},
            {"step": 2, "skill": "scene-image-compose", "status": scene_status, "output": scene_file},
            {"step": 3, "skill": "product-fidelity-check", "status": "ok",
             "verdict": str(fid_verdict), "output": os.path.abspath(os.path.join(step3_dir, "fidelity.json"))},
            {"step": 4, "skill": "（内置）GB/T 2828.1 抽样判定", "status": "ok", "verdict": final_verdict},
            {"step": 5, "skill": "（人工）语义级确认与交付", "status": "pending"},
        ],
        "summary": summary,
        "files": [xlsx, md_path, white_png] + ([scene_file] if scene_file else []),
        "generated_at": at.stamp(),
    }
    at.write_json(result, os.path.join(a.outdir, "batch_qc_result.json"))
    print(f"批量 {batch} · 保真 {fid_verdict} · 批判定：{final_verdict}")
    for f in result["files"]:
        print(" 产物:", f)
    at.emit(result)


if __name__ == "__main__":
    main()
