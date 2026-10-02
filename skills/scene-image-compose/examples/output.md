# 场景合成提示词包 · 不锈钢摩卡壶（厨房晨光 · 抖音 900×1200）

> 由 `scene-image-compose` 生成。合成策略：**图层贴回**（白底商品图 + AI 背景光照融合）——
> 金属壶身高光是仿冒重灾区，商品本体像素不用 AI 生成最稳。
> **对外发布须标注「AI 生成」。**

## 一、策略与参数总览

| 项 | 内容 |
|---|---|
| 合成策略 | 图层贴回：AI 只生成背景与光照融合层，摩卡壶本体从白底图抠出后贴回 |
| 画布 | 900×1200（3:4，抖音商品卡直出） |
| 光影参数 | 方向 upper-left / 色温 3800K（晨光偏暖）/ 光比 2:1 / 接地阴影朝右下 |
| 透视参数 | 机位 45° 俯拍（与台面场景同视角）/ 镜头 50mm / 景深 f/2.8 背景轻虚化 |

## 二、正向提示词

```text
bright kitchen countertop scene at morning, warm daylight from upper left,
color temperature 3800K, light wooden countertop near a window,
scattered coffee beans and a beige linen cloth as props, gentle steam in the air,
soft contact shadows cast toward lower right, gentle fill shadow,
45-degree top-down camera angle, 50mm lens, f/2.8 shallow depth of field,
background slightly blurred, sharp focus on the product area,
product placed at right-side rule-of-thirds point, negative space on the left,
brushed stainless steel moka pot, hex #8C9296, octagonal body, black bakelite handle,
300ml single-cup size, subtle reflections of warm kitchen environment,
photorealistic, e-commerce lifestyle photography
```

## 三、负向提示词

```text
harsh black shadow, double shadows, mismatched light direction, cold studio lighting,
floating product, no contact shadow, wrong perspective, wide-angle distortion,
cluttered props, gibberish text, readable brand logos, strangers hands,
changed product color, warped octagonal body, plastic-looking metal,
overexposed highlights, color banding, watermark
```

## 四、商品锁定清单

| 属性 | 锁定策略 | 验收方式 |
|---|---|---|
| 壶身颜色/材质 | 白底图贴回，本体像素 100% 原图 | 贴回区不做 AI 重绘 |
| 金属高光 | 不重画高光；AI 背景融合层只压暗/提亮边缘 5%–8% 模拟环境光 | 人眼查高光方向是否来自 upper-left |
| 八角壶身结构 | 贴回时按 45° 俯拍机位做透视变换，比例不拉伸 | 对角线长度比对白底图 ±3% |
| 壶身无 Logo | 负向词 `readable brand logos` 防幻觉印刷字 | 人眼逐面检查 |
| 把手电木 | 属本体像素，随贴回保留 | 无 |

## 五、出图后验收清单

1. **光影一致**：壶身高光来自左上、接地阴影朝右下、整体色温偏暖——任一不符即重出
2. **颜色量化**：贴回前后 ΔE00 < 3.0、结构差异块 ≤2%——`product-fidelity-check` 脚本实测
3. **透视一致**：壶身透视与台面木纹消失方向一致（视角差 ≤15°）
4. **画面卫生**：无幻觉杂物、无可读异体文字、咖啡豆/亚麻布 ≤3 件道具

## 六、合规注意

1. 本图为 **AI 生成内容**：抖音发布开启"内容由 AI 生成"声明，不得暗示实拍
2. 场景无人物、无第三方品牌道具；壶身 300ml 容量不得因场景透视被视觉夸大误导
3. 上架前过 `product-fidelity-check` 硬卡点；图上若加利益点文字先过 `platform-compliance-precheck`

---
*本提示词包由 AI 生成（scene-image-compose · de_ecom_01_sk02）；实际出图由用户在图像工具执行，交付前须按第五节验收。*
