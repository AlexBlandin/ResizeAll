#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "tqdm",
#   "attrs",
#   "cattrs",
#   "pillow>=11.2.1",
# ]
# ///
#
"""
resize all w2x wrapper.

Copyright 2022 Alex Blandin

resizeall [-r] [-f] [--yes/no] [--redo] [--force/denoise]
          [-s int] [-d int] [-e /path/to/w2x] [-m /to/model/] [-j load:proc:save] [-o str]
          [-h -?]
  -r = Recursive image find
  --no = Autoanswer any questions with a "no", takes precedence over "--yes"
  --yes = Autoanswer any questions with a "yes"
  --redo = Overwrite already done images
  --always = Always resize at least 2x magnification on all images, even if they are "too big"
  --denoise = Denoise images only
  -x: int = Set the magnification for resizing, use one of {acceptable_magnifications} or 0 to disable, default: 0
  -s: int = Minimum sufficient dimension for an image in pixels,, default: {sufficient_size}px
  -d: int = Maximum dimension, ignore an image if one of the sides goes over, default: {dont_go_over}px
  -n: int = Set the denoise level used, negative to denoise with no resizing, default: {denoise_level}
  -f: "output/folder/" = Place output images in the given folder, relative to the processed image
  -o: "_append2.name" = Output marker appended to file name, to identify the results, default: "{marker}"
  -e: "/path/to/w2x" = Directory of your w2x executable, default: "{executable}"
  -m: "/path/to/model/" = Directory of your model, default: "{model}"
  -j: load:proc:save = Threads used, speedups may use more memory, default: "{job_load}:{job_proc}:{job_save}"
  -h or -? or ? = Show this help page
"""

import traceback
from ctypes import windll
from math import ceil, log2
from pathlib import Path
from subprocess import run
from sys import argv, exit
from time import sleep

from PIL import Image
from tqdm import tqdm

Image.MAX_IMAGE_PIXELS = None
set_title = windll.kernel32.SetConsoleTitleW

args, erroneous = set(argv), []
acceptable_magnifications = [1, 2, 4, 8, 16, 32]
sufficient_size, dont_go_over = 2160, 8640
denoise_level, to_scale, forced_scale = 1, True, 2
executable, model = "C:/bin/w2x/waifu2x-ncnn-vulkan", "C:/bin/w2x/models-cunet"
job_load, job_proc, job_save = 1, 2, 2
output_folder, marker = None, ".w2x"
delimlen = len(marker)


def param(arg):  # noqa: ANN001, ANN201, D103
  a = argv.index(arg)
  return "" if a >= (len(argv) - 1) else argv[a + 1]


if "-?" in args or "?" in args or "-h" in args:
  print(  # noqa: T201
    __doc__.format(
      acceptable_magnifications=acceptable_magnifications,
      sufficient_size=sufficient_size,
      dont_go_over=dont_go_over,
      denoise_level=denoise_level,
      marker=marker,
      executable=executable,
      model=model,
      job_load=job_load,
      job_proc=job_proc,
      job_save=job_save,
    )
  )
  exit()

recursive = "-r" in args
always = "--always" in args
forced = "-x" in args
redoing = "--redo" in args
to_scale = "--denoise" not in args
yes = "--yes" in args
no = "--no" in args
exclude = "--exclude" in args
exclude_list = []

if not to_scale and (always or forced):
  print("You cannot set --denoise either --always or -x, as --denoise is without scaling")  # noqa: T201
  exit(1)

if forced and always:
  always = False  # forced takes precedent

if "-s" in args and (size := int(param("-s"))) > 1:
  sufficient_size = size

if "-d" in args and (size := int(param("-d"))) > 1:
  dont_go_over = size

if "-n" in args and -1 <= abs(level := int(param("-n"))) <= 3:  # noqa: PLR2004
  denoise_level = level

if forced and (size := int(param("-x"))):
  if size in acceptable_magnifications:
    forced_scale = int(size)
  else:
    print(f"Unfortunately, -x must be one of {acceptable_magnifications} (was {size})")  # noqa: T201
    exit(1)

if "-m" in args and len(_model := param("-m")) > 0:
  if _model[0] == '"':
    _model = _model[1:]
  if _model[-1] == '"':
    _model = _model[:-1]
  if len(_model):
    model = _model

if "-e" in args and len(_exec := param("-e")) > 0:
  if _exec[0] == '"':
    _exec = _exec[1:]
  if _exec[-1] == '"':
    _exec = _exec[:-1]
  if len(_exec):
    executable = _exec

output_folder = folder if "-f" in args and len(folder := param("-f")) else None

if "-o" in args and len(delim := param("-o")):
  if delim[0] == '"':
    delim = delim[1:]
  if delim[-1] == '"':
    delim = delim[:-1]
  if len(delim):
    marker = delim
  delimlen = len(delim)

extensions = [".png", ".jpg", ".jpeg", ".jfif", ".tif", ".tiff", ".bmp", ".tga"]
pattern = "*.[pPjJtTbB][nNpPiImMgGfF][gGeEfFpPaAiI]*"
args = (
  f'-f png -n {denoise_level} -j {job_load}:{job_proc}:{job_save} -m "{model}"'  # -l png:jpg:jpeg:jfif:tif:tiff:bmp:tga
)

