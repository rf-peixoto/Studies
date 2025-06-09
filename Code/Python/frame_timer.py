#!/usr/bin/env python3
import argparse
import re
from colorama import init, Fore, Style

# Initialise ANSI colours
init(autoreset=True)

def frames_to_time(frames: int, fps: float) -> tuple[int, int, float]:
    """
    Convert a frame count to hours, minutes, seconds.
    """
    total_seconds = frames / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    return hours, minutes, seconds

def time_to_frames(timestr: str, fps: float) -> int:
    """
    Parse a time string of form 'XhYmZs' (components optional; case-insensitive)
    and convert to a frame count.
    """
    pattern = re.compile(r'^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?$', re.IGNORECASE)
    m = pattern.fullmatch(timestr.strip())
    if not m:
        raise ValueError("Invalid format. Expected e.g. 2h43m22s")
    h = int(m.group(1) or 0)
    mi = int(m.group(2) or 0)
    s = float(m.group(3) or 0.0)
    total_sec = h * 3600 + mi * 60 + s
    return int(total_sec * fps)

def main():
    parser = argparse.ArgumentParser(
        description="Frame↔Time Converter",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '-r', '--fps', type=float, default=60.0,
        help="Frame rate (frames per second). Default: 60.0"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--to-time', metavar='FRAMES', type=int,
        help="Convert FRAMES to H:M:S"
    )
    group.add_argument(
        '--to-frames', metavar='TIME', type=str,
        help="Convert TIME (e.g. 2h43m22s) to frame count"
    )
    args = parser.parse_args()

    fps = args.fps
    if args.to_time is not None:
        h, m, s = frames_to_time(args.to_time, fps)
        print(Fore.CYAN + f"▶ Input frames: {args.to_time}")
        print(Fore.YELLOW + f"⇨ Time: {h}h {m}m {s:.3f}s")
    else:
        frames = time_to_frames(args.to_frames, fps)
        print(Fore.CYAN + f"▶ Input time: {args.to_frames}")
        print(Fore.YELLOW + f"⇨ Frames: {frames}")

if __name__ == "__main__":
    main()
