#!/usr/bin/env python3
"""Stack a landscape video above a landscape image with tight EvoLink labels."""

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT, PANEL_W, PANEL_H, FPS = 1280, 1440, 1280, 720, 30
LABEL_W, BLUE_H, YELLOW_H, LABEL_GAP = 216, 40, 40, 0
LABEL_X, LABEL_Y = WIDTH - 18 - LABEL_W, 10
SKILL_ROOT = Path(__file__).resolve().parents[1]
LOGO = SKILL_ROOT / "assets" / "evolink.png"


def run(args):
    return subprocess.run(args, check=True, text=True, capture_output=True)


def probe(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]).stdout)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_ratio(value):
    if not value or value in ("N/A", "0:1"):
        return 1.0
    a, b = (int(part) for part in value.split(":", 1))
    return a / b if b else 1.0


def media_info(path, *, is_image=False):
    metadata = probe(path)
    stream = next((item for item in metadata["streams"] if item.get("codec_type") == "video"), None)
    if stream is None:
        raise ValueError(f"No decodable image/video stream: {path}")
    width, height = int(stream["width"]), int(stream["height"])
    ratio = width * parse_ratio(stream.get("sample_aspect_ratio")) / height
    tolerance = 0.03 if is_image else 0.05
    if abs(ratio - 16 / 9) > tolerance:
        kind = "image" if is_image else "video"
        raise ValueError(f"Expected a landscape 16:9 {kind}, got {width}x{height}: {path}")
    if is_image:
        return {"width": width, "height": height, "ratio": ratio}
    duration = float(stream.get("duration") or metadata["format"].get("duration") or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"Invalid video duration: {path}")
    return {
        "width": width,
        "height": height,
        "ratio": ratio,
        "duration": duration,
        "has_audio": any(item.get("codec_type") == "audio" for item in metadata["streams"]),
    }


def font(size, italic=False):
    names = ["Arial Bold Italic.ttf", "Arial Italic.ttf"] if italic else ["Arial Bold.ttf", "Arial Black.ttf"]
    paths = [Path("/System/Library/Fonts/Supplemental") / name for name in names]
    paths += [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf" if italic else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("C:/Windows/Fonts/arialbi.ttf" if italic else "C:/Windows/Fonts/arialbd.ttf"),
    ]
    for path in paths:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    raise ValueError("No supported bold font found")


def fit_model_font(text, max_width, size=24):
    while size > 12:
        selected = font(size, italic=True)
        box = selected.getbbox(text)
        if box[2] - box[0] <= max_width:
            return selected
        size -= 1
    return font(12, italic=True)