gifpattern = "*.[gGaAwW][iIpPeE][fFnNbB]*"
gifs = list(Path().rglob(gifpattern) if recursive else Path().glob(gifpattern))
# split gifs
if gifs and not no and (yes or input("Magnify animated images? [y/N]: ").strip().lower() in {"y", "ye", "yes"}):
  for gif in gifs:
    if yes or input(f"Magnify {gif}? [y/N]: ").strip().lower() not in {"y", "ye", "yes"}:
      continue
    try:
      if (
        exstat := run(
          f'ffmpeg -v "warning" -i "{gif}" -vsync 0 -vf mpdecimate=frac=0.01 "{gif.parent}/{gif.stem}"%05d.png',
          capture_output=True,
          check=False,
        )
      ).returncode:
        erroneous.append(("Animation conversion error", str(gif), exstat.stderr, exstat.stdout))
    except Exception as err:  # noqa: BLE001
      trace = traceback.format_exc()
      erroneous.append(("Animation conversion error", str(gif), err, trace))

sleep(0.5)
_unused = yes or no or input("Press [Enter/Return] to start conversion: ")
sleep(0.5)

# grab all dirs
files = {str(p): p for p in (Path().rglob(pattern) if recursive else Path().glob(pattern))}
fc = len(files)
if fc < 1:
  print("Found no files")  # noqa: T201
  exit()

images: list[Path] = []
for img in list(files.values()):
  try:
    imgname = img.parent / img.name
    outparent = img.parent / output_folder if output_folder else img.parent
    outname = outparent / f"{img.stem}{marker}"
    as_resized = f"{Path(outname)}.png"
    an_original = str(
      img.parent / (str(img.stem)[:-delimlen] + "".join(img.suffixes))
    )  # possible original by trimming output delimiter
    ext = str(img.suffix).lower()

    if (
      (as_resized in files and not redoing)
      or (str(img.stem)[-delimlen:] == marker and an_original in files)
      or img.resolve().parts[-2] == "w2x"
      or (output_folder and outparent.is_file())
      or ext not in extensions
      or (exclude and img.parent.name in exclude_list)
    ):
      continue

    wh = Image.open(img).size  # (width, height)
    if not to_scale:
      images.append(img)
      continue
    if (max(wh) > dont_go_over or min(wh) > sufficient_size) and (not forced or not always):
      continue
    images.append(img)
  except Exception as err:  # noqa: BLE001
    trace = traceback.format_exc()
    erroneous.append(("Image Search Error", str(img), err, trace))

print(f"Converting {len(images)} file{'s' if fc != 1 else ''} in {Path.cwd()}")  # noqa: T201
with tqdm(images, unit="img") as pbar:
  for img in pbar:
    try:
      imgname = img.parent / img.name
      outparent = img.parent / output_folder if output_folder else img.parent
      outname = outparent / f"{img.stem}{marker}"
      as_resized = f"{Path(outname)}.png"
      an_original = str(
        img.parent / (str(img.stem)[:-delimlen] + "".join(img.suffixes))
      )  # possible original by trimming output delimiter
      ext = str(img.suffix).lower()

      if (
        (as_resized in files and not redoing)
        or (str(img.stem)[-delimlen:] == marker and an_original in files)
        or img.resolve().parts[-2] == "w2x"
        or (output_folder and outparent.is_file())
        or ext not in extensions
      ):
        continue  # might as well check twice now
      if output_folder and not outparent.is_dir():
        outparent.mkdir()

      wh = Image.open(img).size  # (width, height)
      magnif = 1
      if to_scale:
        magnif = min(1 << max(0, ceil(log2(sufficient_size / min(wh) - 1) + 1)), 32)
      if forced:
        magnif = forced_scale
      elif always:
        magnif = max(2, magnif)

      exstat = None
      if to_scale:
        if (max(wh) > dont_go_over or min(wh) > sufficient_size) and not forced:
          continue
        pbar.set_postfix(magnif=f"{forced_scale if forced else magnif}x{'!!' if magnif > 7 else ''}")  # noqa: PLR2004
        set_title(f"Upscaling {img} by {forced_scale if forced else magnif}x{'!!' if magnif > 7 else ''}")  # noqa: PLR2004
      else:
        pbar.set_postfix(denoise=denoise_level)
        set_title(f"Denoising {img}")

      if not to_scale:
        exstat = run(f'{executable} -i "{img}" -s 1 -o "{as_resized}" {args} -x 0', capture_output=True, check=False)  # noqa: S603
      elif magnif > 7:  # noqa: PLR2004
        exstat = run(
          f'{executable} -i "{img}" -s {magnif} -o "{as_resized}" {args} -x 1',
          capture_output=True,
          check=False,
        )
      elif magnif > 1:
        exstat = run(
          f'{executable} -i "{img}" -s {magnif} -o "{as_resized}" {args} -x 0',
          capture_output=True,
          check=False,
        )

      if exstat and exstat.returncode != 0:
        erroneous.append(("Resize Error", str(img), exstat.stderr, exstat.stdout))
    except Exception as err:  # noqa: BLE001
      trace = traceback.format_exc()
      erroneous.append(("Resize Error", str(img), err, trace))

print("File list exhausted")  # noqa: T201

if (ec := len(erroneous)) > 0:
  from pprint import pprint

  print(f"{ec} errors detected, erroneous files:")  # noqa: T201
  pprint(erroneous, compact=True)  # noqa: T203
else:
  print("No errors detected")  # noqa: T201

if Path("./cudnn_data").exists():
  from shutil import rmtree

  rmtree(Path("./cudnn_data"))
