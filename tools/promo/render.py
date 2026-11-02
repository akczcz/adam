"""
render.py – z nahrávky (record.py) a scénáře (scenes.py) složí promo video: komentář Azure AI Speech (TTS, cs-CZ) + střih ffmpeg → promo.mp4 + promo.srt.

Vstup:  --in  adresář s video.webm, scenes.json, cards/<id>.png (výstup record.py)
Výstup: --out/promo.mp4 (1920×1080, 30 fps, H.264 + AAC), promo.srt (titulky = komentář), tts/<id>.mp3

TTS: SPEECH_KEY (env, nikdy v argumentech ani logu) + --speech-region → REST https://<region>.tts.speech.microsoft.com/cognitiveservices/v1 (SSML).
Bez SPEECH_KEY se místo hlasu vloží ticho dle odhadu délky (kontrola střihu bez útraty).

Pravidla střihu: délku scény určuje komentář (+0,6 s pauza); karta = statický obraz; klip GUI = úsek [t0, t1] nahrávky – delší se ořízne,
kratší podrží poslední snímek (tpad). Scéna GUI bez časové značky (natáčení skončilo dřív) se nahradí kartou se stejným titulkem.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from scenes import RATE, SCENES, VOICE   # noqa: E402

FONT = next((p for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf") if Path(p).exists()), None)


def run(*cmd, quiet=True):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode: raise RuntimeError(f"{cmd[0]} selhal ({r.returncode}): {r.stderr[-800:]}")
    return r.stdout


def duration(path):
    return float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path).strip())


def tts(text, path: Path, region, voice, rate):
    key = os.environ.get("SPEECH_KEY")
    if not key:   # bez klíče: ticho ~ 0,42 s na slovo (cs-CZ neurální hlas ≈ 140 slov/min)
        run("ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", f"{max(2.0, 0.42 * len(text.split())):.2f}", "-q:a", "9", "-acodec", "libmp3lame", path); return "silence"
    ssml = (f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='cs-CZ'><voice name='{voice}'><prosody rate='{rate}'>{html.escape(text)}</prosody></voice></speak>")
    r = httpx.post(f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1", content=ssml.encode("utf-8"), timeout=60,
                   headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml", "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3", "User-Agent": "adam-promo"})
    if r.status_code != 200: raise RuntimeError(f"TTS {r.status_code}: {r.text[:200]}")   # klíč se nikdy neloguje
    path.write_bytes(r.content); return "azure"


def card_fallback(s, out: Path):
    """Scéna GUI bez záběru → karta s titulkem (stejný vzhled jako record.card_html)."""
    from record import card_html
    from playwright.sync_api import sync_playwright
    p = out / "cards" / f"{s['id']}-fallback.png"
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, executable_path=os.environ.get("PW_CHROMIUM") or None); pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.set_content(card_html({**s, "layer": None, "sub": "řídicí pult firmy", "bullets": []})); pg.screenshot(path=str(p)); b.close()
    return p


def srt_time(t):
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=str(HERE / "out")); ap.add_argument("--out", default=None)
    ap.add_argument("--speech-region", default="westeurope"); ap.add_argument("--voice", default=VOICE); ap.add_argument("--rate", default=RATE)
    ap.add_argument("--gap", type=float, default=0.6, help="s ticha za komentářem scény")
    a = ap.parse_args()
    inp = Path(a.inp); out = Path(a.out or a.inp); (out / "tts").mkdir(parents=True, exist_ok=True); (out / "seg").mkdir(exist_ok=True)
    marks = json.loads((inp / "scenes.json").read_text())["marks"] if (inp / "scenes.json").exists() else {}
    video = inp / "video.webm"; vdur = duration(video) if video.exists() else 0.0
    segs, srt, t_acc, report = [], [], 0.0, []
    vf_base = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p"
    for i, s in enumerate(SCENES):
        mp3 = out / "tts" / f"{s['id']}.mp3"; src = tts(s["say"], mp3, a.speech_region, a.voice, a.rate); d = duration(mp3) + a.gap
        seg = out / "seg" / f"{i:02}-{s['id']}.mp4"
        m = marks.get(s["id"]) or {}
        gui_ok = s["kind"] == "gui" and video.exists() and "t0" in m and m.get("t1", vdur) - m["t0"] >= 3 and m["t0"] < vdur
        if gui_ok:
            t0 = m["t0"]; clip = min(m.get("t1", vdur) - t0, vdur - t0, d)
            label = (f",drawtext=fontfile={FONT}:text='{s['title'].replace(chr(39), '').replace(':', '\\:')}':fontcolor=white:fontsize=38:box=1:boxcolor=0x0b1020@0.72:boxborderw=18:x=60:y=h-110" if FONT else "")
            run("ffmpeg", "-y", "-ss", f"{t0:.2f}", "-t", f"{clip:.2f}", "-i", video, "-i", mp3, "-f", "lavfi", "-t", f"{d:.2f}", "-i", "anullsrc=r=48000:cl=stereo",
                "-filter_complex", f"[0:v]{vf_base},tpad=stop_mode=clone:stop_duration={max(0.0, d - clip) + 0.5:.2f}{label}[v];[1:a][2:a]amix=inputs=2:duration=longest:normalize=0[a]",
                "-map", "[v]", "-map", "[a]", "-t", f"{d:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", seg)
            kind = "gui"
        else:
            png = inp / "cards" / f"{s['id']}.png" if s["kind"] == "card" else card_fallback(s, out)
            frames = int(d * 30) + 1   # zoompan z jednoho snímku: d výstupních snímků s pomalým přiblížením (Ken Burns), ne statický obraz
            run("ffmpeg", "-y", "-i", png, "-i", mp3, "-f", "lavfi", "-t", f"{d:.2f}", "-i", "anullsrc=r=48000:cl=stereo",
                "-filter_complex", f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,zoompan=z='min(zoom+0.0004,1.06)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30,format=yuv420p[v];[1:a][2:a]amix=inputs=2:duration=longest:normalize=0[a]",
                "-map", "[v]", "-map", "[a]", "-t", f"{d:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", seg)
            kind = "card" if s["kind"] == "card" else "card-fallback"
        segs.append(seg); srt.append(f"{len(srt) + 1}\n{srt_time(t_acc)} --> {srt_time(t_acc + d - a.gap)}\n{s['say']}\n"); t_acc += d
        report.append({"id": s["id"], "kind": kind, "s": round(d, 1), "tts": src})
        print(f"  {s['id']:14} {kind:14} {d:5.1f} s  tts={src}", flush=True)
    (out / "concat.txt").write_text("".join(f"file '{p.resolve()}'\n" for p in segs))
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", out / "concat.txt", "-c", "copy", "-movflags", "+faststart", out / "promo.mp4")
    (out / "promo.srt").write_text("\n".join(srt), encoding="utf-8")
    total = duration(out / "promo.mp4")
    (out / "render.json").write_text(json.dumps({"total_s": round(total, 1), "scenes": report, "video_s": round(vdur, 1)}, ensure_ascii=False, indent=1))
    print(json.dumps({"promo_mp4": str(out / "promo.mp4"), "total_s": round(total, 1), "video_s": round(vdur, 1)}, ensure_ascii=False))
    if total > 185: print(f"VAROVÁNÍ: {total:.0f} s > 3 min – zkrátit komentář ve scenes.py", flush=True)


if __name__ == "__main__":
    main()
