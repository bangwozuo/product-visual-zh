# 白底图生成

## 元信息

| 字段 | 值 |
|------|-----|
| ID | `de_ecom_01_sk01` |
| 类型 | **`atomic`（原子技能）** |
| 所属员工 | 商品视觉师 |
| 能力族 | — |
| 复杂度 | `S` |
| 阶段 | `P0` |
| 复用度 | ★★★☆☆ |
| 资产形态 | 纯提示词（无运行时依赖） |

## 能力描述

抠图+标准白底

## 输入规格

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `brief` | string | ✅ | 任务简述（产品 / 主题 / 目标） |

## 输出规格

标题、正文、亮点清单

- `title`：标题（含备选）
- `body`：正文
- `highlights`：亮点清单

## 使用步骤

### 方式一：直接使用（最快）

1. 打开任意支持自定义提示词的 AI 工具
2. 复制 `prompt.txt` 的**全部内容**作为系统提示词
3. 按上方「输入规格」提供数据
4. 得到符合「输出规格」的结果

### 方式二：在主流平台导入

| 平台 | 导入方式 |
|------|---------|
| **Coze / 扣子** | 新建 Bot → 人设与回复逻辑 → 粘贴 `prompt.txt` |
| **WorkBuddy** | 新建 Skill → 填入 `prompt.txt` 内容 |
| **Dify** | 新建应用 → 提示词编排 → 粘贴 `prompt.txt` |
| **Claude** | 新建 Project → Instructions → 粘贴 `prompt.txt` |
| **ChatGPT** | 新建 GPT → Instructions → 粘贴 `prompt.txt` |

## 边界（不做的事）

- ❌ 编造数据、案例或效果承诺
- ❌ 使用违反《广告法》的极限词
- ❌ 生成诱导好评、刷量、删差评等违规内容
- ❌ 执行或建议任何绕过平台规则的操作
- ❌ 涉及资金操作或代替用户做最终决策
- ❌ 处理超出本职能力范围的请求（应明确说明并建议转其他技能）

## 调用示例

**输入**：

```json
{
  "product_info": "商品名称：示例商品；主要卖点：轻便、耐用",
  "requirement": "白底图，800x800，用于主图"
}

```

**输出**：

```markdown
## 生成提示词

正向提示词：
Product cutout on pure white background, clean professional e-commerce photography, lightweight and durable item, sharp focus, soft even studio lighting, no shadows, centered composition, high detail, 8k resolution, commercial catalog style, pure white seamless backdrop, optimized for 800x800 main image

## 负面提示词

background noise, gray background, gradient background, shadow, watermark, text, logo, frame, border, human hands, outdoor elements, clutter, blur, distortion, low resolution, cartoon, illustration, reflection

## 质检标准

1. 背景为绝对纯白（RGB 255,255,255），无杂点、无渐变
2. 产品边缘抠图干净，无锯齿、无白边/黑边残留
3. 主体清晰锐利，焦点准确
4. 无投影或阴影（纯白底要求）
5. 尺寸严格 800x800，主体占比 70%-80%
6. 无文字、水印、Logo、边框等干扰

## 执行说明

本资产只产出指令，实际出图需用户在图像工具中执行。输出内容已标注「AI 生成内容」。


```


## 所属工作流

- 商品图批量生成与质检

## 合规声明

- 本技能输出为 **AI 辅助生成内容**，交付前必须经人工审核
- 请按所在平台要求完成 AI 生成内容标识
- 涉及专业领域（法律 / 税务 / 医疗）的内容仅作参考，不构成专业意见

---

*本技能遵循 [bangwozuo 数字员工资产规范](https://github.com/bangwozuo/digital-employee-spec) v3.0*
