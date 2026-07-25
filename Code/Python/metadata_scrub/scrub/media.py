"""Audio and video scrubbing via PyAV (FFmpeg libraries, bundled in the wheel).

Why full re-encode rather than a stream copy: a copy would leave the original
encoder's in-band data intact, and for the common phone-video case the payload
we care about (GPS, capture time, device model) lives in container atoms that a
remux may faithfully carry across. Decoding to raw frames and encoding fresh
means nothing survives that we did not explicitly write.

Three layers get cleaned:
  1. Container metadata  - never copied; the output container starts empty.
  2. Muxer-injected tags  - suppressed with `-fflags +bitexact`, which stops
     FFmpeg writing its own version string into the file.
  3. In-band encoder data - x264 and x265 write a version banner plus their full
     option list into an SEI NAL inside the video bitstream. That survives
     everything above, so it is removed with the `filter_units` bitstream
     filter before muxing.

Rotation is read before stripping and applied to the pixels, otherwise portrait
phone video plays back sideways once the display matrix is gone.
"""
from __future__ import annotations

import os
from fractions import Fraction

import av
import av.stream
import numpy as np

# A fine, highly divisible timebase. Source timestamps are rescaled into it so
# variable-frame-rate recordings keep their pacing instead of being forced to a
# constant rate and drifting out of sync with the audio.
TIMEBASE = Fraction(1, 90000)

VIDEO_ENCODERS = {
    # name:      (encoder, container, audio codec, crf floor, crf span)
    "h264": ("libx264", "mp4", "aac", 40, 24),
    "h265": ("libx265", "mp4", "aac", 44, 26),
    "vp9": ("libvpx-vp9", "webm", "libopus", 50, 26),
    "av1": ("libsvtav1", "mp4", "aac", 55, 30),
}

AUDIO_ENCODERS = {
    "opus": ("libopus", ".opus", "ogg"),
    "aac": ("aac", ".m4a", "ipod"),
    "mp3": ("libmp3lame", ".mp3", "mp3"),
    "flac": ("flac", ".flac", "flac"),
}

SEI_FILTER = {
    "libx264": "filter_units=remove_types=6",       # H.264 SEI
    "libx265": "filter_units=remove_types=39|40",   # HEVC prefix/suffix SEI
}

# Muxer options that stop a container writing its own writer tag.
MUX_OPTIONS = {
    "mp4": {"fflags": "+bitexact", "movflags": "+faststart"},
    "webm": {"fflags": "+bitexact"},
    "ogg": {"fflags": "+bitexact"},
    "ipod": {"fflags": "+bitexact", "movflags": "+faststart"},
    "flac": {"fflags": "+bitexact"},
    # The MP3 muxer writes an ID3v2 tag naming FFmpeg. Turning ID3 off removes it.
    "mp3": {"fflags": "+bitexact", "id3v2_version": "0", "write_id3v1": "0"},
}


def _annexb_nals(buf: bytes):
    """Split an Annex-B buffer into (start_code, payload) pairs."""
    marks, i, n = [], 0, len(buf)
    while i < n - 3:
        if buf[i] == 0 and buf[i + 1] == 0:
            if buf[i + 2] == 1:
                marks.append((i, 3)); i += 3; continue
            if buf[i + 2] == 0 and i + 3 < n and buf[i + 3] == 1:
                marks.append((i, 4)); i += 4; continue
        i += 1
    out = []
    for k, (start, size) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else n
        out.append((buf[start:start + size], buf[start + size:end]))
    return out


def strip_extradata_sei(extradata: bytes, encoder: str) -> bytes:
    """Remove the encoder's version banner from the codec parameter sets.

    x265 puts its build string, CPU features and full option list in an SEI NAL
    that travels inside the stream's extradata, where the bitstream filter that
    cleans the frame packets cannot reach it. This is that same removal, applied
    to the parameter sets, and only when they are in Annex-B form -- the packed
    avcC/hvcC form has no start codes and is left untouched.
    """
    if not extradata or not extradata.startswith(b"\x00\x00"):
        return extradata
    hevc = encoder == "libx265"
    drop = {39, 40} if hevc else {6}

    def nal_type(nal: bytes) -> int:
        return ((nal[0] >> 1) & 0x3F) if hevc else (nal[0] & 0x1F)

    parts = _annexb_nals(extradata)
    if not parts:
        return extradata
    kept = [sc + nal for sc, nal in parts if nal and nal_type(nal) not in drop]
    return b"".join(kept) if kept else extradata


