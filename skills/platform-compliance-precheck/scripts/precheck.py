# -*- coding: utf-8 -*-
"""
平台合规预审 —— 词表分级扫描器。

职责边界：本脚本只做**文本词表精确扫描与产物生成**（这是机器的强项）。
语境判断、误报排除、给出替换写法由模型按 prompt.txt 完成（这是模型的强项）。

用法：
  python precheck.py --input input.json --outdir out
  python precheck.py --demo                # 用内置样例跑一遍
  python precheck.py --text "全网最低价" --platform 淘宝 --category 化妆品

产物：
  out/合规预审清单.xlsx   违规清单 / 需补材料 / 汇总
  out/precheck.json       机器可读结果（供智能体读取）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(SKILL_DIR))
sys.path.insert(0, os.path.join(REPO, "lib"))

try:
    import assettools as at
except ImportError:  # pragma: no cover
    print("[错误] 未找到 lib/assettools.py。请确认技能位于 <repo>/skills/<slug>/scripts/ 下，"
          "且 <repo>/lib/assettools.py 存在。", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------- 词表
# 每条：(正则, 级别, 规则名, 依据, 建议改法)
# 级别：R=红线  W=警告  I=提示

ABSOLUTE = [
    (r"最好|最佳|最优|最强|最低价|最便宜|最先进|最流行|最受欢迎|最高档|最高级|最新技术|最顶级|最优质",
     "R", "绝对化用语·最高级", "《广告法》第九条", "改用具体描述，如「2026 年新款」「店铺热销」"),
    (r"第一|TOP\s*1|top\s*1|No\.?\s*1|冠军|之王|领导者|领导品牌|销量冠军|排名第\s*一",
     "R", "绝对化用语·排名", "《广告法》第九条", "删除排名表述，或改为「店铺热销单品」并注明数据来源与口径"),
    (r"唯一|独家|首创|首个|首款|绝无仅有|空前绝后|前所未有",
     "R", "绝对化用语·唯一性", "《广告法》第九条", "删除；若有专利可改为「已获专利 ZL…」（附专利号）"),
    (r"国家级|世界级|全球级|顶级|极品|极佳|绝佳|终极|极致|巅峰|至尊",
     "R", "绝对化用语·级别", "《广告法》第九条", "删除级别词，改用可验证的客观参数"),
    (r"100\s*%|百分百|彻底|根治|根除|永不|毫无|绝对安全|无任何副作用",
     "R", "绝对化用语·功效断言", "《广告法》第九条", "改为有条件表述，如「实测反馈良好（样本 30 人）」"),
]

CATEGORY_WORDS = {
    "化妆品": [
        (r"治疗|疗效|消炎|杀菌|抗敏|药妆|医学级|医美级|药用|处方|修复痘印|祛斑|美白针", "R", "化妆品·医疗宣称",
         "《化妆品监督管理条例》第 22 条", "删除医疗类表述，改为「护理」「舒缓」等非医疗用词"),
    ],
    "食品": [
        (r"降血压|降血糖|降血脂|抗癌|排毒|壮阳|治疗|防癌", "R", "食品·疾病治疗宣称",
         "《食品安全法》第 73 条", "删除功效宣称，仅描述口味、原料、工艺"),
    ],
    "保健品": [
        (r"治愈|替代药物|无副作用|疗效", "R", "保健品·疗效宣称",
         "不得宣称疾病预防治疗功能", "删除；如为注册保健食品可标「本品不能代替药物」"),
    ],
    "医疗器械": [
        (r"根治|痊愈|包治|无风险", "R", "医疗器械·疗效断言",
         "需附注册证号", "删除；改为「适用于…（详见注册证适用范围）」"),
    ],
    "母婴": [
        (r"最安全|绝对安全", "R", "母婴·安全断言", "《广告法》第九条", "改为「通过 XX 标准检测」并附报告"),
        (r"无添加|零添加", "I", "母婴·无添加宣称", "需检测报告支撑", "补充第三方检测报告编号"),
        (r"防过敏|抗过敏", "I", "母婴·防过敏宣称", "需检测报告支撑", "补充皮肤测试报告编号"),
    ],
    "教育": [
        (r"保过|包过|包就业|100\s*%?\s*提分|名师", "R", "教育·效果保证",
         "《广告法》第 24 条", "删除保证性表述；如为持证教师可标「教师资质：XX」"),
    ],
    "金融": [
        (r"保本|稳赚|零风险|保收益|日入过万|稳赚不赔", "R", "金融·收益保证",
         "《广告法》第 25 条", "删除收益承诺，加「投资有风险，入市需谨慎」"),
    ],
}

WARN_WORDS = [
    (r"最新|首选|推荐|爆款|网红|神器|秒杀|抢购", "W", "营销强化词",
     "平台可能判定为夸大宣传", "保留但加限定语，如「2026 年新品」"),
    (r"仅此一天|最后一天|限时抢购|清仓价", "W", "促销紧迫性",
     "虚假促销风险（若长期使用）", "确认活动真实且注明活动起止时间"),
]

PLATFORM_RULES = {
    "淘宝": [(r"二维码|微信号|加微信|VX|vx|扫码", "R", "淘宝·站外导流",
              "淘宝内容规范：禁站外导流", "删除导流信息，避免扣分"),
             (r"【牛皮癣】|文字边框|贴片文字", "W", "淘宝·主图牛皮癣",
              "主图除 Logo 外不得加文字边框", "主图移除文字与边框，文字移至详情页")],
    "天猫": [(r"二维码|微信号|加微信|微信", "R", "天猫·站外导流", "天猫内容规范", "删除导流信息")],
    "抖音": [(r"二维码|微信号|加微信", "R", "抖音·站外导流", "抖音电商规则", "删除导流信息"),
             (r"绝对|第一|最", "W", "抖音·极限词", "抖音内容规范", "按绝对化用语规则改写")],
    "小红书": [(r"二维码|微信号|加微信|私信领|点赞领", "R", "小红书·导流",
                "小红书社区规范：禁导流", "改为「评论区留言交流」，不发联系方式"),
               (r"绝对|100%|第一", "W", "小红书·极限词", "小红书社区规范", "改写为体验分享口吻")],
    "拼多多": [(r"二维码|微信号|加微信", "R", "拼多多·站外导流", "拼多多规则", "删除导流信息")],
}

DEMO = {
    "platform": "淘宝",
    "category": "化妆品",
    "text": ("【全网最低价】医美级精华液，100% 彻底淡化痘印，效果最好的抗敏修复神器！"
             "国家级实验室研发，独家配方，销量第一。加微信 xxx 领取试用装，扫码进群更优惠。"
             "本品适用于各类肌肤，无任何副作用。"),
}


# ---------------------------------------------------------------- 扫描

def scan(text: str, platform: str, category: str):
    rules = list(ABSOLUTE)
    rules += CATEGORY_WORDS.get(category, [])
    rules += WARN_WORDS
    rules += PLATFORM_RULES.get(platform, [])

    hits, seen = [], set()
    for pattern, level, rule, basis, fix in rules:
        for m in re.finditer(pattern, text):
            span = m.span()
            key = (span, rule)
            if key in seen:
                continue
            seen.add(key)
            hits.append({
                "级别": {"R": "🔴 红线", "W": "🟡 警告", "I": "🔵 提示"}[level],
                "_lvl": level,
                "原文片段": m.group(0),
                "位置": f"第 {span[0] + 1} 字符",
                "命中规则": rule,
                "依据": basis,
                "建议改法": fix,
            })
    order = {"R": 0, "W": 1, "I": 2}
    hits.sort(key=lambda h: (order[h["_lvl"]], h["位置"]))
    for h in hits:
        del h["_lvl"]
    return hits


def summarize(hits, n_chars, platform):
    n = {"R": 0, "W": 0, "I": 0}
    for h in hits:
        lv = h["级别"][0]
        n[{"🔴": "R", "🟡": "W", "🔵": "I"}[lv]] += 1
    if n["R"]:
        verdict = "不建议上架"
    elif n["W"]:
        verdict = "修改后上架"
    else:
        verdict = "通过"
    return {
        "受检平台": platform,
        "受检文本量": f"{n_chars} 字",
        "红线": n["R"],
        "警告": n["W"],
        "提示": n["I"],
        "整体判定": verdict,
    }


# ---------------------------------------------------------------- 主流程

def build(payload, outdir):
    text = payload.get("text", "")
    platform = payload.get("platform", "通用")
    category = payload.get("category", "")
    hits = scan(text, platform, category)
    summary = summarize(hits, len(text), platform)

    at.ensure_outdir(outdir)

    xlsx = at.write_excel(
        os.path.join(outdir, "合规预审清单.xlsx"),
        {
            "违规清单": hits or [{"级别": "（无）", "原文片段": "", "命中规则": "", "依据": "", "建议改法": ""}],
            "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()],
        },
        highlights={"违规清单": {"级别": "contains:红线"}},
        widths={"违规清单": {"原文片段": 26, "命中规则": 22, "依据": 28, "建议改法": 40}},
    )
    js = at.write_json({"summary": summary, "hits": hits,
                        "generated_at": at.stamp(),
                        "note": "词表机器扫描结果；语境判断与误报排除须由模型按 prompt.txt 复核"},
                       os.path.join(outdir, "precheck.json"))
    return {"files": [xlsx, js], "summary": summary, "hit_count": len(hits)}


def main():
    ap = argparse.ArgumentParser(description="平台合规预审 —— 词表分级扫描")
    ap.add_argument("--input", help="输入 JSON（platform/category/text）")
    ap.add_argument("--text", help="直接传文本")
    ap.add_argument("--platform", default="通用")
    ap.add_argument("--category", default="")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true", help="用内置样例跑一遍")
    a = ap.parse_args()

    if a.demo:
        payload = DEMO
    elif a.input:
        payload = at.read_json(a.input)
    elif a.text:
        payload = {"text": a.text, "platform": a.platform, "category": a.category}
    else:
        ap.error("需要 --input / --text / --demo 之一")

    r = build(payload, a.outdir)
    print(f"命中 {r['hit_count']} 项 —— 判定：{r['summary']['整体判定']}")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
