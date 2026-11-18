#!/usr/bin/env python3
"""Turn a moment from a YouTube video/livestream into a captioned vertical clip.

Pipeline:
  1. peaks     - show the "most replayed" moments, so you know where to cut
  2. download  - grab ONLY the section you want (not the whole 8-hour stream)
  3. transcribe- speech -> words with timestamps (Whisper, runs locally)
  4. captions  - build TikTok-style word-by-word captions (.ass subtitle file)
  5. render    - reframe 16:9 -> 9:16 and burn the captions in

Requirements (install once):
  - ffmpeg          https://ffmpeg.org/download.html  (must be on your PATH)
  - pip install yt-dlp faster-whisper

Examples:
  python clip.py peaks  "https://www.youtube.com/watch?v=VIDEO_ID"
  python clip.py make   "https://www.youtube.com/watch?v=VIDEO_ID" --start 1:02:10 --end 1:02:55
  python clip.py make   my_video.mp4 --start 0:30 --end 1:05      # local file works too
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------- helpers

def parse_time(t: str) -> float:
    """'1:02:10' / '62:10' / '3730' / '3730.5' -> seconds."""
    parts = [float(p) for p in str(t).split(":")]
    secs = 0.0
    for p in parts:
        secs = secs * 60 + p
    return secs


def fmt_time(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def run(cmd, cwd=None):
    print("  $", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, cwd=cwd)


def need(tool):
    if not shutil.which(tool):
        sys.exit(f"'{tool}' not found on PATH. Install it first (see top of clip.py).")


def is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


# ------------------------------------------------------- 1. find moments

def cmd_peaks(args):
    need("yt-dlp")
    out = subprocess.run(["yt-dlp", "-j", "--skip-download", args.url],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(out.stderr)
    info = json.loads(out.stdout)
    print(f"\n{info.get('title')}  -  {info.get('channel')}  ({fmt_time(info.get('duration') or 0)})\n")

    heat = info.get("heatmap")
    if not heat:
        print("No 'most replayed' data for this video (needs enough views).")
        print("Fallback: check timestamp comments, or chat replay spikes.")
    else:
        top = sorted(heat, key=lambda h: h["value"], reverse=True)
        picked = []
        for h in top:  # skip peaks that overlap one already picked
            if all(abs(h["start_time"] - p["start_time"]) > args.gap for p in picked):
                picked.append(h)
            if len(picked) == args.top:
                break
        print("Most replayed moments (start a few seconds BEFORE the peak for the setup):")
        for i, h in enumerate(sorted(picked, key=lambda h: h["start_time"]), 1):
            bar = "#" * int(h["value"] * 30)
            print(f"  {i:2}. {fmt_time(h['start_time'])} - {fmt_time(h['end_time'])}  {bar}")

    chapters = info.get("chapters") or []
    if chapters:
        print("\nChapters:")
        for c in chapters:
            print(f"  {fmt_time(c['start_time'])}  {c['title']}")


# ---------------------------------------------------------- 2. download

def download_section(src, start, end, work: Path) -> Path:
    raw = work / "raw.mp4"
    if is_url(src):
        need("yt-dlp")
        run(["yt-dlp",
             "--download-sections", f"*{start}-{end}",
             "--force-keyframes-at-cuts",
             "-f", "bv*[height<=1080]+ba/b",
             "--merge-output-format", "mp4",
             "-o", raw, "--force-overwrites", src])
    else:
        run(["ffmpeg", "-y", "-ss", start, "-to", end, "-i", src,
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", raw])
    return raw


# -------------------------------------------------------- 3. transcribe

def transcribe(video: Path, model_size: str, language):
    from faster_whisper import WhisperModel  # imported here so 'peaks' works without it
    print(f"  loading Whisper '{model_size}' (first run downloads the model)...")
    model = WhisperModel(model_size, device="auto", compute_type="auto")
    segments, _ = model.transcribe(str(video), word_timestamps=True,
                                   language=language, vad_filter=True)
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"start": w.start, "end": w.end, "word": text})
    return words


# ---------------------------------------------------------- 4. captions

def ass_time(s: float) -> str:
    cs = int(round(s * 100))
    return f"{cs // 360000}:{cs % 360000 // 6000:02d}:{cs % 6000 // 100:02d}.{cs % 100:02d}"


def chunk_words(words, max_words=3, max_gap=0.6):
    """Group words into short on-screen phrases (2-3 words reads best on phones)."""
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["start"] - cur[-1]["end"] > max_gap
                    or cur[-1]["word"][-1:] in ".?!,"):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(words, path: Path, font="Arial", size=96, highlight="00FFFF", pos_y=1350):
    """Word-by-word captions: the whole phrase shows, the spoken word lights up.
    Colours in .ass are BGR hex: 00FFFF = yellow, 00FF00 = green, FFFFFF = white."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for chunk in chunk_words(words):
        for i, w in enumerate(chunk):
            start = w["start"]
            # hold until the next word starts so captions don't flicker
            end = chunk[i + 1]["start"] if i + 1 < len(chunk) else w["end"] + 0.15
            parts = []
            for j, cw in enumerate(chunk):
                t = cw["word"].upper().replace("{", "(").replace("}", ")")
                if j == i:
                    t = f"{{\\c&H{highlight}&\\fscx112\\fscy112}}{t}{{\\r}}"
                parts.append(t)
            text = f"{{\\pos(540,{pos_y})}}" + " ".join(parts)
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Cap,,0,0,0,,{text}")
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------ 5. render

