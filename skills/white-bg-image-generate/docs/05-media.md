# 截图与录屏

> 本资产为纯提示词客户端资产，无界面可截图。以下为**实跑运行效果**。

## 运行效果

### 输入

```json
{
  "product_info": "商品名称：示例商品；主要卖点：轻便、耐用",
  "requirement": "白底图，800x800，用于主图"
}

```

### 输出

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


---

*运行效果由实跑验证生成*
