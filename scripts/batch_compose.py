#!/usr/bin/env python3
"""Compose one comparison video for every input folder in a directory."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


VIDEO_SUFFIXES = frozenset({
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ts",
    ".webm",
})
IMAGE_SUFFIXES = frozenset({
    ".bmp",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
})
COMPOSE_SCRIPT = Path(__file__).with_name("compose.py")


def discover_jobs(input_root: Path) -> list[dict[str, Path]]:
    if not input_root.is_dir():
        raise ValueError(f"Input root does not exist or is not a directory: {input_root}")

    folders = sorted(path for path in input_root.iterdir() if path.is_dir())
    if not folders:
        raise ValueError(f"Input root contains no subfolders: {input_root}")

    jobs: list[dict[str, Path]] = []
    for folder in folders:
        files = [path for path in folder.iterdir() if path.is_file() and not path.name.startswith(".")]
        videos = sorted(path for path in files if path.suffix.lower() in VIDEO_SUFFIXES)
        images = sorted(path for path in files if path.suffix.lower() in IMAGE_SUFFIXES)
        if len(videos) != 1 or len(images) != 1:
            raise ValueError(
                f"{folder}: expected exactly one video and one image; "
                f"found {len(videos)} video(s) and {len(images)} image(s)"
            )
        jobs.append({"folder": folder, "video": videos[0], "image": images[0]})
    return jobs


def run_job(job: dict[str, Path], output_root: Path, model_label: str, audio: str, overwrite: bool) -> dict:
    output_dir = output_root / job["folder"].name
    output = output_dir / "comparison.mp4"
    if output.exists() and not overwrite:
        raise ValueError(f"Output already exists: {output}; pass --overwrite to update it")

    command = [
        sys.executable,
        str(COMPOSE_SCRIPT),
        "--top-video",
        str(job["video"]),
        "--bottom-image",
        str(job["image"]),
        "--model-label",
        model_label,
        "--output-dir",
        str(output_dir),
        "--audio",
        audio,
    ]
    if overwrite:
        command.append("--overwrite")

    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"Failed to compose {job['folder'].name}: {detail}")

    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"compose.py returned invalid JSON for {job['folder'].name}") from error
    return {
        "folder": job["folder"].name,
        "video": job["video"].name,
        "image": job["image"].name,
        "result": result,
    }


def check_output_conflicts(jobs: list[dict[str, Path]], output_root: Path, overwrite: bool) -> None:
    if overwrite:
        return
    conflicts = []
    for job in jobs:
        output = output_root / job["folder"].name / "comparison.mp4"
        if output.exists():
            conflicts.append(output)
    if conflicts:
        joined = "\n".join(str(path) for path in conflicts)
        raise ValueError(f"Output already exists:\n{joined}\nPass --overwrite to update existing results")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True, type=Path, help="Directory containing one subfolder per composition")
    parser.add_argument("--output-root", required=True, type=Path, help="Directory receiving one output subfolder per input folder")
    parser.add_argument("--model-label", required=True)
    parser.add_argument("--audio", choices=("top", "none"), default="top")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if not args.model_label.strip():
        parser.error("--model-label must be nonempty")
    input_root = args.input_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    if output_root == input_root or input_root in output_root.parents:
        parser.error("--output-root must be outside --input-root")

    try:
        jobs = discover_jobs(input_root)
        check_output_conflicts(jobs, output_root, args.overwrite)
        results = [run_job(job, output_root, args.model_label.strip(), args.audio, args.overwrite) for job in jobs]
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))

    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "batch-report.json"
    report = {
        "skill": "evolink-video-image-stack",
        "mode": "batch",
        "model_label": args.model_label.strip(),
        "audio": args.audio,
        "input_root": str(input_root),
        "output_root": str(output_root),
        "jobs": results,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_root": str(output_root), "batch_report": str(report_path), "jobs": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
