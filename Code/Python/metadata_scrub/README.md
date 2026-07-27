# scrub

A local web app that **shows you** what is hiding inside your images, audio,
video and PDFs, strips it, and recompresses them. PDFs can also be locked with a
generated password.

Work happens in two phases. Uploading only *inspects*: every file is read and
what is found in it is listed — GPS coordinates as real latitude and longitude,
device model, author name, embedded JavaScript. Nothing is modified until you
look at that and press the button.

Everything runs on the machine you start it on. No CDN, no web fonts, no
analytics, no network calls during processing. The app binds to `127.0.0.1` by
default and a Content-Security-Policy header blocks outbound requests from the
page.

## Setup

```bash
./run.sh
```

That creates a virtual environment, installs everything and starts the server on
<http://127.0.0.1:5000>. If the script will not execute, its permission bit was
lost in transit — use `bash run.sh`, or `chmod +x run.sh` once.

Doing it by hand works too:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

### Two questions on startup

Before the server binds, it asks:

```
  Maximum upload size, in MB? [2048]
  Keep uploaded files for how many minutes? [30]
```

Answer `0` to the second and nothing is ever deleted automatically — files stay
until you press **delete from server now** or remove the temp directory. The
prompts are skipped when there is no terminal attached (a service manager, a
pipe, `--no-prompt`), in which case `SCRUB_MAX_MB` and `SCRUB_TTL` decide.

There is nothing else to install. **No ffmpeg, no Ghostscript, no exiftool.**
Every dependency ships a binary wheel:

| Job | Library | What the wheel contains |
| --- | --- | --- |
| Audio, video | `av` (PyAV) | FFmpeg, built with libx264, libx265, SVT-AV1, libvpx-vp9, libopus, libmp3lame, AAC and FLAC |
| Images | `Pillow`, `pillow-heif` | JPEG, PNG, WebP, AVIF, GIF, TIFF, plus HEIC/HEIF for iPhone photos |
| PDF | `pikepdf` | QPDF: structure editing, stream compression, AES-256 |

The app checks at startup which encoders the installed wheel actually has and
only offers those, so a slimmer build degrades instead of erroring.

### Settings

All optional, all environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `SCRUB_HOST` | `127.0.0.1` | Set to `0.0.0.0` to expose on the network — read the warning below first |
| `SCRUB_PORT` | `5000` | |
| `SCRUB_MAX_MB` | `2048` | Rejected above this, per upload. Overridden by the startup prompt |
| `SCRUB_MAX_FILES` | `40` | Files per run |
| `SCRUB_MAX_JOBS` | `8` | Live jobs before new uploads get a 429 |
| `SCRUB_WORKERS` | `2` | Parallel encodes. Encoder threads are divided between them |
| `SCRUB_TTL` | `1800` | Seconds before results are deleted. `0` means never. Overridden by the startup prompt |
| `SCRUB_PDF_MAX_PAGES` | `5000` | Pages scanned for images. Metadata removal always covers every page |

## Inspecting

The report is grouped by what the data reveals rather than by how technically
interesting it is:

| | |
| --- | --- |
| **high** | identifies a person or a place — GPS, names, serial numbers, comments |
| **active** | executes or carries a payload — JavaScript, auto-run actions, attachments |
| **medium** | identifies equipment or timing — device model, software, timestamps |
| **low** | technical residue with no personal content — density, profiles, handler names |

GPS is decoded out of the EXIF rationals into decimal degrees you can paste
into a map, because "GPSInfo: 6 fields" tells you nothing and
`-23.55, -46.633333` tells you everything.

## Never larger than it started

Re-encoding is how you make a file smaller, but it is not the only way to make
one clean, and sometimes it is the wrong one. A PNG already squeezed by a better
compressor, or a JPEG already below the quality being asked for, comes back
*bigger* from a re-encode — and for a lossy format, worse as well.

So when the output format matches the input and the pixels were not resized,
both routes are run and the smaller one wins:

- **re-encode** — full strip, new compression settings
- **lossless strip** — the container is rebuilt from its critical chunks only
  and the pixel data is copied byte for byte. PNG keeps `IHDR`/`PLTE`/`tRNS`/
  `IDAT` and the APNG animation chunks; JPEG keeps everything but `APP1`–`APP15`
  and `COM`; GIF drops comment and application blocks but keeps graphic control,
  so animation timing survives.

