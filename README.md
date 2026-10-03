# 商品视觉师

> **一人店的"到岗美工"，只出能直接上架的合规商品图**

![演示](docs/demo.mp4)

*上方演示串接了本仓 5 个代表资产的真实执行截图：白底图生成 → 产品保真校验 → 文案排版 → 主图 A/B 版本生成 → 商品图批量生成与质检（每张均为脚本实跑产物，单资产完整截图见各资产 README）。*

[![Stage](https://img.shields.io/badge/stage-P0-orange)](https://github.com/bangwozuo)
[![Asset](https://img.shields.io/badge/asset-prompt--only-blueviolet)](#资产形态)
[![NoKey](https://img.shields.io/badge/API%20Key-not%20required-success)](#资产形态)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

---

## 数字员工总览

| 项 | 内容 |
|------|------|
| 身份 | **商品视觉师**——一人店的"到岗美工"，只出能直接上架的合规商品图 |
| 边界 | 做：商品图生成、质检、合规预审、多平台适配；不做：品牌 VI、仿冒与虚假功效图 |
| 硬卡点 | 每张 AI 生成图上架前过 `product-fidelity-check`（保真）+ `platform-compliance-precheck`（合规）双卡点 |
| KPI | 一次过审率 ≥90%；单张交付 ≤5 分钟；返工率 ≤10% |
| 目标用户 | 月上新 5-50 款的四平台一人店/夫妻店（电商小卖家） |

---

## 资产矩阵（11 个资产）

| 资产 | 一句话 | 类型 | README |
|------|--------|------|--------|
| 白底图生成 | 带背景图 → 平台过审的纯白底主图 + 五项量化的质检 | 技能 | [README](skills/white-bg-image-generate/README.md) |
| 场景图合成 | 白底图融进真实场景——光影/透视双一致的合成提示词包 | 技能 | [README](skills/scene-image-compose/README.md) |
| 产品保真校验 | 实物图 vs 生成图六维量化比对，出返工指令单 | 技能 | [README](skills/product-fidelity-check/README.md) |
| 平台合规预审 | 极限词/牛皮癣检测，24 条词表扫描出 Excel 预审清单 | 技能 | [README](skills/platform-compliance-precheck/README.md) |
| 文案排版 | 卖点上图：8px 栅格 + 三级字号 + 对比度实测 | 技能 | [README](skills/copy-layout/README.md) |
| AI 模特换装 | 平铺图 → 可投喂图像模型的换装提示词包（换装不换商品） | 技能 | [README](skills/ai-model-swap/README.md) |
| 商品图批量生成与质检 | 生成→场景化→保真→GB/T 2828.1 抽样判定全链路 | 工作流 | [README](workflows/product-image-batch-qc-flow/README.md) |
| 主图 A/B 版本生成 | 两版主图落位 + 合规 + z 检验出统计结论 | 工作流 | [README](workflows/hero-image-ab-flow/README.md) |
| 平台合规预审流程 | 采集→扫描→整改→复检闭环，红线归零才放行 | 工作流 | [README](workflows/platform-compliance-flow/README.md) |
| 多平台规格一键适配 | 一套主素材 → 四平台可直接上传的规格包 | 工作流 | [README](workflows/multi-platform-spec-flow/README.md) |
| 详情页排版生成 | 卖点 → 五屏说服路径 + 落位 + 合规 + 长图校验 | 工作流 | [README](workflows/detail-page-layout-flow/README.md) |

---

## 它是谁

面向 **电商小卖家** 的数字员工资产包。

| 项目 | 内容 |
|------|------|
| 目标用户 | 月上新 5-50 款的四平台一人店/夫妻店 |
| 交付物 | 一次过审率 ≥90%；单张交付 ≤5 分钟；返工率 ≤10% |
| 技能数 | 6 |
| 工作流数 | 5 |
| 旧名存档 | `视觉设计师·小图` |

---

## 资产形态

**提示词资产 + 离线质检脚本** —— 这是理解本仓库的关键：

| 特性 | 说明 |
|------|------|
| ✅ 无需 API Key | 一个 Key 都不需要 |
| ✅ 无需部署 | 没有服务端；质检脚本（保真/白底/排版/工作流）可离线复跑 |
| ✅ 平台无关 | 提示词粘贴到任何 AI 工具即可使用 |
| ✅ 真实可验证 | 量化指标全部来自脚本实测，README 截图为真实执行产物 |
| ✅ 用户自备算力 | 模型来自你自己的订阅 |

---

## 快速开始

```text
1. 打开 skills/white-bg-image-generate/prompt.txt
2. 全文复制
3. 粘贴到你常用的 AI 工具（Coze / WorkBuddy / Dify / Claude / ChatGPT）
4. 按 SKILL.md 的输入规格提供数据
```

就这四步。完整指引见 [使用手册](docs/04-usage.md)。

---

## 仓库结构

```text
product-visual-zh/
├── README.md / employee.md / package.yaml     # 入口与 12 字段定义卡
├── docs/01~07                                 # 员工级文档（架构/流程/场景/手册/示例/录像/测试）
├── skills/                                    # 6 个原子技能
│   └── <skill>/
│       ├── README.md  SKILL.md  prompt.txt  schema.json  examples/
│       └── docs/                              # 该技能自己的 10 项文档 + 配图
├── workflows/                                 # 5 条工作流（复合技能）
│   └── <workflow>/
│       ├── README.md  SKILL.md  prompt.txt  schema.json  examples/
│       └── docs/                              # 该工作流自己的 10 项文档 + 配图
├── knowledge/                                 # RAG wiki 知识库
│   ├── README.md  RAG-接入指南.md  template.md
│   └── wiki/(index.md, _template.md, entries/)
├── connectors/                                # 连接器说明 + 合规红线
├── quality/                                   # 效果基线与追踪日志
└── tests/                                     # 资产校验测试（离线，无需密钥）
```

### 每个技能 / 工作流自带的 docs

| 文档 | 内容 |
|------|------|
| `README.md` | 资产速览与快速开始 |
| `docs/01-usage-manual.md` | 安装使用手册 |
| `docs/02-architecture.md` | 业务架构图 |
| `docs/03-flow.md` | 流程图（Mermaid + 配图） |
| `docs/04-examples.md` | 使用示例 |
| `docs/05-media.md` | 截图和录屏（清单 + 分镜脚本） |
| `docs/06-scenarios.md` | 使用场景（适用 / 不适用） |
| `docs/07-audience.md` | 用户群体 |
| `docs/08-value.md` | 解决问题与价值 |
| `docs/09-test-report.md` | 测试报告 |
| `docs/assets/overview.svg` | 自动生成的流程示意图 |

---

## 交付物导航

| 文档 | 内容 |
|------|------|
| [业务架构](docs/01-architecture.md) | 四层架构 + 数据流 + 能力边界 |
| [工作流流程](docs/02-workflow.md) | 5 条工作流的 DAG 可视化 |
| [使用场景](docs/03-scenarios.md) | 3 个真实场景（含前后对比） |
| [使用手册](docs/04-usage.md) | 各平台导入指引 + 常见问题 |
| [示例库](docs/05-examples.md) | 6 组输入输出示例 |
| [录像脚本](docs/06-recording-script.md) | 7 镜头分镜 + 旁白稿 |
| [校验报告](docs/07-test-report.md) | 资产质量校验结果 |

---

## 技能清单（6 个）

| # | 技能 | 能力族 | 复杂度 | 提示词 | 文档 |
|---|------|--------|--------|--------|------|
| 1 | 白底图生成 | 文案生成 | `S` | [prompt.txt](skills/white-bg-image-generate/prompt.txt) | [docs](skills/white-bg-image-generate/docs/) |
| 2 | 场景图合成 | 文案生成 | `M` | [prompt.txt](skills/scene-image-compose/prompt.txt) | [docs](skills/scene-image-compose/docs/) |
| 3 | 产品保真校验 | 文案生成 | `M` | [prompt.txt](skills/product-fidelity-check/prompt.txt) | [docs](skills/product-fidelity-check/docs/) |
| 4 | 平台合规预审 | 合规校验 | `S` | [prompt.txt](skills/platform-compliance-precheck/prompt.txt) | [docs](skills/platform-compliance-precheck/docs/) |
| 5 | 文案排版 | 上架优化 | `S` | [prompt.txt](skills/copy-layout/prompt.txt) | [docs](skills/copy-layout/docs/) |
| 6 | AI 模特换装 | 文案生成 | `L` | [prompt.txt](skills/ai-model-swap/prompt.txt) | [docs](skills/ai-model-swap/docs/) |

## 工作流清单（5 条）

| # | 工作流 | 阶段 | 复杂度 | 触发 | 定义 | 文档 |
|---|--------|------|--------|------|------|------|
| 1 | 商品图批量生成与质检 | `P0` | `M` | 人工 | [SKILL.md](workflows/product-image-batch-qc-flow/SKILL.md) | [docs](workflows/product-image-batch-qc-flow/docs/) |
| 2 | 主图 A/B 版本生成 | `P0` | `S` | 人工 | [SKILL.md](workflows/hero-image-ab-flow/SKILL.md) | [docs](workflows/hero-image-ab-flow/docs/) |
| 3 | 平台合规预审 | `P0` | `S` | 事件（出图完成） | [SKILL.md](workflows/platform-compliance-flow/SKILL.md) | [docs](workflows/platform-compliance-flow/docs/) |
| 4 | 多平台规格一键适配 | `P1` | `M` | 事件（新品上架） | [SKILL.md](workflows/multi-platform-spec-flow/SKILL.md) | [docs](workflows/multi-platform-spec-flow/docs/) |
| 5 | 详情页排版生成 | `P1` | `M` | 人工 | [SKILL.md](workflows/detail-page-layout-flow/SKILL.md) | [docs](workflows/detail-page-layout-flow/docs/) |

---

## 知识库与连接器

| 目录 | 说明 |
|------|------|
| [`knowledge/`](knowledge/README.md) | RAG wiki 知识库：填入业务信息可显著提升输出质量 |
| [`connectors/`](connectors/README.md) | 连接器说明：数据从哪来、怎么合规地来 |

---

## 资产校验

```bash
pip install -r requirements.txt
pytest tests/ -v
```

校验技能完整性、提示词结构、契约一致性、工作流 DAG、技能级与工作流级 docs 完整性、知识库 wiki 与连接器结构。
**不需要任何 API Key。**

---

## 合规声明

- ✅ 所有输出为 **AI 辅助生成**，交付前须人工审核
- ✅ 提示词内置**违禁词禁止清单**，符合《广告法》要求
- ✅ 遵循《人工智能生成合成内容标识办法》
- ✅ 连接器只走**官方 API** 或**用户导出数据**
- ✅ 所有对外发布动作**保留人工确认环节**

---

## 许可

[Apache-2.0](LICENSE) — 可自由使用、修改、商用

---

*由 bangwozuo 业务库自动生成 · 2026-09-29*
