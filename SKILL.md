---
name: evolink-video-image-stack
description: 将一个或多个 16:9 横版视频与图片按“今日爆款”8:9 上下拼接版式合成为视频，并添加紧贴的 EvoLink.ai 与模型名双标签；支持单组或按文件夹批量处理
---

# EvoLink 爆款样式：视频 + 图片上下拼接

这是一个版式级模板。它只复用今日爆款中的画面结构、尺寸、标签和输出规则，不固化具体人物、餐厅、剧情、Prompt 或模型生成内容。

用于用户提供一个 16:9 横版视频和一个 16:9 横版图片，并希望生成同款上下拼接视频的本地合成任务。默认视频在上方、图片在下方；用户明确指定顺序时，按用户指定顺序执行。也支持把多个“每个文件夹含一段视频和一张图片”的输入批量处理，并按输入文件夹名称分别归档输出。

已确认的样式预览见 [assets/preview.png](assets/preview.png)。

## 输入与自动判断

- 接受一段可解码的横版视频和一张可解码的横版图片；两者都应接近 16:9。
- 默认将视频作为上方动态结果，将图片作为下方静态参考图。
- 模型标签优先使用用户明确提供的模型名；没有明确提供时，可从文件名和上下文推断。只有在推断结果不明确时才询问模型标签。
- 不把当前案例的角色、场景、故事或 Prompt 写死到输出中；这些内容随输入素材变化。

执行入口：

```bash
python3 "<skill-root>/scripts/compose.py" \
  --top-video "/path/to/video.mp4" \
  --bottom-image "/path/to/image.png" \
  --model-label "Seedance2.5" \
  --output-dir "/path/to/output" \
  --audio top
```

批量处理入口：

```bash
python3 "<skill-root>/scripts/batch_compose.py" \
  --input-root "/path/to/input" \
  --output-root "/path/to/output" \
  --model-label "Seedance2.5" \
  --audio top
```

批量模式只扫描 `--input-root` 的直接子文件夹。每个子文件夹必须恰好包含一个可识别的视频文件和一个可识别的图片文件；输出会写入 `--output-root/<输入文件夹名>/`，并在输出根目录生成 `batch-report.json`。输入和已有输出检查在渲染前完成，避免因某个文件夹素材数量不符合要求或输出冲突而静默漏处理。需要更新已有结果时传入 `--overwrite`。

## 固定样式与输出规则

- 输出固定为 1280×1440、30 fps、H.264 MP4，视频和图片各占 1280×720，连续上下排列，没有外框和间隔
- 视频和图片按比例填充 16:9 显示区域并从中心裁切，允许图片轻微偏离 16:9；不拉伸画面
- 视频从第 0 秒原速播放，图片静止覆盖完整视频时长；输出时长按视频时长向上取整到 30 fps 整帧
- `--audio top` 保留上方视频原声，默认使用该模式；`--audio none` 输出静音
- 视频右上角固定为 x=1046、y=10 px，右边距 18 px；标签宽 216 px
- 上方蓝色标签高 40 px，颜色 `#0758AA`，圆角 9 px，使用 `assets/evolink.png` 白色 logo 和 `EvoLink.ai`
- 下方黄色标签高 40 px，颜色 `#FFEF40`，圆角 9 px，只显示 `--model-label`，黑色粗斜体并自动缩小字号
- 两条标签尺寸均为 216×40 px，垂直间距固定为 0 px，直接相接；除用户明确要求外不添加其他水印、费用或宣传语
- 输入素材、品牌资产和模型标签保持用户提供的事实，不生成或猜测品牌，不修改原始文件

脚本会检查 ffmpeg、ffprobe、Pillow、输入比例、完整解码、尺寸、帧数、时长和音轨，并在输出目录生成：

- `comparison.mp4`
- `poster.png`
- `comparison-start.png`、`comparison-middle.png`、`comparison-end.png`
- `preview.html`
- `render-report.json`，记录输入文件名、SHA-256、输出参数和水印位置

已有 `comparison.mp4` 时默认拒绝覆盖，用户明确要求更新时传入 `--overwrite`

生成后查看至少一张真实预览，确认上下顺序、右上标签没有截断且两条标签紧贴，再交付 `comparison.mp4` 的绝对路径