def available_video_encoders() -> list[str]:
    out = []
    for key, (enc, *_rest) in VIDEO_ENCODERS.items():
        try:
            av.codec.Codec(enc, "w")
            out.append(key)
        except Exception:
            pass
    return out


def available_audio_encoders() -> list[str]:
    out = []
    for key, (enc, *_rest) in AUDIO_ENCODERS.items():
        try:
            av.codec.Codec(enc, "w")
            out.append(key)
        except Exception:
            pass
    return out


def _crf(quality: int, floor: int, span: int) -> int:
    """Quality 0-100 -> CRF. Higher quality means a lower CRF number."""
    return int(round(floor - (max(0, min(100, quality)) / 100.0) * span))


def _rotation(stream) -> int:
    """Rotation in degrees, from the display matrix or the legacy tag."""
    try:
        rot = stream.metadata.get("rotate")
        if rot:
            return int(float(rot)) % 360
    except Exception:
        pass
    try:
        for sd in stream.side_data:
            if "DISPLAYMATRIX" in str(sd.type):
                return int(round(float(sd.rotation))) % 360
    except Exception:
        pass
    return 0


def _even(n: int) -> int:
    return n if n % 2 == 0 else n - 1


def _rotate_frame(frame, degrees: int):
    arr = frame.to_ndarray(format="rgb24")
    arr = np.rot90(arr, k=(-degrees // 90) % 4)
    return av.VideoFrame.from_ndarray(np.ascontiguousarray(arr), format="rgb24")


def _pick_streams(container):
    video = None
    audio = None
    for s in container.streams:
        if s.type == "video" and video is None:
            if s.disposition & av.stream.Disposition.attached_pic:
                continue  # cover art -- artwork, not a video track; dropped
            video = s
        elif s.type == "audio" and audio is None:
            audio = s
    return video, audio


def process_video(src: str, out_dir: str, opts: dict, log, progress) -> str:
    quality = int(opts.get("quality", 70))
    codec_key = opts.get("video_codec", "h264")
    preset = opts.get("preset", "medium")
    max_height = int(opts.get("max_height", 0) or 0)
    audio_kbps = int(opts.get("video_audio_kbps", 128))

    if codec_key not in VIDEO_ENCODERS:
        codec_key = "h264"
    enc_name, ext, aenc_name, floor, span = VIDEO_ENCODERS[codec_key]
    crf = _crf(quality, floor, span)

    inp = av.open(src)
    iv, ia = _pick_streams(inp)
    if iv is None:
        inp.close()
        raise ValueError("no video track found")

    tags = dict(inp.metadata)
    if tags:
        log(f"container tags found: {', '.join(sorted(tags))}")
    for s in inp.streams:
        st = dict(s.metadata)
        if st:
            log(f"{s.type} stream tags: {', '.join(sorted(st))}")
    if not tags:
        log("no container-level tags")

    rotation = _rotation(iv)
    src_w = iv.codec_context.width
    src_h = iv.codec_context.height
    if rotation in (90, 270):
        disp_w, disp_h = src_h, src_w
    else:
        disp_w, disp_h = src_w, src_h
    if rotation:
        log(f"display rotation {rotation} deg -- baking into pixels before strip")

    scale = 1.0
    if max_height and disp_h > max_height:
        scale = max_height / float(disp_h)
    out_w = _even(int(round(disp_w * scale)))
    out_h = _even(int(round(disp_h * scale)))
    if scale != 1.0:
        log(f"scaling {disp_w}x{disp_h} -> {out_w}x{out_h}")

    fps = iv.average_rate or iv.guessed_rate or Fraction(30, 1)
    total = iv.frames or 0
    if not total and inp.duration:
        total = int(float(inp.duration / av.time_base) * float(fps))
    total = max(total, 1)

    dst = os.path.join(out_dir, "out." + ext)
    # +bitexact stops the muxer stamping its own version into the file.
    out = av.open(dst, "w", options=MUX_OPTIONS.get(ext, {"fflags": "+bitexact"}))

    enc_opts = {"crf": str(crf)}
    if enc_name in ("libx264", "libx265"):
        enc_opts["preset"] = preset
    elif enc_name == "libsvtav1":
        enc_opts["preset"] = {"veryfast": "10", "fast": "8", "medium": "6",
                              "slow": "4"}.get(preset, "6")
    elif enc_name == "libvpx-vp9":
        enc_opts.update({"b": "0", "row-mt": "1", "deadline": "good"})
    if enc_name == "libx265":
        enc_opts["x265-params"] = "log-level=none"   # x265 otherwise spams stderr

    ov = out.add_stream(enc_name, rate=fps, options=enc_opts)
    ov.width, ov.height = out_w, out_h
    ov.pix_fmt = "yuv420p"
    ov.time_base = TIMEBASE
    ov.codec_context.thread_count = 0
    # The MP4 muxer always writes a handler name. Left alone it says
    # "VideoHandler", which identifies the writer; a space says nothing.
    ov.metadata["handler_name"] = " "
    log(f"video: {enc_name} crf {crf} preset {preset}")

    bsf = None
    if enc_name in SEI_FILTER:
        try:
            bsf = av.BitStreamFilterContext(SEI_FILTER[enc_name], in_stream=ov)
            log("bitstream filter armed: encoder SEI banner will be removed")
        except Exception as exc:
            log(f"bitstream filter unavailable ({exc}); SEI banner will remain")

    oa = None
    resampler = None
    if ia is not None:
        channels = getattr(ia.codec_context, "channels", 2) or 2
        layout = "stereo" if channels > 1 else "mono"
        rate = 48000
        oa = out.add_stream(aenc_name, rate=rate)
        oa.bit_rate = audio_kbps * 1000
        oa.layout = layout
        oa.metadata["handler_name"] = " "
        resampler = av.AudioResampler(format="s16", layout=layout, rate=rate)
        log(f"audio: {aenc_name} {audio_kbps}k {layout}")
    else:
        log("no audio track")

    done = 0
    last_pts = -1
    last_pct = 0

    # The parameter sets can only be edited before the container header is
    # written, and the header goes out on the first mux of *either* stream. So
    # nothing is muxed until the video encoder has opened and its banner has
    # been cut out. In practice that holds back a handful of packets.
    gate = {"open": False, "pending": []}

    def unlock() -> bool:
        if gate["open"]:
            return True
        try:
            ex = bytes(ov.codec_context.extradata or b"")
        except Exception:
            ex = b""
        if not ex:
            return False              # encoder not open yet, keep holding
        try:
            clean = strip_extradata_sei(ex, enc_name)
            if clean != ex:
                ov.codec_context.extradata = clean
                log(f"encoder banner cut from parameter sets "
                    f"({len(ex)} -> {len(clean)} bytes)")
        except Exception as exc:
            log(f"could not edit parameter sets ({exc})")
        gate["open"] = True
        return True

    def emit(packet, is_video: bool) -> None:
        if not unlock():
            gate["pending"].append((packet, is_video))
            return
        if gate["pending"]:
            for held, held_video in gate["pending"]:
                _mux(out, bsf if held_video else None, held)
            gate["pending"].clear()
        _mux(out, bsf if is_video else None, packet)

    def drain() -> None:
        """Last resort: release anything still held, e.g. a video-free input."""
        for held, held_video in gate["pending"]:
            _mux(out, bsf if held_video else None, held)
        gate["pending"].clear()

    try:
        streams = [s for s in (iv, ia) if s is not None]
        for packet in inp.demux(streams):
            if packet.dts is None:
                continue
            for frame in packet.decode():
                if packet.stream is iv:
                    if rotation:
                        frame = _rotate_frame(frame, rotation)
                    if (frame.width, frame.height) != (out_w, out_h):
                        frame = frame.reformat(width=out_w, height=out_h,
                                               format="yuv420p")
                    t = frame.time
                    pts = int(round(t / TIMEBASE)) if t is not None else last_pts + 1
                    if pts <= last_pts:
                        pts = last_pts + 1
                    last_pts = pts
                    frame.pts = pts
                    frame.time_base = TIMEBASE
                    for pkt in ov.encode(frame):
                        emit(pkt, True)
                    done += 1
                    pct = 5 + int(90 * min(done / total, 1.0))
                    if pct != last_pct:
                        last_pct = pct
                        progress(pct)
                elif oa is not None:
                    for rframe in resampler.resample(frame):
                        for pkt in oa.encode(rframe):
                            emit(pkt, False)

        for pkt in ov.encode():
            emit(pkt, True)
        drain()
        if bsf is not None:
            for pkt in (bsf.flush() or []):
                out.mux(pkt)
        if oa is not None:
            for rframe in (resampler.resample(None) or []):
                for pkt in oa.encode(rframe):
                    emit(pkt, False)
            for pkt in oa.encode():
                emit(pkt, False)
        drain()
    finally:
        out.close()
        inp.close()

    log(f"{done} frames re-encoded from scratch")
    progress(98)
    return dst


def _mux(out, bsf, packet):
    if bsf is None:
        out.mux(packet)
        return
    for filtered in (bsf.filter(packet) or []):
        out.mux(filtered)


def process_audio(src: str, out_dir: str, opts: dict, log, progress) -> str:
    codec_key = opts.get("audio_codec", "opus")
    kbps = int(opts.get("audio_kbps", 128))
    if codec_key not in AUDIO_ENCODERS:
        codec_key = "opus"
    enc_name, ext, fmt = AUDIO_ENCODERS[codec_key]

    inp = av.open(src)
    ia = next((s for s in inp.streams if s.type == "audio"), None)
    if ia is None:
        inp.close()
        raise ValueError("no audio track found")

    tags = dict(inp.metadata) | dict(ia.metadata)
    if tags:
        log(f"tags found: {', '.join(sorted(tags))}")
    else:
        log("no tags in container")
    art = [s for s in inp.streams
           if s.type == "video" and (s.disposition & av.stream.Disposition.attached_pic)]
    if art:
        log(f"{len(art)} embedded cover image(s) dropped -- artwork can carry its own EXIF")

    channels = getattr(ia.codec_context, "channels", 2) or 2
    layout = "stereo" if channels > 1 else "mono"
    src_rate = ia.codec_context.sample_rate or 48000
    rate = 48000 if enc_name == "libopus" else min(src_rate, 48000)

    dst = os.path.join(out_dir, "out" + ext)
    out = av.open(dst, "w", format=fmt,
                  options=MUX_OPTIONS.get(fmt, {"fflags": "+bitexact"}))
    oa = out.add_stream(enc_name, rate=rate)
    oa.layout = layout
    oa.metadata["handler_name"] = " "
    if enc_name == "flac":
        log(f"audio: flac lossless {layout} @ {rate} Hz")
    else:
        oa.bit_rate = kbps * 1000
        log(f"audio: {enc_name} {kbps}k {layout} @ {rate} Hz")

    fmt_name = "s16"
    if enc_name == "flac":
        fmt_name = "s16"
    resampler = av.AudioResampler(format=fmt_name, layout=layout, rate=rate)

    duration = float(inp.duration / av.time_base) if inp.duration else 0.0
    last_pct = 0
    try:
        for frame in inp.decode(ia):
            for rframe in resampler.resample(frame):
                for pkt in oa.encode(rframe):
                    out.mux(pkt)
            if duration and frame.time is not None:
                pct = 5 + int(90 * min(frame.time / duration, 1.0))
                if pct != last_pct:
                    last_pct = pct
                    progress(pct)
        for rframe in (resampler.resample(None) or []):
            for pkt in oa.encode(rframe):
                out.mux(pkt)
        for pkt in oa.encode():
            out.mux(pkt)
    finally:
        out.close()
        inp.close()

    log("re-encoded from decoded samples; no tag block written")
    progress(98)
    return dst
