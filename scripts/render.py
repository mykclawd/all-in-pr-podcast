#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Render an all-in-pr-podcast script.md to a single MP3.

Usage:
  render.py script.md --dry-run
  render.py script.md -o episode.mp3 [--engine auto|elevenlabs|say]
  render.py --list-voices
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
HOSTS = ("JASON", "FRIEDBERG", "CHAMATH", "SACKS")
LINE_RE = re.compile(r"^\s*\**(JASON|FRIEDBERG|CHAMATH|SACKS)\**\s*:\s*(.+?)\s*$", re.I)
TAG_RE = re.compile(r"\[[a-z ,'-]+\]\s*", re.I)
API = "https://api.elevenlabs.io"
WPM = 150  # measured with the voices.json cast: 444 words -> 2:58, 474 -> 2:59
MIN_WORDS, TARGET_MAX, HARD_MAX = 300, 470, 600  # warn outside 300-470 (~2:15-3:30); fail only above 600 (~4:25)


def die(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def load_config() -> dict:
    return json.loads((SKILL_DIR / "voices.json").read_text())


def parse(path: Path) -> list[tuple[str, str]]:
    turns = []
    for raw in path.read_text().splitlines():
        m = LINE_RE.match(raw)
        if m:
            turns.append((m.group(1).upper(), m.group(2)))
    if not turns:
        die(f"no speaker lines (HOST: text) found in {path}")
    return turns


def spoken(text: str) -> str:
    return TAG_RE.sub("", text).strip()


def apply_pronunciations(text: str, pron: dict) -> str:
    """Respell names for TTS only (e.g. Friedberg -> Freedberg)."""
    for word, say in pron.items():
        text = re.sub(rf"\b{re.escape(word)}\b", say, text)
    return text


def host_speed(cfg: dict, host: str) -> float:
    return float(cfg.get("speed", {}).get(host, 1.0))


def stats(turns: list[tuple[str, str]]) -> dict:
    per = {h: {"turns": 0, "words": 0} for h in HOSTS}
    for host, text in turns:
        per[host]["turns"] += 1
        per[host]["words"] += len(spoken(text).split())
    words = sum(p["words"] for p in per.values())
    chars = sum(len(t) for _, t in turns)
    return {"per": per, "words": words, "chars": chars, "est_sec": round(words / WPM * 60)}


def check(s: dict) -> list[str]:
    problems = []
    per = s["per"]
    if s["words"] > HARD_MAX:
        problems.append(f"too long: {s['words']} words (hard max {HARD_MAX})")
    for h in HOSTS:
        if per[h]["turns"] == 0:
            problems.append(f"{h} never speaks")
    if per["FRIEDBERG"]["words"] < max(per[h]["words"] for h in HOSTS):
        problems.append("FRIEDBERG should have the most words (he owns the how)")
    if per["SACKS"]["turns"] < 2:
        problems.append("SACKS needs at least 2 turns (alternative + risk)")
    return problems


def print_stats(s: dict) -> None:
    for h in HOSTS:
        p = s["per"][h]
        print(f"  {h:<10} {p['turns']:>2} turns  {p['words']:>4} words")
    print(f"  total: {s['words']} words, {s['chars']} chars (~credits), est {s['est_sec'] // 60}:{s['est_sec'] % 60:02d}")


# ---------- ElevenLabs ----------

def api_key() -> str | None:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if key:
        return key.strip()
    if shutil.which("security"):
        r = subprocess.run(
            ["security", "find-generic-password", "-a", os.environ.get("USER", ""), "-s", "elevenlabs-api-key", "-w"],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    return None


def http(method: str, url: str, key: str, body: dict | None = None) -> bytes:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("xi-api-key", key)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        hint = {401: "invalid API key", 402: "out of credits / plan limit", 422: "request rejected; try --chunk-chars 1200", 429: "rate limited; retry shortly"}.get(e.code, "")
        die(f"ElevenLabs HTTP {e.code} {hint}: {detail}")
    except urllib.error.URLError as e:
        die(f"cannot reach ElevenLabs: {e.reason}")


def chunk(turns: list[tuple[str, str]], limit: int) -> list[list[tuple[str, str]]]:
    chunks, cur, size = [], [], 0
    for t in turns:
        n = len(t[1])
        if cur and size + n > limit:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(t)
        size += n
    if cur:
        chunks.append(cur)
    return chunks


def retime_segments(src: Path, dst: Path, segments: list[dict], speeds: list[float]) -> None:
    """Speed up individual speakers inside one dialogue clip. ElevenLabs returns
    back-to-back voice segments; each is cut out, tempo-adjusted (pitch kept),
    and joined again in order, so nothing overlaps."""
    chains, labels = [], []
    for i, seg in enumerate(segments):
        start = seg["start_time_seconds"]
        end = segments[i + 1]["start_time_seconds"] if i + 1 < len(segments) else None
        trim = f"atrim=start={start}" + (f":end={end}" if end is not None else "")
        tempo = f",atempo={speeds[i]}" if abs(speeds[i] - 1.0) > 0.01 else ""
        chains.append(f"[0:a]{trim},asetpts=PTS-STARTPTS{tempo}[s{i}]")
        labels.append(f"[s{i}]")
    graph = ";".join(chains) + f";{''.join(labels)}concat=n={len(labels)}:v=0:a=1[out]"
    ffmpeg(["-i", str(src), "-filter_complex", graph, "-map", "[out]",
            "-ar", "44100", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "128k", str(dst)])


def render_elevenlabs(turns, cfg, key, workdir: Path, chunk_chars: int) -> list[Path]:
    el = cfg["elevenlabs"]
    voices = el["voices"]
    pron = cfg.get("pronunciations", {})
    retime = any(abs(host_speed(cfg, h) - 1.0) > 0.01 for h, _ in turns)
    parts = []
    groups = chunk(turns, chunk_chars)
    for i, group in enumerate(groups):
        print(f"  elevenlabs chunk {i + 1}/{len(groups)} ({sum(len(t) for _, t in group)} chars)", file=sys.stderr)
        body = {
            "model_id": el.get("model_id", "eleven_v3"),
            "inputs": [{"voice_id": voices[h], "text": apply_pronunciations(t, pron)} for h, t in group],
        }
        fmt = el.get("output_format", "mp3_44100_128")
        raw = workdir / f"part{i:03d}.raw.mp3"
        p = workdir / f"part{i:03d}.mp3"
        if not retime:
            raw.write_bytes(http("POST", f"{API}/v1/text-to-dialogue?output_format={fmt}", key, body))
            raw.rename(p)
        else:
            data = json.loads(http("POST", f"{API}/v1/text-to-dialogue/with-timestamps?output_format={fmt}", key, body))
            raw.write_bytes(base64.b64decode(data["audio_base64"]))
            segs = sorted(data.get("voice_segments") or [], key=lambda x: x["start_time_seconds"])
            if not segs:
                raw.rename(p)
            else:
                speeds = [host_speed(cfg, group[sg["dialogue_input_index"]][0]) for sg in segs]
                retime_segments(raw, p, segs, speeds)
        parts.append(p)
    return parts


def list_voices(key: str) -> None:
    data = json.loads(http("GET", f"{API}/v2/voices?page_size=100", key))
    for v in data.get("voices", []):
        labels = v.get("labels") or {}
        desc = ", ".join(str(x) for x in (labels.get("gender"), labels.get("age"), labels.get("accent"), labels.get("descriptive") or labels.get("description"), labels.get("use_case")) if x)
        print(f"{v['voice_id']}  {v['name']:<28} {v.get('category', ''):<10} {desc}")


# ---------- macOS say ----------

def render_say(turns, cfg, workdir: Path) -> list[Path]:
    if not shutil.which("say"):
        die("macOS `say` not available; set an ElevenLabs key instead")
    sc = cfg["say"]
    installed = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    parts = []
    for i, (host, text) in enumerate(turns):
        voice = sc["voices"][host]
        args = ["say", "-r", str(sc.get("rate", 200))]
        if voice.split(" (")[0] in installed:
            args += ["-v", voice]
        aiff = workdir / f"turn{i:03d}.aiff"
        line = apply_pronunciations(spoken(text), cfg.get("pronunciations", {})).replace("—", ", ")
        subprocess.run(args + ["-o", str(aiff), line], check=True)
        mp3 = workdir / f"turn{i:03d}.mp3"
        speed = host_speed(cfg, host)
        tempo = ["-af", f"atempo={speed}"] if abs(speed - 1.0) > 0.01 else []
        ffmpeg(["-i", str(aiff), *tempo, "-ar", "44100", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "128k", str(mp3)])
        parts.append(mp3)
    return parts


# ---------- stitching ----------

def ffmpeg(args: list[str]) -> None:
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True)
    if r.returncode != 0:
        die(f"ffmpeg failed: {r.stderr.strip()}")


def stitch(parts: list[Path], out: Path, workdir: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if len(parts) == 1:
        shutil.copyfile(parts[0], out)
        return
    lst = workdir / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "128k", str(out)])


