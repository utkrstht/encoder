#!/usr/bin/env python3
import argparse, struct, subprocess, json, tempfile, os, sys
from pathlib import Path
import numpy as np
import zstandard as zstd

MAGIC = b"YTF1"

def grid_dimensions(width, height, block_size, gutter):
    cell = block_size + gutter
    cols = width // cell
    rows = height // cell
    return cols, rows

def decode_frames_from_raw_bytes(raw_bytes, width, height, block_size, gutter):
    cols, rows = grid_dimensions(width, height, block_size, gutter)
    frame_size = width * height
    total_frames = len(raw_bytes) // frame_size
    recovered = bytearray()

    stripe_w = max(1, block_size // 8)
    total_stripe_area_w = stripe_w * 8

    for f in range(total_frames):
        offset = f * frame_size
        frame = np.frombuffer(raw_bytes[offset:offset+frame_size], dtype=np.uint8).reshape((height, width))
        for idx in range(cols * rows):
            r = idx // cols
            c = idx % cols
            x0 = c * (block_size + gutter)
            y0 = r * (block_size + gutter)
            sx = x0 + (block_size - total_stripe_area_w) // 2
            byte = 0
            for bit in range(8):
                x_stripe0 = sx + bit * stripe_w
                x_stripe1 = x_stripe0 + stripe_w
                xs0 = max(0, min(width, x_stripe0))
                xs1 = max(0, min(width, x_stripe1))
                ys0 = max(0, min(height, y0 + 1))
                ys1 = max(0, min(height, y0 + block_size - 1))
                if xs1 <= xs0 or ys1 <= ys0:
                    sample_val = 0
                else:
                    sample = frame[ys0:ys1, xs0:xs1]
                    sample_val = int(sample.mean()) if sample.size > 0 else 0
                bitval = 1 if sample_val > 127 else 0
                byte = (byte << 1) | bitval
            recovered.append(byte)
    return bytes(recovered)

def download_youtube(link):
    import yt_dlp
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".webm").name
    opts = {"outtmpl": tmp, "format": "bestvideo"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([link])
    return tmp

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=str, help="Local video file path")
    p.add_argument("--youtube", type=str, help="YouTube video URL")
    p.add_argument("--manifest", type=str, default=None)
    p.add_argument("--outfile", type=str, help="Output file path for recovered payload")
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--block", type=int, default=8)
    p.add_argument("--gutter", type=int, default=1)
    p.add_argument("--fps", type=int, default=60)
    p.add_argument("--compress", action="store_true", help="Use zstd decompression for local files")
    args = p.parse_args()

    if args.youtube:
        infile = download_youtube(args.youtube)
        manifest = {}
        import yt_dlp
        ydl_opts = {"quiet": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(args.youtube, download=False)
            manifest = {"description": info.get("description", "")}
        if args.outfile is None:
            args.outfile = info.get("title", "output.bin")
    elif args.input:
        infile = args.input
        if args.manifest:
            with open(args.manifest) as f:
                manifest = json.load(f)
        else:
            manifest = {}
    else:
        raise SystemExit("Provide either --input or --youtube")

    width = manifest.get("width", args.width)
    height = manifest.get("height", args.height)
    fps = manifest.get("fps", args.fps)

    # fast ffmpeg raw extraction
    ff_cmd = [
        "ffmpeg",
        "-i", infile,
        "-f", "rawvideo",
        "-pix_fmt", "gray",
        "-s", f"{width}x{height}",
        "-r", str(fps),
        "-threads", "0",
        "-"
    ]
    print("Running ffmpeg:", " ".join(ff_cmd))
    proc = subprocess.run(ff_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        print(proc.stderr.decode(errors="ignore"))
        raise SystemExit("ffmpeg extraction failed")
    raw_bytes = proc.stdout
    print(f"Extracted {len(raw_bytes)} raw bytes from video")

    recovered_payload = decode_frames_from_raw_bytes(raw_bytes, width, height, args.block, args.gutter)
    print(f"Recovered payload bytes (including header): {len(recovered_payload)}")

    # parse header
    if recovered_payload.startswith(MAGIC):
        compressed_len = struct.unpack_from("<Q", recovered_payload, 4)[0]
        original_len = struct.unpack_from("<Q", recovered_payload, 12)[0]
        comp_bytes = recovered_payload[20:20+compressed_len]
    elif manifest and "compressed_length" in manifest:
        compressed_len = manifest["compressed_length"]
        original_len = manifest.get("original_length", None)
        comp_bytes = recovered_payload[:compressed_len]
    else:
        raise SystemExit("Cannot determine compressed length: missing header or manifest")

    # decompress if needed
    if args.compress and args.input:
        dctx = zstd.ZstdDecompressor()
        orig = dctx.decompress(comp_bytes)
        if original_len: orig = orig[:original_len]
    else:
        orig = comp_bytes  # no decompression

    if args.outfile:
        Path(args.outfile).write_bytes(orig)
        print("Wrote recovered file:", args.outfile)
    else:
        sys.stdout.buffer.write(orig)

    # cleanup
    if args.youtube:
        os.remove(infile)

if __name__ == "__main__":
    main()