def make_label(model_name, destination):
    canvas = Image.new("RGBA", (LABEL_W, BLUE_H + LABEL_GAP + YELLOW_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((0, 0, LABEL_W - 1, BLUE_H - 1), radius=9, fill=(7, 88, 170, 255))
    yellow_y = BLUE_H + LABEL_GAP
    draw.rounded_rectangle((0, yellow_y, LABEL_W - 1, yellow_y + YELLOW_H - 1), radius=9, fill=(255, 239, 64, 255))

    logo = Image.open(LOGO).convert("RGBA")
    alpha_box = logo.getchannel("A").getbbox()
    if not alpha_box:
        raise ValueError("EvoLink logo has no visible content")
    logo = logo.crop(alpha_box).resize((31, 31), Image.Resampling.LANCZOS)
    brand = "EvoLink.ai"
    brand_font = font(29)
    brand_box = draw.textbbox((0, 0), brand, font=brand_font)
    group_width = 31 + 6 + brand_box[2] - brand_box[0]
    group_x = (LABEL_W - group_width) // 2
    canvas.alpha_composite(logo, (group_x, 4))
    draw.text((group_x + 37, BLUE_H // 2), brand, font=brand_font, fill="white", anchor="lm")

    draw.text((LABEL_W // 2, yellow_y + YELLOW_H // 2), model_name, font=fit_model_font(model_name, LABEL_W - 20), fill="black", anchor="mm")
    canvas.save(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-video", required=True, type=Path)
    parser.add_argument("--bottom-image", required=True, type=Path)
    parser.add_argument("--model-label", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--audio", choices=("top", "none"), default="top")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    for binary in ("ffmpeg", "ffprobe"):
        if not shutil.which(binary):
            parser.error(f"{binary} is required")
    if not args.model_label.strip():
        parser.error("--model-label must be nonempty")

    top = args.top_video.expanduser().resolve()
    bottom = args.bottom_image.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output = output_dir / "comparison.mp4"
    if not top.is_file():
        parser.error(f"Top video does not exist: {top}")
    if not bottom.is_file():
        parser.error(f"Bottom image does not exist: {bottom}")
    if output.exists() and not args.overwrite:
        parser.error(f"Output already exists: {output}; pass --overwrite to update it")
    try:
        output.relative_to(SKILL_ROOT)
    except ValueError:
        pass
    else:
        parser.error("Output directory must be outside the skill directory")

    top_info = media_info(top)
    bottom_info = media_info(bottom, is_image=True)
    if args.audio == "top" and not top_info["has_audio"]:
        parser.error("Top video has no audio stream; use --audio none")
    frames = math.ceil(top_info["duration"] * FPS - 1e-7)
    duration = frames / FPS
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="evolink-video-image-stack-") as temporary:
        temporary = Path(temporary)
        label_path = temporary / "label.png"
        make_label(args.model_label.strip(), label_path)
        rendered = temporary / "comparison.mp4"
        filters = (
            f"[0:v]setpts=PTS-STARTPTS,fps={FPS},scale={PANEL_W}:{PANEL_H}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={PANEL_W}:{PANEL_H},setsar=1,tpad=stop_mode=clone:stop_duration={duration},trim=duration={duration}[top];"
            f"[1:v]fps={FPS},scale={PANEL_W}:{PANEL_H}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={PANEL_W}:{PANEL_H},setsar=1,trim=duration={duration}[bottom];"
            f"[top][bottom]vstack=inputs=2[stack];"
            f"[stack][2:v]overlay={LABEL_X}:{LABEL_Y}:shortest=1:format=auto,format=yuv420p[v]"
        )
        command = [
            "ffmpeg", "-v", "error", "-y", "-i", str(top),
            "-loop", "1", "-framerate", str(FPS), "-i", str(bottom),
            "-loop", "1", "-framerate", str(FPS), "-i", str(label_path),
            "-filter_complex", filters, "-map", "[v]",
        ]
        if args.audio == "none":
            command += ["-an"]
        else:
            command += ["-map", "0:a:0", "-af", "asetpts=PTS-STARTPTS,apad", "-c:a", "aac", "-b:a", "192k"]
        command += [
            "-frames:v", str(frames), "-t", f"{duration:.9f}", "-r", str(FPS),
            "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-movflags", "+faststart", str(rendered),
        ]
        run(command)
        run(["ffmpeg", "-v", "error", "-xerror", "-err_detect", "explode", "-i", str(rendered), "-f", "null", "-"])
        rendered_info = probe(rendered)
        rendered_video = next(item for item in rendered_info["streams"] if item.get("codec_type") == "video")
        actual_frames = int(rendered_video.get("nb_frames") or 0)
        if (int(rendered_video["width"]), int(rendered_video["height"]), actual_frames) != (WIDTH, HEIGHT, frames):
            raise ValueError("Output dimensions or frame count failed verification")
        os.replace(rendered, output)

    for name, timestamp in (("start", 0), ("middle", duration / 2), ("end", (frames - 1) / FPS)):
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{timestamp:.9f}", "-i", str(output), "-frames:v", "1", str(output_dir / f"comparison-{name}.png")])
    shutil.copy2(output_dir / "comparison-start.png", output_dir / "poster.png")
    (output_dir / "preview.html").write_text(
        '<!doctype html>\n<meta charset="utf-8">\n<title>EvoLink video image stack</title>\n'
        '<video controls playsinline preload="metadata" poster="poster.png" style="max-width:100%;height:auto" src="comparison.mp4"></video>\n',
        encoding="utf-8",
    )
    report = {
        "skill": {"name": "evolink-video-image-stack", "version": "1.0.0"},
        "composition": "top video / bottom static image",
        "output": {"file": output.name, "width": WIDTH, "height": HEIGHT, "fps": FPS, "frames": frames, "duration_seconds": duration, "audio": args.audio},
        "watermark": {"position": "top video upper-right", "brand": "EvoLink.ai", "model_label": args.model_label.strip(), "label_size_px": [LABEL_W, BLUE_H], "vertical_gap_px": LABEL_GAP, "margins_px": {"right": 18, "top": LABEL_Y}},
        "inputs": [
            {"role": "top", "file": top.name, "sha256": sha256(top), "width": top_info["width"], "height": top_info["height"], "duration_seconds": top_info["duration"]},
            {"role": "bottom", "file": bottom.name, "sha256": sha256(bottom), "width": bottom_info["width"], "height": bottom_info["height"], "display": "center crop to 1280x720"},
        ],
        "validation": {"full_decode": "passed", "previews": ["comparison-start.png", "comparison-middle.png", "comparison-end.png"]},
    }
    (output_dir / "render-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "previews": [str(output_dir / f"comparison-{name}.png") for name in ("start", "middle", "end")], "width": WIDTH, "height": HEIGHT, "fps": FPS, "frames": frames, "duration": duration, "audio": args.audio, "full_decode": "passed"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit((error.stderr or str(error))[-4000:])
    except (OSError, ValueError) as error:
        raise SystemExit(str(error))
