# clipper

Turns a moment from a YouTube video or livestream into a vertical 9:16 clip with word-by-word captions, ready for Shorts, TikTok or Reels.

## Setup (once, on your computer)

1. Install **ffmpeg** (https://ffmpeg.org/download.html).
   - Windows: `winget install ffmpeg`
   - Mac: `brew install ffmpeg`
2. Install the two Python packages:
   ```
   pip install yt-dlp faster-whisper
   ```

## Use

```bash
# 1. Find the moments people rewatched the most
python clip.py peaks "https://www.youtube.com/watch?v=qSyo5d-dVzA"

# 2. Make a clip. Start a few seconds before the peak and end right after the payoff.
python clip.py make "https://www.youtube.com/watch?v=qSyo5d-dVzA" --start 1:02:10 --end 1:02:55 --out speed1.mp4
```

Note: the timestamps above are only an example. Use the ones `peaks` gives you.

## Fixing captions

Whisper makes mistakes, especially with slang, names and people yelling. After each run, the script saves `<clip>_work/words.json`.

1. Fix the words in `words.json`.
2. Re-render without transcribing again:

```bash
python clip.py make "URL" --start 1:02:10 --end 1:02:55 --out speed1.mp4 --words speed1_work/words.json
```

## Options

| Flag | What it does |
|---|---|
| `--layout blur` | (default) Keeps the full 16:9 frame in the middle, with a blurred copy behind it. Best for gameplay. |
| `--layout zoom` | Fills more of the screen but cuts off the sides. |
| `--layout crop` | Crops the centre to 9:16. Best for a person talking straight to the camera. |
| `--model medium` | Better transcription, but slower. Choices are `tiny` / `base` / `small` / `medium` / `large-v3`. |
| `--highlight 00FF00` | Sets the colour of the spoken word. The hex is BGR: `00FFFF` is yellow and `00FF00` is green. |
| `--caption-y 1500` | Sets how high the captions sit: 0 is the top and 1920 is the bottom. |
| `--font "Impact"` | Uses any font installed on your computer. |

## If YouTube says "Sign in to confirm you're not a bot"

Add `--cookies-from-browser chrome` (or `firefox` / `edge`) to the yt-dlp call in `download_section()` in `clip.py`.