The lossless route can only ever delete, so it cannot grow a file. Indexed
images keep their palette *and* their transparent index, because both are the
picture rather than a note about it.

Audio and video reach the same guarantee a different way: the streams are copied
verbatim into a fresh container with no metadata, with the in-band encoder
banner filtered out on the way through. That is what `lossless` means for them -
decoding an encoded bitstream only to encode it again cannot improve on it, it
can only cost quality, time and usually size. It is also the fallback whenever a
re-encode comes back larger than the input, which happens when a file was
already encoded more efficiently than the level being asked for.

The one case where a flat 0% is accurate but useless is a photograph stored as
PNG. That gets called out in the log with what a format change would actually
save, rather than being reported as a job well done.

## Quality levels

There is one decision: how good the result should look. Everything else follows
from it.

| level | what it means |
| --- | --- |
| `lossless` | Nothing is re-encoded. Metadata comes off; pixels and samples stay byte for byte what they were. |
| `imperceptible` | Compressed to just before the point you could tell. |
| `high` | A difference exists, but you would have to look for it side by side. |
| `balanced` | Clearly smaller, still good to look at. The default. |
| `small` | Visible softening on detailed images. |
| `tiny` | Plainly degraded. For when it simply has to fit. |

### Why not just a quality slider

Because an encoder quality number does not mean the same thing twice. Measured
against the originals, JPEG quality 82 produces:

| content | structural similarity at q82 |
| --- | --- |
| photograph | **0.75** - visibly damaged |
| screenshot | 0.996 - almost perfect |
| icon | 0.973 |

One number, three completely different outcomes. So the number is not passed
through to the encoder. The level sets a similarity floor instead, and the
encoder setting is *searched for*: candidates are encoded, compared against the
original with SSIM, and the search bisects a ladder running from heavily
compressed to barely compressed for the leftmost setting that still clears the
floor. Four or five encodes, and the answer is the most compression that
particular picture can take at that quality.

The ladder puts the 4:2:0 to 4:4:4 chroma step near the top on purpose, so
similarity never decreases along it and the bisection stays valid. A noisy
photograph that cannot afford chroma subsampling gets found out and given 4:4:4;
a screenshot that can afford it does not.

Video and audio work differently because they already have the right mechanism.
CRF *is* a perceptual quality target - it holds quality steady and lets the
bitrate move, which is exactly the goal. Levels map to the equivalent CRF per
encoder, tuned so a level looks the same whether x264, x265, VP9 or AV1 produces
it. Audio bitrates are per-codec for the same reason: Opus reaches transparency
far lower than MP3 does, and one shared number would either waste space or
damage the sound depending on which codec was picked.

### Analysis is not downsampled

Comparison runs at up to 2 megapixels, and that is the slow part - roughly a
second or two per image. Halving it was tried: at 1 MP the search chose a 35 KB
file where the honest answer was 273 KB, because downsampling smooths away
exactly the artefacts the measurement exists to catch. Accuracy won.

## What gets removed

### Images

The hard part is that Pillow carries `im.info` — EXIF, GPS, XMP, IPTC, embedded
thumbnails, ICC profiles, PNG text chunks — straight through a normal open and
save. Saving "without metadata" does not remove it.

So the image is rebuilt from its raw pixel buffer. Nothing ancillary survives,
because nothing ancillary is copied. The new file is then written with the
metadata parameters explicitly blanked as a second line of defence.

Two things are read *before* the strip, because deleting them blindly damages
the picture instead of protecting anyone:

- **Orientation** is baked into the pixels first. Otherwise every phone photo
  comes out sideways once the EXIF tag describing the rotation is gone.
- **Colour profiles** are converted to sRGB first, then discarded. Otherwise
  wide-gamut photos come out visibly wrong.

### Audio and video

Files are fully decoded and re-encoded rather than remuxed. A remux would leave
the original encoder's in-band data intact, and container atoms holding capture
time, GPS and device model can survive a copy. Decoding to raw frames and
encoding fresh means nothing survives that was not deliberately written.

Three separate layers are cleaned:

1. **Container and stream tags** — never copied. The output container starts
   empty. The MP4 handler name, normally `VideoHandler`, is overwritten.
2. **Muxer-injected tags** — suppressed with `-fflags +bitexact`, which stops
   FFmpeg stamping its own version string into the output.
