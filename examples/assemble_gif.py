from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent
frames_dir = OUT / "output" / "frames"
frame_files = ["f0.png", "f1.png", "f2.png", "f3.png", "f4.png", "f5.png"]
durations = [1400, 1200, 1200, 900, 1200, 1800]  # ms par frame

imgs = [
    Image.open(frames_dir / f).convert("P", palette=Image.Palette.ADAPTIVE, colors=128)
    for f in frame_files
]

output_path = OUT / "illustrations" / "demo_interaction.gif"
imgs[0].save(
    output_path,
    save_all=True,
    append_images=imgs[1:],
    duration=durations,
    loop=0,
    optimize=True,
)
print(f"gif written -> {output_path}")
