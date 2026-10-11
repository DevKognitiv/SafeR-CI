#!/usr/bin/env python3
"""Colour-vision deficiency simulation for the screen rubric (docs/qa/screen-rubric.md §2).

Writes ``<name>.deutan.png`` and ``<name>.protan.png`` next to each PNG given on the
command line, using the Machado, Oliveira and Fernandes (2009) dichromat matrices at full
severity (the ones browser DevTools use for "emulate vision deficiencies"), applied in
linear RGB. Needs Pillow (``python3 -m pip install pillow``); with numpy the conversion is
exact, without it the matrix is applied in gamma space (a visible but acceptable
approximation for the checklist).

    python3 simulate_cvd.py out/security/light-fr-1.0-360x780.png [more.png ...]
    python3 simulate_cvd.py --all out/            # every PNG under a directory
"""

from __future__ import annotations

import argparse
import pathlib
import sys

try:
    from PIL import Image
except ImportError:  # pragma: no cover - environment check
    sys.exit("Pillow is required: python3 -m pip install pillow")

MATRICES = {
    "deutan": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "protan": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
}


def _simulate_numpy(image: Image.Image, matrix) -> Image.Image:
    import numpy as np  # noqa: PLC0415 - optional dependency

    rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    out = linear @ np.asarray(matrix, dtype=np.float32).T
    out = np.clip(out, 0.0, 1.0)
    srgb = np.where(out <= 0.0031308, out * 12.92, 1.055 * (out ** (1 / 2.4)) - 0.055)
    return Image.fromarray((srgb * 255.0 + 0.5).astype("uint8"), "RGB")


def _simulate_pillow(image: Image.Image, matrix) -> Image.Image:
    # Gamma-space approximation when numpy is unavailable.
    flat = tuple(v for row in matrix for v in (*row, 0.0))
    return image.convert("RGB").convert("RGB", flat)


def simulate(path: pathlib.Path) -> list[pathlib.Path]:
    image = Image.open(path)
    written = []
    for name, matrix in MATRICES.items():
        try:
            result = _simulate_numpy(image, matrix)
        except ImportError:
            result = _simulate_pillow(image, matrix)
        target = path.with_name(f"{path.stem}.{name}.png")
        result.save(target, optimize=True)
        written.append(target)
    return written


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", help="PNG files, or directories with --all")
    parser.add_argument("--all", action="store_true", help="treat paths as directories and convert every capture in them")
    args = parser.parse_args(argv)
    files: list[pathlib.Path] = []
    for raw in args.paths:
        p = pathlib.Path(raw)
        if args.all and p.is_dir():
            files.extend(f for f in sorted(p.rglob("*.png")) if ".deutan." not in f.name and ".protan." not in f.name)
        else:
            files.append(p)
    for f in files:
        for target in simulate(f):
            print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
