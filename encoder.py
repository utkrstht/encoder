#!/usr/bin/env python3
"""
Options (env args or CLI):
  --width (default 1920)
  --height (default 1080)
  --block (default 8)
  --gutter (default 1)
  --fps (default 60)
  --crf (default 10)
"""
import argparse, math, json, subprocess, os
from pathlib import Path
import numpy as np, cv2

def grid_dimensions(width, height, block_size, gutter):
    cell = block_size + gutter
    cols = width // cell
    rows = height // cell
    return cols, rows

def render_frame_from_payload(frame_index, payload_bytes, width, height, block_size, gutter):
    W = width; H = height; B = block_size; G = gutter
    cols, rows = grid_dimensions(W, H, B, G)
    cell = B + G
    img = np.zeros((H, W, 3), dtype=np.uint8)  # black background
    max_blocks = cols * rows
    for idx, b in enumerate(payload_bytes):
        if idx >= max_blocks: break
        r = idx // cols
        c = idx % cols
        x0 = c * cell
        y0 = r * cell
        stripe_w = max(1, B // 8)
        total_stripe_area_w = stripe_w * 8
        sx = x0 + (B - total_stripe_area_w) // 2
        for bit in range(8):
            bitval = (b >> (7-bit)) & 1
            color = 255 if bitval else 0
            x_stripe0 = sx + bit * stripe_w
            x_stripe1 = x_stripe0 + stripe_w
            img[y0:y0+B, x_stripe0:x_stripe1, :] = color
    # small frame marker (not necessary)
    return img

def encode_file_to_frames(infile, out_dir, width, height, block_size, gutter):
    out_dir = Path(out_dir); frames_dir = out_dir / "frames"; frames_dir.mkdir(parents=True, exist_ok=True)
    data = Path(infile).read_bytes()
    cols, rows = grid_dimensions(width, height, block_size, gutter)
    blocks_per_frame = cols * rows
    frames_needed = math.ceil(len(data) / blocks_per_frame)
    frame_paths = []
    for f in range(frames_needed):
        start = f * blocks_per_frame; end = start + blocks_per_frame
        chunk = data[start:end]
        img = render_frame_from_payload(f, chunk, width, height, block_size, gutter)
        fname = frames_dir / f"frame_{f:06d}.png"
        cv2.imwrite(str(fname), img)
        frame_paths.append(fname)
    return frame_paths, len(data)

def assemble_video_with_ffmpeg(frames_dir, out_video, fps=60, crf=10):
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%06d.png"),
        "-c:v", "libvpx-vp9",
        "-pix_fmt", "yuv420p",
        "-b:v", "0",
        "-crf", str(crf),
        "-g", "300",
        str(out_video)
    ]
    print("Running ffmpeg to assemble video (this may take time):")
    print(" ".join(cmd))
    subprocess.check_call(cmd)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("outdir")
    p.add_argument("--width",type=int,default=1920)
    p.add_argument("--height",type=int,default=1080)
    p.add_argument("--block",type=int,default=8)
    p.add_argument("--gutter",type=int,default=1)
    p.add_argument("--fps",type=int,default=60)
    p.add_argument("--crf",type=int,default=10)
    args = p.parse_args()

    frames, orig_len = encode_file_to_frames(args.input, args.outdir, args.width, args.height, args.block, args.gutter)
    manifest = {
        "input_file": str(args.input),
        "file_length": orig_len,
        "frames": len(frames),
        "width": args.width,
        "height": args.height,
        "block_size": args.block,
        "gutter": args.gutter,
        "fps": args.fps,
        "crf": args.crf
    }
    manifest_path = Path(args.outdir) / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Wrote {len(frames)} frames to {args.outdir}/frames and manifest to {manifest_path}")

    # assemble video
    out_video = Path(args.outdir) / "encoded.webm"
    try:
        assemble_video_with_ffmpeg(Path(args.outdir)/"frames", out_video, fps=args.fps, crf=args.crf)
        print("Video assembled at:", out_video)
    except Exception as e:
        print("ffmpeg assembly failed or ffmpeg not present. Frames are available. Error:", e)

if __name__ == '__main__':
    main()