LAYOUTS = {
    # full 16:9 frame in the middle, blurred zoomed copy filling the background.
    # Best for gameplay: nothing gets cut off.
    "blur": ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
             "gblur=sigma=30,eq=brightness=-0.1[bg];"
             "[0:v]scale=1080:-2[fg];"
             "[bg][fg]overlay=(W-w)/2:(H-h)/2"),
    # crop the centre to 9:16. Best when one person is in the middle of the frame.
    "crop": "[0:v]crop=ih*9/16:ih,scale=1080:1920",
    # zoom in a bit more than 'blur' (fills 75% of the height, sides cut off).
    "zoom": ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
             "gblur=sigma=30,eq=brightness=-0.1[bg];"
             "[0:v]scale=-2:1440,crop=1080:1440[fg];"
             "[bg][fg]overlay=0:(H-h)/2"),
}


def render(raw: Path, ass: Path, out: Path, layout: str, work: Path):
    vf = LAYOUTS[layout]
    if ass:
        vf += f",ass={ass.name}"   # relative name avoids Windows path-escaping pain
    vf += "[v]"
    run(["ffmpeg", "-y", "-i", raw.name, "-filter_complex", vf,
         "-map", "[v]", "-map", "0:a?",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
         out.resolve()], cwd=work)


def cmd_make(args):
    need("ffmpeg")
    out = Path(args.out).resolve()
    work = out.parent / (out.stem + "_work")
    work.mkdir(parents=True, exist_ok=True)

    print("[2/5] downloading section", args.start, "->", args.end)
    raw = download_section(args.src, args.start, args.end, work)

    ass = None
    if not args.no_captions:
        words_file = work / "words.json"
        if args.words:
            words = json.loads(Path(args.words).read_text(encoding="utf-8"))
        else:
            print("[3/5] transcribing")
            words = transcribe(raw, args.model, args.language)
        words_file.write_text(json.dumps(words, indent=1), encoding="utf-8")
        print(f"      {len(words)} words -> {words_file}  (edit this to fix mistakes, "
              f"then re-run with --words {words_file})")
        print("[4/5] building captions")
        ass = work / "captions.ass"
        build_ass(words, ass, font=args.font, size=args.size,
                  highlight=args.highlight, pos_y=args.caption_y)

    print("[5/5] rendering", args.layout, "layout")
    render(raw, ass, out, args.layout, work)
    print(f"\nDone -> {out}")


# --------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pk = sub.add_parser("peaks", help="list the most replayed moments of a video")
    pk.add_argument("url")
    pk.add_argument("--top", type=int, default=10)
    pk.add_argument("--gap", type=float, default=90, help="min seconds between peaks")
    pk.set_defaults(func=cmd_peaks)

    mk = sub.add_parser("make", help="cut, caption and reframe one clip")
    mk.add_argument("src", help="YouTube URL or local video file")
    mk.add_argument("--start", required=True, help="e.g. 1:02:10")
    mk.add_argument("--end", required=True, help="e.g. 1:02:55")
    mk.add_argument("--out", default="clip.mp4")
    mk.add_argument("--layout", choices=LAYOUTS, default="blur")
    mk.add_argument("--model", default="small",
                    help="whisper size: tiny/base/small/medium/large-v3 (bigger = better, slower)")
    mk.add_argument("--language", default=None, help="e.g. en (default: auto-detect)")
    mk.add_argument("--words", help="reuse an edited words.json instead of transcribing")
    mk.add_argument("--no-captions", action="store_true")
    mk.add_argument("--font", default="Arial")
    mk.add_argument("--size", type=int, default=96)
    mk.add_argument("--highlight", default="00FFFF", help="BGR hex, 00FFFF = yellow")
    mk.add_argument("--caption-y", type=int, default=1350, help="0 = top, 1920 = bottom")
    mk.set_defaults(func=cmd_make)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
