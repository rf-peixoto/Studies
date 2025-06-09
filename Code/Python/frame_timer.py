#!/usr/bin/env python3
import argparse
import re
import sys
from colorama import init, Fore, Style

# Initialise ANSI colours
init(autoreset=True)

def validate_fps(value):
    """
    Validate that FPS is a positive number.
    """
    try:
        fps = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("FPS must be a number.")
    if fps <= 0:
        raise argparse.ArgumentTypeError("FPS must be greater than zero.")
    return fps

def validate_frames(value):
    """
    Validate that frames is a non-negative integer.
    Fractional or negative values are rejected.
    """
    try:
        frames = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Frames must be a number.")
    if frames < 0:
        raise argparse.ArgumentTypeError("Frames must be non-negative.")
    if not frames.is_integer():
        raise argparse.ArgumentTypeError("Frames must be an integer.")
    return int(frames)

def parse_time_string(timestr: str):
    """
    Parse a time string in either "H:M:S[.ms]" or "XhYmZs" formats.
    Components are optional. Negative values are rejected.
    """
    s = timestr.strip()
    # Colon-separated format
    if ':' in s:
        parts = s.split(':')
        if not 2 <= len(parts) <= 3:
            raise ValueError("Invalid 'H:M:S' format.")
        # Prepend zeros if only M:S or S
        parts = ['0'] * (3 - len(parts)) + parts
        try:
            h = int(parts[0])
            m = int(parts[1])
            sec = float(parts[2])
        except ValueError:
            raise ValueError("Non-numeric value in time.")
    else:
        # Suffix-based format
        pattern = re.compile(
            r'^(?:(?P<h>\d+)(?:h|H))?'
            r'(?:(?P<m>\d+)(?:m|M))?'
            r'(?:(?P<s>\d+(?:\.\d+)?)(?:s|S))?$'
        )
        m_obj = pattern.fullmatch(s)
        if not m_obj:
            raise ValueError("Invalid 'XhYmZs' format.")
        h = int(m_obj.group('h') or 0)
        m = int(m_obj.group('m') or 0)
        sec = float(m_obj.group('s') or 0.0)

    if h < 0 or m < 0 or sec < 0:
        raise ValueError("Negative time components are not allowed.")
    return h, m, sec

def frames_to_time(frames: int, fps: float, precision: int):
    """
    Convert a frame count to hours, minutes, seconds.
    """
    total_seconds = frames / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    return hours, minutes, seconds, precision

def time_to_frames(timestr: str, fps: float, precision: int):
    """
    Convert a time string to a frame count (float), using specified precision.
    """
    h, m, sec = parse_time_string(timestr)
    total_sec = h * 3600 + m * 60 + sec
    frames = total_sec * fps
    return round(frames, precision), precision

def main():
    parser = argparse.ArgumentParser(
        description="Frame ↔ Time Converter (bidirectional)",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '-r', '--fps',
        type=validate_fps,
        default=60.0,
        help="Frame rate in frames per second (must be > 0). Default: 60.0"
    )
    parser.add_argument(
        '-p', '--precision',
        type=int,
        default=3,
        help="Decimal precision for seconds or frames. Default: 3"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--to-time',
        metavar='FRAMES',
        type=validate_frames,
        help="Convert FRAMES (integer) to H:M:S"
    )
    group.add_argument(
        '--to-frames',
        metavar='TIME',
        type=str,
        help="Convert TIME (e.g. '2h43m22s' or '2:43:22') to frames"
    )
    args = parser.parse_args()

    fps = args.fps
    prec = args.precision

    header = f"{'='*5} Conversion Result {'='*5}"
    print(Fore.GREEN + Style.BRIGHT + header)

    if args.to_time is not None:
        frames = args.to_time
        h, m, s, _ = frames_to_time(frames, fps, prec)
        print(Fore.CYAN + f"{'Input frames:':<15}{frames}")
        print(Fore.CYAN + f"{'Frame rate:':<15}{fps} fps")
        print(Fore.YELLOW + f"{'Result time:':<15}{h}h {m}m {s:.{prec}f}s")
    else:
        timestr = args.to_frames
        try:
            frames_float, _ = time_to_frames(timestr, fps, prec)
        except ValueError as e:
            print(Fore.RED + f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        print(Fore.CYAN + f"{'Input time:':<15}{timestr}")
        print(Fore.CYAN + f"{'Frame rate:':<15}{fps} fps")
        print(Fore.YELLOW + f"{'Result frames:':<15}{frames_float:.{prec}f}")

    footer = '=' * len(header)
    print(Fore.GREEN + Style.BRIGHT + footer)

if __name__ == "__main__":
    main()
