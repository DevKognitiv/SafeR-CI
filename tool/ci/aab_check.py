#!/usr/bin/env python3
"""Android App Bundle gate: download-size estimate per ABI, asset budgets and 16 KB ELF alignment.

Usage: python3 tool/ci/aab_check.py <app.aab> [--budget tool/ci/size_budget.json] [--report out.md]

Exit code 1 when a 64-bit native library is not 16 KB aligned (Google Play requirement for 16 KB page-size
devices) or when a budget in the budget file is set and exceeded. Budgets left at null are reported only, so the
first CI run can establish the baseline that later runs are gated against (baseline + 10% until under 35 MB).
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

PT_LOAD = 1
PAGE_16K = 16 * 1024
ABIS_64 = {"arm64-v8a", "x86_64"}


def load_alignments(data: bytes) -> list[int]:
    """Return p_align of every PT_LOAD segment of an ELF image (empty list when not an ELF)."""
    if data[:4] != b"\x7fELF" or len(data) < 0x40:
        raise ValueError("not an ELF image")
    is_64 = data[4] == 2
    endian = "<" if data[5] == 1 else ">"
    if is_64:
        e_phoff = struct.unpack_from(endian + "Q", data, 0x20)[0]
        e_phentsize, e_phnum = struct.unpack_from(endian + "HH", data, 0x36)
    else:
        e_phoff = struct.unpack_from(endian + "I", data, 0x1C)[0]
        e_phentsize, e_phnum = struct.unpack_from(endian + "HH", data, 0x2A)
    aligns = []
    if e_phoff + e_phnum * e_phentsize > len(data) or e_phentsize < (56 if is_64 else 32):
        raise ValueError("truncated or malformed program header table")
    for index in range(e_phnum):
        offset = e_phoff + index * e_phentsize
        if is_64:
            p_type = struct.unpack_from(endian + "I", data, offset)[0]
            p_align = struct.unpack_from(endian + "Q", data, offset + 48)[0]
        else:
            p_type = struct.unpack_from(endian + "I", data, offset)[0]
            p_align = struct.unpack_from(endian + "I", data, offset + 28)[0]
        if p_type == PT_LOAD:
            aligns.append(p_align)
    return aligns


def human(size: int) -> str:
    return f"{size / 1024 / 1024:.2f} MB" if size >= 1024 * 1024 else f"{size / 1024:.1f} KB"


def analyse(aab: Path) -> dict:
    """Walk the bundle: per-ABI download estimate (compressed base module without other ABIs), assets, ELF alignment."""
    result = {"aab_bytes": aab.stat().st_size, "abi_download_bytes": {}, "fonts_bytes": 0, "images_bytes": 0, "libs": [], "modules": set()}
    with zipfile.ZipFile(aab) as bundle:
        infos = bundle.infolist()
        abis = set()
        base_common = 0
        per_abi = defaultdict(int)
        for info in infos:
            parts = info.filename.split("/")
            if len(parts) < 2:
                continue
            module = parts[0]
            result["modules"].add(module)
            if module != "base":
                continue
            if parts[1] == "lib" and len(parts) >= 4:
                abi = parts[2]
                abis.add(abi)
                per_abi[abi] += info.compress_size
                if info.filename.endswith(".so"):
                    try:
                        aligns = load_alignments(bundle.read(info))
                        parsed = True
                    except (ValueError, struct.error):
                        aligns, parsed = [], False
                    result["libs"].append({
                        "path": info.filename,
                        "abi": abi,
                        "bytes": info.file_size,
                        "load_aligns": aligns,
                        "parsed": parsed,
                        "aligned_16k": parsed and bool(aligns) and all(a >= PAGE_16K for a in aligns),
                    })
            else:
                base_common += info.compress_size
                if "/assets/flutter_assets/assets/fonts/" in info.filename or "/assets/flutter_assets/fonts/" in info.filename:
                    result["fonts_bytes"] += info.file_size
                if "/assets/flutter_assets/assets/images/" in info.filename or "/assets/flutter_assets/assets/illustrations/" in info.filename:
                    result["images_bytes"] += info.file_size
        for abi in sorted(abis):
            result["abi_download_bytes"][abi] = base_common + per_abi[abi]
    result["modules"] = sorted(result["modules"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("aab")
    parser.add_argument("--budget", default="tool/ci/size_budget.json")
    parser.add_argument("--report", default=None)
    args = parser.parse_args()
    aab = Path(args.aab)
    if not aab.exists():
        print(f"AAB not found: {aab}")
        return 2
    budget = {}
    budget_path = Path(args.budget)
    if budget_path.exists():
        budget = json.loads(budget_path.read_text())
    res = analyse(aab)
    failures: list[str] = []
    lines = [f"# App bundle report: {aab.name}", "", f"- Bundle size: {human(res['aab_bytes'])} ({res['aab_bytes']} bytes)", f"- Modules: {', '.join(res['modules'])}"]
    for abi, size in res["abi_download_bytes"].items():
        lines.append(f"- Download estimate {abi}: {human(size)} ({size} bytes)")
    lines.append(f"- Bundled fonts: {human(res['fonts_bytes'])}")
    lines.append(f"- Bundled images/illustrations: {human(res['images_bytes'])}")
    lines.append("")
    lines.append("| Native library | ABI | Size | PT_LOAD align | 16 KB |")
    lines.append("| --- | --- | --- | --- | --- |")
    for lib in res["libs"]:
        ok = "yes" if lib["aligned_16k"] else "NO"
        aligns = ", ".join(hex(a) for a in lib["load_aligns"]) if lib["parsed"] else "unparsable ELF"
        lines.append(f"| {lib['path'].split('/')[-1]} | {lib['abi']} | {human(lib['bytes'])} | {aligns} | {ok} |")
        if lib["abi"] in ABIS_64 and not lib["aligned_16k"]:
            failures.append(f"{lib['path']} is not 16 KB aligned (PT_LOAD align: {aligns})")
    aab_max = budget.get("aab_bytes_max")
    if aab_max and res["aab_bytes"] > aab_max:
        failures.append(f"bundle {res['aab_bytes']} bytes exceeds budget {aab_max}")
    for abi, limit in (budget.get("abi_download_bytes_max") or {}).items():
        size = res["abi_download_bytes"].get(abi)
        if limit and size and size > limit:
            failures.append(f"{abi} download estimate {size} bytes exceeds budget {limit}")
    fonts_max = budget.get("fonts_bytes_max")
    if fonts_max and res["fonts_bytes"] > fonts_max:
        failures.append(f"fonts {res['fonts_bytes']} bytes exceed budget {fonts_max}")
    images_max = budget.get("images_bytes_max")
    if images_max and res["images_bytes"] > images_max:
        failures.append(f"images {res['images_bytes']} bytes exceed budget {images_max}")
    lines.append("")
    lines.append("## Result")
    lines.append("")
    if failures:
        lines.extend(f"- FAIL: {f}" for f in failures)
    else:
        lines.append("- PASS: every 64-bit native library is 16 KB aligned and every configured budget holds")
    if not aab_max:
        lines.append("- Note: no bundle budget configured yet (tool/ci/size_budget.json); this run records the baseline")
    report = "\n".join(lines) + "\n"
    print(report)
    if args.report:
        Path(args.report).write_text(report)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
