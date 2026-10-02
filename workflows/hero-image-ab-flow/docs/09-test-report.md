# 测试报告

## 一、结构校验

| 项 | 结果 |
|---|---|
| 四件套齐全（SKILL.md / prompt.txt / schema.json / examples/input.json） | ✅ PASS |
| SKILL.md 九段齐全 + frontmatter + ID 行（`de_ecom_01_wf02`） | ✅ PASS |
| JSON Schema 合法，输入输出字段与 SKILL.md 一致 | ✅ PASS |
| prompt.txt 必需区块（角色/DAG/步骤明细/输出格式/禁止事项/合规） | ✅ PASS |
| 无占位符残留 | ✅ PASS |
| 无 API Key / 无模型调用代码 | ✅ PASS |

## 二、脚本实跑（`scripts/run_flow.py`）

**命令**：

```bash
python3 scripts/run_flow.py --input examples/input.json --outdir out
python3 scripts/run_flow.py --demo --outdir out_demo
```

**运行环境**：Python 3.13 / Pillow 12.3.0 / openpyxl

| 项 | 结果 |
|---|---|
| 退出码 | 0（两路均通过） |
| 上游调用 1 | `skills/copy-layout/scripts/grid_preview.py` × 2（两版落位图，DAG 真实 slug） |
| 上游调用 2 | `skills/platform-compliance-precheck/scripts/precheck.py` × 2（两版文案扫描，DAG 真实 slug） |
| 版式结论 | 两版「通过」，文字面积 8.8% |
| 合规结论 | 两版 0 红线 0 警告 |
| CTR 判定 | A 3.00% / B 4.23%（电商 2–5% 基准区间） |
| z 检验 | z=2.61、p=0.0091、相对提升 +41.0% → **差异显著，B 胜出**（与 prompt 方法论示例一致） |
| 产物 1 | `out/主图AB测试报告.xlsx`（版本判定/版式留痕/合规留痕/统计判定/汇总） |
| 产物 2 | `out/主图AB测试报告.md` |
| 产物 3 | `out/step2_版式栅格/版本1、版本2/版式栅格示意图.png` |
| 产物 4 | `out/step3_文案合规/版本1、版本2/precheck.json` |
| 产物 5 | `out/ab_flow_result.json` |
| 耗时 | < 3 s |

### 失败处理演练

| 情况 | 演练方式 | 结果 |
|---|---|---|
| 版本数 <2 | 空版本输入 | 中止（退出码 1），提示「至少 2 个版本」 |
| 上游退出码≠0 / 产物缺失 | 代码路径：打印 stderr 中止 | 覆盖 |
| 样本不足 | 曝光 <1000 或天数 <3 | 判定行标「样本不足，不下结论」，不做胜负宣告 |
| 版本缺数据 | 缺 days/impressions/clicks | 标「数据缺失」，正常退出 |
| 文案红线 >0 | precheck 命中即标「❌ 打回改文案」 | 覆盖（合规留痕红显） |
| 显著但提升 <10% | z ≥1.96 且 lift <0.10 | 结论附加换图风险提示 |

## 三、深度标准核对（D1–D5）

| 维度 | 证据 | 结果 |
|---|---|---|
| D1 领域术语 | CTR/两比例 z 检验/单变量原则/基准区间/图文不符/掉权重/样本门槛 | ✅ |
| D2 量化约束 | ≥1000 曝光、≥3 天、CTR 1%/2%/5% 分档、\|z\|≥1.96、p<0.05、提升 <10% 提示 | ✅ |
| D3 方法/算法 | 五步 DAG + CTR 分档判定表 + z 检验公式与结论规则树 | ✅ |
| D4 领域专属失败模式 | 小样本噪声、时段流量结构失真、伪 A/B 无法归因、高 CTR 高退款、老链接换图掉权重 | ✅ |
| D5 输出可交付 | Excel 四 sheet 留痕 + md 报告 + 每版落位图与合规 json | ✅ |

## 四、边界与已知限制

| 限制 | 说明 |
|---|---|
| 数据来源 | 脚本不抓平台后台，impressions/clicks 由人工从生意参谋/抖店罗盘回填 |
| z 检验前提 | 大样本正态近似；本工具面向曝光 ≥1000 的场景，不适用于极小样本精确检验 |
| 归因边界 | CTR 差异≠转化差异；详情页承接问题需另行排查 |

## 五、结论

**通过。** 设计→落位→合规→测试→统计判定全链路实跑（z=2.61 显著路径），
样本不足与红线打回路径可演练，两个上游均为本仓真实 slug 且退出码 0。

---

*测试报告基于真实实跑输出生成 · 2026-09-30*
