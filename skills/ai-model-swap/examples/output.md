# 换装提示词包 · 法式碎花连衣裙（抖音商品卡 3:4）

> 本包由 `ai-model-swap` 按「路线 B：ControlNet OpenPose + IP-Adapter」生成。
> 在图像工具中执行后，按第六节质检清单逐项验收。**对外发布须标注「AI 生成」。**

## 一、推荐路线与理由

| 项 | 内容 |
|---|---|
| 推荐路线 | B：ControlNet OpenPose 骨架 + IP-Adapter 商品参考 |
| 理由 | 只有挂拍图、无真人素材，路线 A（局部重绘）不适用；刺绣 Logo「LUMI」已列入贴回方案，不依赖模型生成 |
| 分辨率 | 1024×1536（3:4），抖音商品卡直出；如需淘宝主图另裁 800×800 或 1000×1000 |

## 二、正向提示词

```text
full body photo of a young asian woman, natural standing pose, arms relaxed at sides,
wearing navy blue midi dress, hex #1F3A5F base color, small ditsy daisy floral print,
flower scale 8mm, evenly distributed, viscose rayon fabric, soft matte drape,
square neckline, puff sleeves, A-line silhouette, hem below knee,
afternoon street background, soft natural daylight, directional light from upper left,
light shadow on ground, realistic fabric folds following body movement,
professional e-commerce fashion photography, sharp focus on garment,
texture of dress identical to reference image
```

## 三、负向提示词

```text
deformed hands, extra fingers, fused fingers, distorted logo, misspelled text,
changed pattern, rescaled floral print, color shift, navy turning purple,
blurry fabric texture, watermark, plastic skin, doll-like face,
asymmetric hem, floating collar, mismatched buttons, wrong sleeve length,
fabric merging with background, harsh flash lighting, cropped feet
```

## 四、参数规格

| 参数 | 值 | 说明 |
|---|---|---|
| 采样器 | DPM++ 2M Karras | 步数 30（28–35 区间内，低于 25 步布纹会有水波纹伪影） |
| CFG Scale | 7 | 高于 9 会出塑料感高光，破坏哑光垂坠质感 |
| ControlNet OpenPose | 权重 1.0 | 骨架图须手部关键点齐全，缺失就换骨架 |
| IP-Adapter（挂拍图） | 权重 0.8 | 0.7–0.85 区间；低于 0.7 版型漂移，高于 0.9 会带进平铺扁平感 |
| 种子 | 首次随机，出图后记录 | 复盘时同种子改词，归因到提示词而非随机性 |

## 五、商品本体锁定清单

| 属性 | 锁定词 | 风险提示 |
|---|---|---|
| 颜色 | navy blue, hex #1F3A5F | 不写"深蓝色"；负向词加 `navy turning purple` 防漂移 |
| 图案 | ditsy daisy floral print, flower scale 8mm | 不写比例模型一定把雏菊重排成大花 |
| 材质 | viscose rayon, soft matte drape | 只写 cotton 会出现挺括感，与垂坠面料不符 |
| 版型 | square neckline, puff sleeve, A-line midi | 版型结构词一个不许省，缺一个漂一个 |
| Logo | 不进正向提示词 | 刺绣字母由原图贴回（左下摆区域 2–4px 羽化合成），模型拼字母必然拼错 |

## 六、出图后质检清单

| # | 检查项 | 合格线 | 不合格处置 |
|---|---|---|---|
| 1 | 颜色一致性 | ΔE00 < 3.0（跑 product-fidelity-check 脚本实测） | 降 IP-Adapter 至 0.75 重出 |
| 2 | 碎花图案 | 花径约 8mm、分布均匀、无重排 | 补 `evenly distributed, scale 8mm` 重出 |
| 3 | Logo「LUMI」 | 字形笔画与原图一致（人工逐字母核对） | 改走路线 C 贴回 |
| 4 | 版型结构 | 方领/泡泡袖/A 字中长与描述一致 | 补结构词重出 |
| 5 | 模特手部 | 五指齐全无融合 | 换骨架图或对手部 inpaint（幅度 0.45–0.60） |
| 6 | 面料质感 | 哑光垂坠、褶皱随动作自然 | 负向词加 `plastic skin, stiff fabric` 重出 |

## 七、合规注意

1. 本图为 **AI 生成内容**：抖音发布时开启"内容由 AI 生成"声明；按《互联网信息服务深度合成管理规定》不得移除标识。
2. 仅用于商品主图/详情展示，**不得作为买家秀**或暗示真人试穿实拍。
3. 上架前过双卡点：`product-fidelity-check`（保真）→ `platform-compliance-precheck`（文案合规）。
4. 主图需 800×800 及以上时从 3:4 原图裁切；不得反向把 1:1 拉伸成 3:4。

---
*本提示词包由 AI 生成（ai-model-swap · de_ecom_01_sk06）；实际出图效果取决于所用图像工具，交付前须人工按第六节验收。*