def duration(path: Path) -> str:
    if not shutil.which("ffprobe"):
        return "?"
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        s = round(float(r.stdout.strip()))
        return f"{s // 60}:{s % 60:02d}"
    except ValueError:
        return "?"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", nargs="?", type=Path)
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--engine", choices=("auto", "elevenlabs", "say"), default="auto")
    ap.add_argument("--dry-run", action="store_true", help="validate the script; no API calls")
    ap.add_argument("--force", action="store_true", help="render even if validation fails")
    ap.add_argument("--chunk-chars", type=int, default=1800)
    ap.add_argument("--list-voices", action="store_true")
    a = ap.parse_args()
    cfg = load_config()

    if a.list_voices:
        key = api_key() or die("no ElevenLabs key (ELEVENLABS_API_KEY or keychain item elevenlabs-api-key)")
        list_voices(key)
        return
    if not a.script:
        ap.error("script path required")

    turns = parse(a.script)
    s = stats(turns)
    problems = check(s)
    print_stats(s)
    if s["words"] < MIN_WORDS or TARGET_MAX < s["words"] <= HARD_MAX:
        print(f"  WARN: {s['words']} words is outside the {MIN_WORDS}-{TARGET_MAX} target; fine if the content needs it")
    for p in problems:
        print(f"  FAIL: {p}")
    if a.dry_run:
        print("  OK" if not problems else "  validation failed")
        sys.exit(1 if problems else 0)
    if problems and not a.force:
        die("validation failed; fix the script or pass --force")
    if not shutil.which("ffmpeg"):
        die("ffmpeg not found; brew install ffmpeg")

    out = a.out or a.script.with_name("episode.mp3")
    engine = a.engine
    key = api_key() if engine in ("auto", "elevenlabs") else None
    if engine == "elevenlabs" and not key:
        die("no ElevenLabs key. Run: security add-generic-password -a \"$USER\" -s elevenlabs-api-key -w")
    if engine == "auto":
        engine = "elevenlabs" if key else "say"
        if engine == "say":
            print("  no ElevenLabs key found; falling back to macOS say", file=sys.stderr)

    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        parts = render_elevenlabs(turns, cfg, key, wd, a.chunk_chars) if engine == "elevenlabs" else render_say(turns, cfg, wd)
        stitch(parts, out, wd)

    used = s["chars"] if engine == "elevenlabs" else 0
    print(f"wrote {out} ({duration(out)}, engine={engine}, ~{used} credits)")


if __name__ == "__main__":
    main()
