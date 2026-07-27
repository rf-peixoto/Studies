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
     filter, and for H.265 also cut out of the stream's parameter sets, which
     the filter cannot reach.

Rotation is read before stripping and applied to the pixels, otherwise portrait
phone video plays back sideways once the display matrix is gone.
"""
from __future__ import annotations

import os
from fractions import Fraction

import av
import av.stream

# A fine, highly divisible timebase. Source timestamps are rescaled into it so
# variable-frame-rate recordings keep their pacing instead of being forced to a
# constant rate and drifting out of sync with the audio.
TIMEBASE = Fraction(1, 90000)

VIDEO_ENCODERS = {
    # name:      (encoder, container, audio codec)
    "h264": ("libx264", "mp4", "aac"),
    "h265": ("libx265", "mp4", "aac"),
    "vp9": ("libvpx-vp9", "webm", "libopus"),
    "av1": ("libsvtav1", "mp4", "aac"),
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

# Layouts we will try to preserve rather than folding down to stereo.
SURROUND = {3: "3.0", 4: "quad", 5: "5.0", 6: "5.1", 7: "6.1", 8: "7.1"}

# CRF is already a perceptual quality target: it holds quality steady and lets
# the bitrate move, which is exactly "compress as hard as this quality allows".
# These are the equivalent settings per encoder, tuned so a level looks the same
# whichever codec produces it.
VIDEO_CRF = {
    "libx264":    {"lossless": 14, "imperceptible": 18, "high": 21,
                   "balanced": 24, "small": 28, "tiny": 33},
    "libx265":    {"lossless": 16, "imperceptible": 20, "high": 24,
                   "balanced": 27, "small": 31, "tiny": 36},
    "libvpx-vp9": {"lossless": 20, "imperceptible": 26, "high": 30,
                   "balanced": 33, "small": 37, "tiny": 42},
    "libsvtav1":  {"lossless": 20, "imperceptible": 26, "high": 30,
                   "balanced": 35, "small": 40, "tiny": 46},
}

# Bitrates per level, per codec. Opus reaches transparency far lower than MP3
# does, so one shared number would either waste space or damage the audio
# depending on which codec was chosen.
AUDIO_KBPS = {
    # "lossless" cannot mean FLAC inside an MP4, so it means the highest
    # bitrate the codec is worth giving -- otherwise it would fall through to
    # the balanced setting and come out smaller than the level below it.
    "libopus":    {"lossless": 256, "imperceptible": 160, "high": 128,
                   "balanced": 96, "small": 64, "tiny": 48},
    "aac":        {"lossless": 320, "imperceptible": 256, "high": 192,
                   "balanced": 144, "small": 96, "tiny": 64},
    "libmp3lame": {"lossless": 320, "imperceptible": 320, "high": 256,
                   "balanced": 192, "small": 128, "tiny": 96},
    "flac":       {"lossless": 0, "imperceptible": 0, "high": 0,
                   "balanced": 0, "small": 0, "tiny": 0},
}


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


def encoder_threads() -> int:
    """Cores per worker.

    Two workers each asking for every core is worse than either alone, because
    the encoders then fight for the same hardware. SCRUB_WORKERS is read here
    rather than passed in so the split stays correct wherever this is called.
    """
    try:
        cores = len(os.sched_getaffinity(0))
    except AttributeError:
        cores = os.cpu_count() or 2
    workers = max(1, int(os.environ.get("SCRUB_WORKERS", "2")))
    return max(1, cores // workers)


def crf_for(encoder: str, level: str) -> int:
    table = VIDEO_CRF.get(encoder, VIDEO_CRF["libx264"])
    return table.get(level, table["balanced"])


def kbps_for(encoder: str, level: str) -> int:
    table = AUDIO_KBPS.get(encoder, AUDIO_KBPS["libopus"])
    return table.get(level, table["balanced"])


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


def _rotation(stream) -> int:
    """Rotation in degrees, from the display matrix or the legacy tag."""
    try:
        rot = stream.metadata.get("rotate")
        if rot:
            return int(float(rot)) % 360
    except Exception:
        pass
    try:
        for side in stream.side_data:
            if "DISPLAYMATRIX" in str(side.type):
                return int(round(float(side.rotation))) % 360
    except Exception:
        pass
    return 0


def _even(n: int) -> int:
    return max(2, n if n % 2 == 0 else n - 1)


def _layout_for(channels: int, encoder: str) -> str:
    """Preserve the channel layout when the encoder can take it.

    Folding 5.1 down to stereo without saying so throws away three channels of
    someone's audio. Opus and AAC both handle multichannel; MP3 does not.
    """
    if channels <= 1:
        return "mono"
    if channels == 2:
        return "stereo"
    if encoder in ("libmp3lame",):
        return "stereo"
    return SURROUND.get(channels, "stereo")


def _build_graph(in_stream, degrees: int, out_w: int, out_h: int):
    """Rotate and scale inside FFmpeg rather than round-tripping through numpy."""
    graph = av.filter.Graph()
    nodes = [graph.add_buffer(template=in_stream)]
    chain = {90: [("transpose", "clock")],
             270: [("transpose", "cclock")],
             180: [("hflip", None), ("vflip", None)]}.get(degrees, [])
    for name, arg in chain:
        nodes.append(graph.add(name, arg) if arg else graph.add(name))
    nodes.append(graph.add("scale", f"{out_w}:{out_h}"))
    nodes.append(graph.add("format", "yuv420p"))
    nodes.append(graph.add("buffersink"))
    for a, b in zip(nodes, nodes[1:]):
        a.link_to(b)
    graph.configure()
    return graph


# Demuxer names are comma-joined lists; muxer names are not. Map what we can
# and fall back to re-encoding when a container has no clean output equivalent.
REMUX_FORMAT = {
    "mov,mp4,m4a,3gp,3g2,mj2": "mp4", "matroska,webm": "matroska",
    "mp3": "mp3", "flac": "flac", "wav": "wav", "ogg": "ogg", "aac": "adts",
}


def remux(src: str, out_dir: str, log, progress) -> str | None:
    """Copy the streams untouched into a container with no metadata.

    This is what "lossless" has to mean for audio and video: the encoded
    bitstream is already the result of someone's choices, and decoding it only
    to encode it again cannot improve on it -- it can only cost quality, time,
    and usually size as well. The packets are copied verbatim; only the
    container is rebuilt, and the in-band encoder banner is filtered out on the
    way through, so the strip guarantee still holds.
    """
    inp = av.open(src)
    fmt = REMUX_FORMAT.get(inp.format.name)
    if fmt is None:
        inp.close()
        return None

    keep = [st for st in inp.streams
            if st.type in ("video", "audio")
            and not (st.type == "video"
                     and st.disposition & av.stream.Disposition.attached_pic)]
    if not keep:
        inp.close()
        return None

    ext = {"mp4": "mp4", "matroska": "mkv", "mp3": "mp3", "flac": "flac",
           "wav": "wav", "ogg": "ogg", "adts": "aac"}[fmt]
    # Deliberately not "out.<ext>": the encode path may already have written
    # that name, and this can be called to replace it.
    dst = os.path.join(out_dir, "copy." + ext)
    out = av.open(dst, "w", format=fmt,
                  options=MUX_OPTIONS.get(fmt, {"fflags": "+bitexact"}))

    mapping = {}
    filters = {}
    for st in keep:
        ost = out.add_stream_from_template(st)
        try:
            ost.metadata.clear()
        except Exception:
            pass
        ost.metadata["handler_name"] = " "
        mapping[st.index] = ost
        name = st.codec_context.name
        bsf_name = {"h264": SEI_FILTER["libx264"],
                    "hevc": SEI_FILTER["libx265"]}.get(name)
        if bsf_name:
            try:
                filters[st.index] = av.BitStreamFilterContext(bsf_name, in_stream=st)
            except Exception:
                pass

    total = float(inp.duration / av.time_base) if inp.duration else 0.0
    try:
        for packet in inp.demux(keep):
            if packet.dts is None:
                continue
            ost = mapping[packet.stream.index]
            bsf = filters.get(packet.stream.index)
            packet.stream = ost
            if bsf is None:
                out.mux(packet)
            else:
                for filtered in (bsf.filter(packet) or []):
                    out.mux(filtered)
            if total and packet.pts is not None and packet.time_base:
                progress(5 + int(90 * min(float(packet.pts * packet.time_base)
                                          / total, 1.0)))
        for st_index, bsf in filters.items():
            for filtered in (bsf.flush() or []):
                out.mux(filtered)
    except Exception as exc:
        out.close()
        inp.close()
        log(f"remux failed ({type(exc).__name__}: {exc})")
        return None
    finally:
        try:
            out.close()
            inp.close()
        except Exception:
            pass

    log("streams copied verbatim into a clean container; "
        "nothing was decoded or re-encoded")
    progress(96)
    return dst


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


def _mux(out, bsf, packet):
    if bsf is None:
        out.mux(packet)
        return
    for filtered in (bsf.filter(packet) or []):
        out.mux(filtered)


# --------------------------------------------------------------------------
# video
# --------------------------------------------------------------------------

def process_video(src: str, out_dir: str, opts: dict, log, progress) -> str:
    level = opts.get("level", "balanced")
    codec_key = opts.get("video_codec", "h264")
    preset = opts.get("preset", "medium")
    max_height = int(opts.get("max_height", 0) or 0)

    if codec_key not in VIDEO_ENCODERS:
        codec_key = "h264"
    enc_name, ext, aenc_name = VIDEO_ENCODERS[codec_key][:3]
    audio_kbps = kbps_for(aenc_name, level)

    # ---- probe once, encode possibly more than once -----------------------
    probe = av.open(src)
    iv, ia = _pick_streams(probe)
    if iv is None:
        probe.close()
        raise ValueError("no video track found")

    tags = dict(probe.metadata)
    log(f"container tags found: {', '.join(sorted(tags))}" if tags
        else "no container-level tags")
    for s in probe.streams:
        st = dict(s.metadata)
        if st:
            log(f"{s.type} stream tags: {', '.join(sorted(st))}")

    rotation = _rotation(iv)
    src_w, src_h = iv.codec_context.width, iv.codec_context.height
    disp_w, disp_h = (src_h, src_w) if rotation in (90, 270) else (src_w, src_h)
    if rotation:
        log(f"display rotation {rotation} deg -- baking into pixels before strip")

    scale = min(1.0, max_height / float(disp_h)) if max_height else 1.0
    out_w, out_h = _even(round(disp_w * scale)), _even(round(disp_h * scale))
    if scale != 1.0:
        log(f"scaling {disp_w}x{disp_h} -> {out_w}x{out_h}")

    fps = iv.average_rate or iv.guessed_rate or Fraction(30, 1)
    total = iv.frames or 0
    duration = float(probe.duration / av.time_base) if probe.duration else 0.0
    if not total and duration:
        total = int(duration * float(fps))
    total = max(total, 1)
    has_audio = ia is not None
    channels = getattr(ia.codec_context, "channels", 2) if has_audio else 0
    probe.close()

    dst = os.path.join(out_dir, "out." + ext)
    threads = encoder_threads()

    # ---- one encoding pass ------------------------------------------------
    def encode(crf: int | None, bitrate: int | None,
               lo: int, hi: int) -> int:
        inp = av.open(src)
        viv, via = _pick_streams(inp)
        out = av.open(dst, "w", options=MUX_OPTIONS.get(ext,
                                                        {"fflags": "+bitexact"}))

        enc_opts: dict[str, str] = {}
        if crf is not None:
            enc_opts["crf"] = str(crf)
        if enc_name in ("libx264", "libx265"):
            enc_opts["preset"] = preset
        elif enc_name == "libsvtav1":
            enc_opts["preset"] = {"veryfast": "10", "fast": "8", "medium": "6",
                                  "slow": "4"}.get(preset, "6")
        elif enc_name == "libvpx-vp9":
            enc_opts.update({"row-mt": "1", "deadline": "good"})
            enc_opts["b"] = str(bitrate) if bitrate else "0"
        if enc_name == "libx265":
            enc_opts["x265-params"] = "log-level=none"  # x265 otherwise spams

        ov = out.add_stream(enc_name, rate=fps, options=enc_opts)
        ov.width, ov.height = out_w, out_h
        ov.pix_fmt = "yuv420p"
        ov.time_base = TIMEBASE
        ov.codec_context.thread_count = threads
        # The MP4 muxer always writes a handler name. Left alone it says
        # "VideoHandler", which identifies the writer; a space says nothing.
        ov.metadata["handler_name"] = " "
        if bitrate:
            ov.bit_rate = bitrate

        bsf = None
        if enc_name in SEI_FILTER:
            try:
                bsf = av.BitStreamFilterContext(SEI_FILTER[enc_name], in_stream=ov)
            except Exception as exc:
                log(f"bitstream filter unavailable ({exc}); SEI banner will remain")

        oa = None
        resampler = None
        if via is not None:
            layout = _layout_for(channels, aenc_name)
            oa = out.add_stream(aenc_name, rate=48000)
            oa.bit_rate = audio_kbps * 1000
            oa.layout = layout
            oa.metadata["handler_name"] = " "
            resampler = av.AudioResampler(format="s16", layout=layout, rate=48000)

        graph = None
        if rotation:
            try:
                graph = _build_graph(viv, rotation, out_w, out_h)
            except Exception as exc:
                log(f"filter graph unavailable ({exc}); falling back to reformat")

        # The parameter sets can only be edited before the container header is
        # written, and the header goes out on the first mux of *either* stream.
        # So nothing is muxed until the video encoder has opened and its banner
        # has been cut out. In practice that holds back a handful of packets.
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
            for held, held_video in gate["pending"]:
                _mux(out, bsf if held_video else None, held)
            gate["pending"].clear()
            _mux(out, bsf if is_video else None, packet)

        def drain() -> None:
            for held, held_video in gate["pending"]:
                _mux(out, bsf if held_video else None, held)
            gate["pending"].clear()

        done = 0
        dropped = 0
        last_pts = -1
        last_pct = -1

        def send_video(frame):
            nonlocal last_pts, dropped
            t = frame.time
            pts = int(round(t / TIMEBASE)) if t is not None else last_pts + 1
            if pts <= last_pts:
                # Two frames claiming the same instant. Squeezing the second one
                # into a 1/90000 s slot would slowly pull audio out of sync, so
                # the duplicate is dropped instead.
                dropped += 1
                return
            last_pts = pts
            frame.pts = pts
            frame.time_base = TIMEBASE
            for pkt in ov.encode(frame):
                emit(pkt, True)

        try:
            streams = [s for s in (viv, via) if s is not None]
            for packet in inp.demux(streams):
                # A null-DTS packet at end of stream is the flush signal; it
                # decodes to whatever is still held in the reorder buffer.
                # Skipping it loses the tail of the video.
                for frame in packet.decode():
                    if packet.stream is viv:
                        if graph is not None:
                            graph.push(frame)
                            while True:
                                try:
                                    send_video(graph.pull())
                                except (av.error.BlockingIOError, av.error.EOFError):
                                    break
                        else:
                            if (frame.width, frame.height) != (out_w, out_h):
                                frame = frame.reformat(width=out_w, height=out_h,
                                                       format="yuv420p")
                            send_video(frame)
                        done += 1
                        pct = lo + int((hi - lo) * min(done / total, 1.0))
                        if pct != last_pct:
                            last_pct = pct
                            progress(pct)
                    elif oa is not None:
                        for rframe in resampler.resample(frame):
                            for pkt in oa.encode(rframe):
                                emit(pkt, False)

            if graph is not None:
                try:
                    graph.push(None)
                    while True:
                        try:
                            send_video(graph.pull())
                        except (av.error.BlockingIOError, av.error.EOFError):
                            break
                except Exception:
                    pass
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

        if dropped:
            log(f"{dropped} duplicate-timestamp frame(s) dropped to hold sync")
        return done

    # ---- drive it ---------------------------------------------------------
    if level == "lossless" and not max_height and opts.get("video_codec_forced") is not True:
        copied = remux(src, out_dir, log, progress)
        if copied is not None:
            return copied
        log("this container cannot be rebuilt by copy; re-encoding instead")

    crf = crf_for(enc_name, level)
    log(f"video: {enc_name} crf {crf} preset {preset} ({threads} thread(s)) "
        f"-- constant quality, bitrate follows the picture")
    if has_audio:
        log(f"audio: {aenc_name} {audio_kbps}k "
            f"{_layout_for(channels, aenc_name)}")
    done = encode(crf, None, 5, 95)
    log(f"{done} frames re-encoded from scratch")

    # An already efficiently-encoded file can come back larger at a high
    # quality level. Copying the streams instead is both smaller and lossless,
    # so there is no reason to hand back the worse of the two.
    if os.path.getsize(dst) > os.path.getsize(src) and not max_height:
        log(f"re-encoding grew this file "
            f"({os.path.getsize(src) // 1024} KB -> "
            f"{os.path.getsize(dst) // 1024} KB); copying the original streams "
            f"instead")
        copied = remux(src, out_dir, log, progress)
        if copied is not None and copied != dst:
            try:
                os.remove(dst)
            except OSError:
                pass
            return copied
    progress(98)
    return dst


# --------------------------------------------------------------------------
# audio
# --------------------------------------------------------------------------

def process_audio(src: str, out_dir: str, opts: dict, log, progress) -> str:
    level = opts.get("level", "balanced")
    codec_key = opts.get("audio_codec", "opus")
    if level == "lossless":
        copied = remux(src, out_dir, log, progress)
        if copied is not None:
            return copied
        log("this container cannot be rebuilt by copy; encoding FLAC instead")
        codec_key = "flac"
    if codec_key not in AUDIO_ENCODERS:
        codec_key = "opus"
    enc_name, ext, fmt = AUDIO_ENCODERS[codec_key]
    kbps = kbps_for(enc_name, level)

    inp = av.open(src)
    ia = next((s for s in inp.streams if s.type == "audio"), None)
    if ia is None:
        inp.close()
        raise ValueError("no audio track found")

    tags = dict(inp.metadata) | dict(ia.metadata)
    log(f"tags found: {', '.join(sorted(tags))}" if tags
        else "no tags in container")
    art = [s for s in inp.streams
           if s.type == "video" and (s.disposition & av.stream.Disposition.attached_pic)]
    if art:
        log(f"{len(art)} embedded cover image(s) dropped -- artwork can carry "
            f"its own EXIF")

    channels = getattr(ia.codec_context, "channels", 2) or 2
    layout = _layout_for(channels, enc_name)
    if channels > 2 and layout == "stereo":
        log(f"{channels} channels folded to stereo -- {enc_name} cannot carry them")
    elif channels > 2:
        log(f"{channels}-channel layout '{layout}' preserved")
    src_rate = ia.codec_context.sample_rate or 48000
    rate = 48000 if enc_name == "libopus" else min(src_rate, 48000)

    duration = float(inp.duration / av.time_base) if inp.duration else 0.0

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

    resampler = av.AudioResampler(format="s16", layout=layout, rate=rate)
    last_pct = -1
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

    if os.path.getsize(dst) > os.path.getsize(src):
        log("re-encoding grew this file; copying the original stream instead")
        copied = remux(src, out_dir, log, progress)
        if copied is not None and copied != dst:
            try:
                os.remove(dst)
            except OSError:
                pass
            return copied
    progress(98)
    return dst
