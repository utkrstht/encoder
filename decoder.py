import argparse, sys, subprocess, tempfile, shutil
from pathlib import Path
import numpy as np, cv2, json

def grid_dimensions(width, height, block_size, gutter):
    cell = block_size + gutter
    cols = width // cell
    rows = height // cell
    return cols, rows

def extract_frames_from_video(video_path, out_frames_dir, fps=60):
    out_frames_dir = Path(out_frames_dir); out_frames_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", str(video_path), "-r", str(fps), str(out_frames_dir/"frame_%06d.png")]
    print("Running ffmpeg to extract frames:", " ".join(cmd))
    subprocess.check_call(cmd)
    return sorted(out_frames_dir.glob("frame_*.png"))

def decode_frames_to_bytes(frame_paths, width, height, block_size, gutter):
    cols, rows = grid_dimensions(width, height, block_size, gutter)
    cell = block_size + gutter
    recovered = bytearray()
    for fp in frame_paths:
        img = cv2.imread(str(fp))
        if img is None:
            raise RuntimeError(f"Failed to load {fp}")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        B = block_size
        stripe_w = max(1, B // 8)
        total_stripes_w = stripe_w * 8
        for idx in range(cols*rows):
            r = idx // cols
            c = idx % cols
            x0 = c * cell; y0 = r * cell
            sx = x0 + (B - total_stripes_w) // 2
            byte = 0
            for bit in range(8):
                x_stripe0 = sx + bit * stripe_w
                x_stripe1 = x_stripe0 + stripe_w
                xs = x_stripe0 + stripe_w//2
                ys0 = y0 + 1; ys1 = y0 + B - 1
                xs0 = max(x_stripe0, xs-1); xs1 = min(x_stripe1, xs+2)
                ys0 = max(ys0, 0); ys1 = min(ys1, gray.shape[0])
                if xs0 >= xs1 or ys0 >= ys1:
                    sample_val = 0
                else:
                    sample_region = gray[ys0:ys1, xs0:xs1]
                    sample_val = int(sample_region.mean()) if sample_region.size>0 else 0
                bitval = 1 if sample_val > 127 else 0
                byte = (byte << 1) | bitval
            recovered.append(byte)
    return bytes(recovered)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("inpath")
    p.add_argument("outfile")
    p.add_argument("--width",type=int,default=1920)
    p.add_argument("--height",type=int,default=1080)
    p.add_argument("--block",type=int,default=8)
    p.add_argument("--gutter",type=int,default=1)
    p.add_argument("--fps",type=int,default=60)
    args = p.parse_args()

    inpath = Path(args.inpath)
    tempdir = None
    frames_dir = None
    if inpath.is_file() and inpath.suffix.lower() in {".webm", ".mp4", ".mkv", ".mov"}:
        tempdir = tempfile.mkdtemp(prefix="ytstore_frames_")
        try:
            frame_paths = extract_frames_from_video(inpath, Path(tempdir), fps=args.fps)
            frames_dir = Path(tempdir)
        except Exception as e:
            print("ffmpeg extraction failed:", e); sys.exit(1)
    elif inpath.is_dir():
        frames_dir = inpath
        frame_paths = sorted(frames_dir.glob("frame_*.png"))
    else:
        print("Input must be a video file or a frames directory.")
        sys.exit(1)

    if not frame_paths:
        print("No frames found to decode.")
        sys.exit(1)

    # try to load manifest if present next to frames_dir
    manifest = None
    mpath = frames_dir.parent / "manifest.json" if (frames_dir.name == "frames") else frames_dir / "manifest.json"
    if mpath.exists():
        try:
            manifest = json.loads(mpath.read_text())
            print("Loaded manifest:", mpath)
        except:
            manifest = None

    data = decode_frames_to_bytes(frame_paths, args.width, args.height, args.block, args.gutter)
    if manifest and "file_length" in manifest:
        trimmed = data[:manifest["file_length"]]
    else:
        trimmed = data
    Path(args.outfile).write_bytes(trimmed)
    print("Wrote recovered", len(trimmed), "bytes to", args.outfile)

    if tempdir:
        shutil.rmtree(tempdir)

if __name__ == '__main__':
    main()
