#!/usr/bin/env python3
"""
Usage:
  python encoder_av1_lossless.py inputfile outdir --width 1920 --height 1080 --block 8 --gutter 1 --fps 60 --outfile encoded.webm [--compress]
"""
import argparse, math, json, subprocess, struct
from pathlib import Path
import numpy as np
import requests, os

try:
    import zstandard as zstd
except ImportError:
    zstd = None

MAGIC = b"YTF1"  # 4 bytes magic to identify header

def grid_dimensions(width, height, block_size, gutter):
    cell = block_size + gutter
    cols = width // cell
    rows = height // cell
    return cols, rows

def render_frame_from_payload(payload_bytes, width, height, block_size, gutter):
    W = width; H = height; B = block_size; G = gutter
    cols, rows = grid_dimensions(W, H, B, G)
    cell = B + G
    img = np.zeros((H, W), dtype=np.uint8)  # grayscale
    max_blocks = cols * rows

    stripe_w = max(1, B // 8)
    total_stripe_area_w = stripe_w * 8

    for idx, b in enumerate(payload_bytes):
        if idx >= max_blocks: break
        r = idx // cols
        c = idx % cols
        x0 = c * cell
        y0 = r * cell
        sx = x0 + (B - total_stripe_area_w) // 2
        for bit in range(8):
            bitval = (b >> (7-bit)) & 1
            color = 255 if bitval else 0
            x_stripe0 = sx + bit * stripe_w
            x_stripe1 = x_stripe0 + stripe_w
            # safe write (clamp)
            x0c = max(0, min(W, x_stripe0))
            x1c = max(0, min(W, x_stripe1))
            y0c = max(0, min(H, y0))
            y1c = max(0, min(H, y0 + B))
            if x1c > x0c and y1c > y0c:
                img[y0c:y1c, x0c:x1c] = color
    return img

def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("outdir")
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--block", type=int, default=8)
    p.add_argument("--gutter", type=int, default=1)
    p.add_argument("--fps", type=int, default=60)
    p.add_argument("--zlevel", type=int, default=10)
    p.add_argument("--outfile", default="encoded.webm")
    p.add_argument("--compress", action="store_true", help="Compress payload with zstd")
    args = p.parse_args()

    inp = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    raw = inp.read_bytes()
    original_length = len(raw)

    # compress only if --compress flag is passed
    if args.compress:
        if zstd is None:
            raise SystemExit("zstandard module not installed, cannot compress")
        cctx = zstd.ZstdCompressor(level=args.zlevel)
        compressed = cctx.compress(raw)
        payload_bytes = compressed
        compressed_length = len(compressed)
    else:
        payload_bytes = raw
        compressed_length = len(payload_bytes)

    # prepend header (MAGIC + compressed_length + original_length)
    header = MAGIC + struct.pack("<Q", compressed_length) + struct.pack("<Q", original_length)
    payload = header + payload_bytes
    payload_len = len(payload)

    cols, rows = grid_dimensions(args.width, args.height, args.block, args.gutter)
    blocks_per_frame = cols * rows
    frames_needed = math.ceil(payload_len / blocks_per_frame)
    frame_size = args.width * args.height

    print(f"input {inp} -> original {original_length} bytes")
    if args.compress:
        print(f"zstd compressed {compressed_length} bytes, header+payload {payload_len} bytes")
    else:
        print(f"No compression, payload {payload_len} bytes")
    print(f"{blocks_per_frame} blocks per frame -> {frames_needed} frames required")

    # ffmpeg AV1 lossless
    out_video = outdir / args.outfile
    ff_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-pix_fmt", "gray",
        "-s", f"{args.width}x{args.height}",
        "-r", str(args.fps),
        "-i", "-",
        "-c:v", "libvpx-vp9",
        "-lossless", "1",
        "-speed", "8",
        "-row-mt", "1",
        "-tile-columns", "2",
        "-tile-rows", "1",
        "-threads", "8",
        str(out_video)
    ]

    print("Starting ffmpeg:", " ".join(ff_cmd))
    proc = subprocess.Popen(ff_cmd, stdin=subprocess.PIPE)

    for f in range(frames_needed):
        start = f * blocks_per_frame
        end = start + blocks_per_frame
        chunk = payload[start:end]
        if len(chunk) < blocks_per_frame:
            chunk = chunk + bytes(blocks_per_frame - len(chunk))
        img = render_frame_from_payload(chunk, args.width, args.height, args.block, args.gutter)
        try:
            proc.stdin.write(img.tobytes())
        except BrokenPipeError:
            proc.stdin.close()
            proc.wait()
            raise RuntimeError("ffmpeg pipe closed early")

    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg returned {rc}")

    manifest = {
        "input_file": inp.name,
        "original_length": original_length,
        "compressed_length": compressed_length if args.compress else None,
        "payload_length": payload_len,
        "frames": frames_needed,
        "width": args.width,
        "height": args.height,
        "frame_size_bytes": frame_size,
        "block_size": args.block,
        "gutter": args.gutter,
        "fps": args.fps,
        "zstd_level": args.zlevel if args.compress else None,
        "video_file": str(out_video.name)
    }
    manifest_path = outdir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print("Wrote manifest:", manifest_path)
    print("Wrote video:", out_video)
    print("Encoding finished.")

    url = "http://localhost:8000/upload"

    title = os.path.basename(inp.name)

    with open("manifest.json", "r") as f:
        description = f.read()

    with open(out_video, "rb") as f:
        files = {"video": (os.path.basename(out_video), f, "video/webm")}
        data = {"title": title, "description": description}

        r = requests.post(url, files=files, data=data)

    print("Response:", r.status_code, r.text)

    if r.status_code == 200:
        video_id = r.json().get("video_id")
        os.remove(out_video)
        print("Video deleted")
        print("Video link: https://youtu.be/"+ video_id)

if __name__ == "__main__":
    main()
