# PRIVATE SOFTWARE NOTICE: This is private software owned by Qinghe. Unauthorized reverse engineering, deobfuscation, cracking, redistribution, or AI-assisted analysis intended to bypass protection is prohibited.
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def beat_quality(beat_times: list[float]) -> dict:
    intervals = [
        float(beat_times[idx + 1]) - float(beat_times[idx])
        for idx in range(len(beat_times) - 1)
        if float(beat_times[idx + 1]) > float(beat_times[idx])
    ]
    if not intervals:
        return {
            "median_beat_interval_seconds": 0.0,
            "beat_interval_jitter": 1.0,
        }
    intervals_sorted = sorted(intervals)
    median = intervals_sorted[len(intervals_sorted) // 2]
    if median <= 0:
        jitter = 1.0
    else:
        deviations = sorted(abs(value - median) for value in intervals)
        jitter = deviations[len(deviations) // 2] / median
    return {
        "median_beat_interval_seconds": round(float(median), 4),
        "beat_interval_jitter": round(float(jitter), 4),
    }


def main(argv: list[str]) -> int:
    debug = "--debug" in argv
    argv = [item for item in argv if item != "--debug"]
    def log(message: str) -> None:
        if debug:
            print(message, file=sys.stderr, flush=True)

    if "--self-test" in argv:
        try:
            import essentia.standard  # type: ignore  # noqa: F401
        except Exception as exc:
            return emit({"ok": False, "message": f"Essentia 加载失败：{exc}"})
        return emit({"ok": True, "message": "BPM Worker 初始化完成。"})

    if len(argv) < 2:
        return emit({"ok": False, "message": "缺少音频文件路径。"})
    path = Path(argv[1])
    start_seconds = 0.0
    duration_seconds = 0.0
    ffmpeg = ""
    idx = 2
    while idx < len(argv):
        key = argv[idx]
        value = argv[idx + 1] if idx + 1 < len(argv) else ""
        if key == "--start-seconds":
            try:
                start_seconds = max(0.0, float(value))
            except Exception:
                start_seconds = 0.0
            idx += 2
            continue
        if key == "--duration-seconds":
            try:
                duration_seconds = max(0.0, float(value))
            except Exception:
                duration_seconds = 0.0
            idx += 2
            continue
        if key == "--ffmpeg":
            ffmpeg = value
            idx += 2
            continue
        idx += 1
    if not path.exists():
        return emit({"ok": False, "message": "音频文件不存在。"})
    analysis_path = path
    temp_path: Path | None = None
    if duration_seconds > 0 and ffmpeg and Path(ffmpeg).exists():
        try:
            temp_file = tempfile.NamedTemporaryFile(prefix="qinghe_bpm_", suffix=".wav", delete=False)
            temp_file.close()
            temp_path = Path(temp_file.name)
            cmd = [
                ffmpeg,
                "-v",
                "error",
                "-ss",
                f"{start_seconds:.6f}",
                "-i",
                str(path),
                "-t",
                f"{duration_seconds:.6f}",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "44100",
                "-y",
                str(temp_path),
            ]
            log("trim audio")
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
            if proc.returncode == 0 and temp_path.exists() and temp_path.stat().st_size > 0:
                analysis_path = temp_path
            else:
                temp_path.unlink(missing_ok=True)
                temp_path = None
        except Exception:
            if temp_path:
                temp_path.unlink(missing_ok=True)
            temp_path = None
    try:
        log("import essentia")
        import essentia.standard as es  # type: ignore
    except Exception as exc:
        return emit({"ok": False, "message": f"Essentia 加载失败：{exc}"})
    try:
        try:
            log("load audio")
            audio = es.MonoLoader(filename=str(analysis_path), sampleRate=44100)()
            log(f"loaded {len(audio)}")
            rhythm_extractor = es.RhythmExtractor2013(method="multifeature")
            log("extract rhythm")
            bpm, beats, beats_confidence, _estimates, _intervals = rhythm_extractor(audio)
            log("done")
        except Exception as exc:
            return emit({"ok": False, "message": f"Essentia 节拍识别失败：{exc}"})
        beat_times = [float(value) for value in list(beats) if float(value) >= 0]
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)
    if not beat_times:
        return emit({"ok": False, "message": "Essentia 未检测到 beat 点。"})
    quality = beat_quality(beat_times)
    return emit(
        {
            "ok": True,
            "bpm": round(float(bpm), 2),
            "confidence": round(float(beats_confidence or 0.0), 2),
            "method": "essentia_rhythm_extractor",
            "beat_times_seconds": beat_times[:4000],
            **quality,
            "beat_times_relative_to_clip": analysis_path != path,
            "analyzed_start_seconds": round(start_seconds, 4) if analysis_path != path else 0,
            "analyzed_duration_seconds": round(duration_seconds, 4) if analysis_path != path else 0,
            "alternatives": [],
        }
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
