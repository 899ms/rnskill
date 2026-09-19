#!/usr/bin/env python3
"""Read-only source-video audit; visual samples are not a creative verdict."""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--cuts', default='', help='Actual cut times in seconds, comma separated')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--samples', type=int, default=25, help='Overview frames, 4–64')
    args = parser.parse_args()
    source = args.video.resolve()
    if not source.is_file():
        parser.error('Source video does not exist')
    if not 4 <= args.samples <= 64:
        parser.error('--samples must be between 4 and 64')
    for tool in ('ffmpeg', 'ffprobe'):
        if not shutil.which(tool):
            parser.error(f'{tool} must be installed and on PATH')
    try:
        cuts = [float(v.strip()) for v in args.cuts.split(',') if v.strip()]
    except ValueError:
        parser.error('--cuts must contain numbers')
    meta = json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(source)]).stdout)
    videos = [s for s in meta['streams'] if s['codec_type'] == 'video' and not s.get('disposition', {}).get('attached_pic')]
    audios = [s for s in meta['streams'] if s['codec_type'] == 'audio']
    if not videos:
        parser.error('Input has no video stream')
    duration = float(videos[0].get('duration') or meta['format']['duration'])
    if not math.isfinite(duration) or duration <= 0:
        parser.error('Input has no usable duration')
    if any(not math.isfinite(c) or not 0 < c < duration for c in cuts):
        parser.error('Each cut must be strictly inside the video duration')
    cuts = sorted(set(cuts))
    out = args.out.resolve()
    targets = ['report.json', 'decode.log', 'overview.jpg'] + [f'cut-{i:02d}.jpg' for i in range(1, len(cuts) + 1)]
    if any((out / name).exists() for name in targets):
        parser.error('Output artifacts already exist; choose a new --out directory')
    out.mkdir(parents=True, exist_ok=True)
    cmd = ['ffmpeg', '-hide_banner', '-nostdin', '-i', str(source), '-map', f'0:{videos[0]["index"]}', '-vf', 'blackdetect=d=0.05:pix_th=0.04']
    if audios:
        cmd += ['-map', f'0:{audios[0]["index"]}', '-af', 'volumedetect']
    cmd += ['-f', 'null', '-']
    decoded = subprocess.run(cmd, capture_output=True, text=True)
    (out / 'decode.log').write_text(decoded.stderr)
    report = {
        'source': str(source), 'duration_seconds': duration,
        'media': meta, 'cuts_seconds': cuts, 'decode_ok': decoded.returncode == 0,
        'black_intervals': re.findall(r'black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)', decoded.stderr),
        'audio_measurements': re.findall(r'(mean_volume|max_volume):\s*([-\w.]+) dB', decoded.stderr),
        'limits': 'Visual samples require inspection. Black detection may flag intentional darkness. Audio levels do not verify sound design, absence of speech, synchronization, or listening quality.'
    }
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    if decoded.returncode:
        raise RuntimeError(f'Full decode failed; inspect {out / "decode.log"}')
    columns = min(5, args.samples)
    rows = math.ceil(args.samples / columns)
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-n', '-i', str(source), '-map', f'0:{videos[0]["index"]}', '-vf', f'fps={args.samples / duration:.9f},scale=480:-1,tile={columns}x{rows}:nb_frames={args.samples}', '-frames:v', '1', str(out / 'overview.jpg')])
    for i, cut in enumerate(cuts, 1):
        start = max(0, cut - 0.6)
        length = min(1.2, duration - start)
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-n', '-ss', str(start), '-i', str(source), '-t', str(length), '-map', f'0:{videos[0]["index"]}', '-vf', 'fps=5,scale=480:-1,tile=6x1', '-frames:v', '1', str(out / f'cut-{i:02d}.jpg')])
    print(json.dumps({'output': str(out), 'duration_seconds': duration, 'decode_ok': True, 'cuts': len(cuts)}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (subprocess.CalledProcessError, RuntimeError, ValueError, KeyError) as exc:
        print(f'Audit failed: {exc}', file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError):
            print(exc.stderr, file=sys.stderr)
        sys.exit(1)