3. **In-band encoder banners** — x264 and x265 write their build string, CPU
   features and complete option list into an SEI NAL inside the video
   bitstream. That survives everything above. It is removed from frame packets
   with the `filter_units` bitstream filter, and — for H.265, where it also
   sits in the stream's parameter sets, out of the filter's reach — cut out of
   the extradata directly, before the container header is written.

Rotation is read from the display matrix and applied to the pixels before the
matrix is deleted, so portrait video does not end up sideways. Embedded cover
art is dropped, since artwork carries its own EXIF.

### PDF

A PDF hides identifying data in more places than the properties dialog shows.
All of these are removed:

- the DocInfo dictionary (Author, Producer, Creator, CreationDate)
- the XMP packet at the document root, which often disagrees with DocInfo and
  is the copy most "remove properties" tools miss
- per-page XMP, `/PieceInfo` and `/LastModified`, where editors park private
  working state — Illustrator and InDesign both do this
- embedded JavaScript, `/OpenAction` scripts and `/AA` action dictionaries
- file attachments, which travel invisibly inside the document

Compression is a separate pass over the embedded images, since in almost every
real document the images are the file. Bilevel scans are skipped: they are
CCITT or JBIG2, and JPEG would both wreck the text edges and make the file
bigger. Any image that would not get smaller is left alone.

When no password is set the file is saved with a deterministic ID, so two runs
of the same input produce the same bytes rather than a random identifier that
could correlate copies.

## Passwords

Generated from `secrets.choice`, the system CSPRNG. Length is adjustable from 12
to 64 characters and the entropy in bits is shown. Ambiguous characters
(`Il1O0S5B8` and friends) are excluded by default so the password can be read
aloud or typed from a screen.

Encryption is AES-256, revision 6. The owner password is randomised separately
from the one you set, so nobody holding only the open password can lift the
permission flags.

**The password is displayed once and never written to disk.** An AES-256 PDF
cannot be recovered without it.

## Honest limitations

- **MP3 keeps two generic encoder strings**, `Lavf` in the Xing header and
  `LAME3.100` inside the bitstream. Neither can be removed without breaking the
  format. **WebM keeps `Lavf`** as its writing application; the Matroska muxer
  hardcodes it. These are constants present in every file those encoders
  produce and say nothing about you — but if encoder fingerprinting matters,
  Opus, AAC, FLAC, H.264, H.265 and AV1 all verify completely clean.
- **Deleted means unlinked.** Files are removed after the TTL and the upload is
  deleted the moment processing ends, but on an SSD or a copy-on-write
  filesystem that does not guarantee the blocks are unrecoverable. Overwriting
  would be theatre. If that matters, run this on an encrypted volume.
- **Images inside nested PDF form XObjects** are not reached by the compression
  pass. Metadata removal is unaffected; only the size saving is.
- **Multichannel audio survives into Opus, AAC and FLAC**, but MP3 cannot carry
  it, so a 5.1 track folds to stereo. The log says when that happens rather than
  doing it quietly.
- **The development server is what `python app.py` starts.** For anything
  beyond localhost use a real WSGI server, put it behind TLS, and think hard
  about whether you want other people's files on your disk.
- **Converting to PNG from a lossy source will usually be larger.** That is
  lossless compression doing its job. It only happens when you ask for PNG
  explicitly; keeping the original format never grows a file.

## Layout

```
app.py              Flask routes, config, security headers
jobs.py             job registry, thread pool, progress, temp file lifecycle
scrub/detect.py     content-based file classification
scrub/inspector.py  read-only metadata reporting
scrub/images.py     Pillow: strip and recompress
scrub/lossless.py   container rewriting that never touches pixel data
scrub/similarity.py SSIM, used to decide how hard a file can be compressed
scrub/media.py      PyAV: transcode, strip, SEI removal
scrub/pdfs.py       pikepdf: strip, compress, encrypt, generate passwords
templates/, static/ the page
```

Work runs in a thread pool rather than processes because PyAV, Pillow and zlib
all release the GIL in C, so encodes genuinely run in parallel while progress
state stays trivial to share.

Each job owns one directory under a single temp root. Nothing is written
elsewhere, no path is built from user input, and a reaper thread deletes each
job directory once it passes its TTL. Encoder threads are divided by the worker
count, so two workers do not each try to claim every core and then fight over
them. The results archive is built on disk rather than in memory, because
holding a batch of finished video in RAM to zip it is how a local tool runs a
machine out of memory.
