# 测试报告

## 一、结构校验

| 项 | 结果 |
|---|---|
| 四件套齐全（SKILL.md / prompt.txt / schema.json / examples/input.json） | ✅ PASS |
| SKILL.md 九段齐全 + frontmatter + ID 行（`de_ecom_01_wf03`） | ✅ PASS |
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

**运行环境**：Python 3.13 / openpyxl（上游 precheck.py 依赖）

| 项 | 结果 |
|---|---|
| 退出码 | 0（两路均通过） |
| 上游调用 | `skills/platform-compliance-precheck/scripts/precheck.py` × 2（初检/复检，DAG 节点为本仓真实 slug） |
| 闭环结果 | 初检红线 12 / 警告 1 → 整改对照 13 项 → 复检（第 1 轮）红线 0 → **通过（修改后上架）** |
| 产物 1 | `out/合规整改流程报告.xlsx`（初检/整改对照/复检/汇总 4 sheet，红线行标红） |
| 产物 2 | `out/合规整改流程报告.md`（人读报告） |
| 产物 3 | `out/初检/合规预审清单.xlsx`、`out/复检/合规预审清单.xlsx`（上游真实产物） |
| 产物 4 | `out/compliance_flow_result.json`（机器可读，含步骤状态与轮次） |
| 耗时 | < 2 s |

### 失败处理演练

| 情况 | 演练方式 | 结果 |
|---|---|---|
| 受检文本为空 | 构造空 text 输入 | 中止（退出码 1），打印 `[失败处理] 受检文本为空` |
| 上游产物缺失/退出码≠0 | 代码路径：rc≠0 打印 stderr 后中止 | 覆盖 |
| 未提供 revised_text | 去掉字段重跑 | 正常退出，复检标「未执行」，交付整改清单 |
| 复检红线未归零 | 判定走「不建议上架」分支 | 覆盖（≤3 轮上限写进 prompt 与脚本） |

## 三、深度标准核对（D1–D5）

| 维度 | 证据 | 结果 |
|---|---|---|
| D1 领域术语 | 词表扫描/语境误报排除/复检闭环/牛皮癣/类目词表/留痕清单/OCR 采集 | ✅ |
| D2 量化约束 | 复检红线 =0、警告 ≤2 项、整改 ≤3 轮、覆盖率 100%、抖音文字 ≤20% | ✅ |
| D3 方法/算法 | 五步 DAG + 每步输入/处理/输出/失败处理表 + 复检循环规则 | ✅ |
| D4 领域专属失败模式 | OCR 漏检、语境误报、词表滞后于平台更新、用户拒绝删功效表述、规避式改写 | ✅ |
| D5 输出可交付 | Excel 三清单留痕 + md 报告 + json，输出模板含四张表 | ✅ |

## 四、边界与已知限制

| 限制 | 说明 |
|---|---|
| 整改文案来源 | 脚本只做复检验证；整改话术由模型按 prompt.txt 产出（脚本复用用户提供的 revised_text） |
| 词表时效 | precheck.py 词表覆盖高频违规词，新违规词靠人工确认兜底 |
| OCR 环节 | 脚本不内置 OCR；图上文字由人工抄录或上游 OCR 提供 |

## 五、结论

**通过。** 初检→整改→复检→人工确认全链路实跑闭环（红线 12 → 0），
上游 slug 真实存在且双路退出码 0，失败处理可演练，深度五维全过。

---

*测试报告基于真实实跑输出生成 · 2026-09-30*
