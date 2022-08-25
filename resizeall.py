from subprocess import run
from itertools import repeat, count
from pathlib import Path
from ctypes import windll
from time import sleep
from math import ceil
from sys import argv
import traceback

set_title = windll.kernel32.SetConsoleTitleW

from tqdm import tqdm
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

args, erroneous = set(argv), []
sufficient_size, dont_go_over = 2160, 8640 # sufficient_size is this as it means resizing takes less than 10s on average
denoise_level, to_scale = 1, True
executable, model = "C:/bin/w2x/w2x-cui", "C:/bin/w2x/models/cunet"
output_folder, marker = "w2x/", ".w2x"
delimlen = len(marker)

def param(arg):
  a = argv.index(arg)
  return "" if a >= (len(argv) - 1) else argv[a + 1]

if "-?" in args or "?" in args or "-h" in args:
  print("w2x resize-all")
  print()
  print(f"args:")
  print(
    f'  w2x [-r] [-f] [--yes/no] [--redo] [--force] [-s {sufficient_size}] [-d {dont_go_over}] [-e /path/to/w2x] [-m /path/to/w2x/model/] [-o "{marker}"] [-h -? ?]'
  )
  print(f"    -r Recursive image find")
  print(f'    --no Autoanswer any questions with a "no", takes precedence over "--yes"')
  print(f'    --yes Autoanswer any questions with a "yes"')
  print(f"    --redo Overwrite already done images")
  print(f'    --force Force at least 2x magnification on all images, even if they are "too big"')
  print(
    f"    -s {sufficient_size} Minimum sufficient dimension for an image in pixels, defaults to {sufficient_size}px"
  )
  print(
    f"    -d {dont_go_over} Maximum dimension, ignore an image if one of the sides goes over, defaults to {dont_go_over}px"
  )
  print(
    f"    -n {denoise_level} Set the denoise level used, negative to denoise with no resizing, defaults to {denoise_level}"
  )
  print(f'    -e "{executable}" Directory for your w2x executable, default is "{executable}"')
  print(f'    -m "{model}" Directory for your model, defaults to "{model}"')
  print(
    f'    -f "{output_folder}" Place output images in the given folder, relative to the processed image, defaults to "{output_folder}"'
  )
  print(f'    -o "{marker}" Output marker, to identify the results, default is "{marker}"')
  print(f"    -h or -? or ? Show this help page")
  exit()

recursive = "-r" in args
forced = "--force" in args
redoing = "--redo" in args
yes = "--yes" in args
no = "--no" in args
exclude = "--exclude" in args
exclude_list = []

if "-s" in args and (size := int(param("-s"))) > 1:
  sufficient_size = size

if "-d" in args and (size := int(param("-d"))) > 1:
  dont_go_over = size

if "-n" in args and 0 <= abs(level := int(param("-n"))) <= 3:
  if level < 0:
    to_scale = False
    level = abs(level)
  denoise_level = level

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

if "-f" in args and len(folder := param("-f")):
  output_folder = folder
elif "-f" in args:
  output_folder = "w2x/"
else:
  output_folder = None

if "-o" in args and len(delim := param("-o")):
  if delim[0] == '"':
    delim = delim[1:]
  if delim[-1] == '"':
    delim = delim[:-1]
  if len(delim):
    marker = delim
  delimlen = len(delim)

extensions = [".png", ".jpg", ".jpeg", ".jfif", ".tif", ".tiff", ".bmp", ".tga"]
pattern, args = "*.[pPjJtTbB][nNpPiImMgGfF][gGeEfFpPaAiI]*", f'-e png -l png:jpg:jpeg:jfif:tif:tiff:bmp:tga -m {"noise_scale" if to_scale else "noise"} -n {denoise_level} -p cudnn --model_dir "{model}" -t'

gifpattern = "*.[gGaAwW][iIpPeE][fFnNbB]*"
gifs = list(Path(".").rglob(gifpattern) if recursive else Path(".").glob(gifpattern))
# split gifs
if len(gifs) and not no and (yes or input(f"Magnify animated images? [y/N]: ").strip().lower() in ["y", "ye", "yes"]):
  for gif in gifs:
    if yes or input(f"Magnify {gif}? [y/N]: ").strip().lower() not in ["y", "ye", "yes"]: continue
    try:
      if (
        exstat := run(
          f'ffmpeg -v "warning" -i "{gif}" -vsync 0 -vf mpdecimate=frac=0.01 "{gif.parent}/{gif.stem}"%05d.png',
          capture_output = True
        )
      ).returncode:
        erroneous.append(("Animation conversion error", str(gif), exstat.stderr, exstat.stdout))
    except Exception as err:
      trace = traceback.format_exc()
      erroneous.append(("Animation conversion error", str(gif), err, trace))

sleep(0.5)
yes or no or input("Press [Enter/Return] to start conversion: ")
sleep(0.5)

# grab all dirs
files = dict([(str(p), p) for p in (Path(".").rglob(pattern) if recursive else Path(".").glob(pattern))])
fc = len(files)
if fc < 1:
  print("Found no files")
  exit()

images = []
for img in list(files.values()):
  try:
    imgname = img.parent / img.name
    outparent = img.parent / output_folder if output_folder else img.parent
    outname = outparent / f"{img.stem}{marker}"
    as_resized = f"{Path(outname)}.png"
    an_original = str(
      img.parent / (str(img.stem)[:-delimlen] + "".join(img.suffixes))
    ) # possible original by trimming output delimiter
    ext = str(img.suffix).lower()
    if (as_resized in files and not redoing) \
      or (str(img.stem)[-delimlen:] == marker and an_original in files) \
      or img.resolve().parts[-2] == "w2x" \
      or (output_folder and outparent.is_file()) \
      or ext not in extensions \
      or exclude and img.parent.name in exclude_list:
      continue
    wh = Image.open(img).size # (width, height)
    if not to_scale:
      images.append(img)
      continue
    if (max(wh) > dont_go_over or min(wh) > sufficient_size) and not forced: continue
    images.append(img)
  except Exception as err:
    trace = traceback.format_exc()
    erroneous.append(("Image Search Error", str(img), err, trace))

print(f"Converting {len(images)} file{'s' if fc != 1 else ''} in {Path('.').resolve()}")
with tqdm(images, unit = "img") as pbar:
  for img in pbar:
    try:
      imgname = img.parent / img.name
      outparent = img.parent / output_folder if output_folder else img.parent
      outname = outparent / f"{img.stem}{marker}"
      as_resized = f"{Path(outname)}.png"
      an_original = str(
        img.parent / (str(img.stem)[:-delimlen] + "".join(img.suffixes))
      ) # possible original by trimming output delimiter
      ext = str(img.suffix).lower()
      if (as_resized in files and not redoing) \
        or (str(img.stem)[-delimlen:] == marker and an_original in files) \
        or img.resolve().parts[-2] == "w2x" \
        or (output_folder and outparent.is_file()) \
        or ext not in extensions:
        continue # might as well check twice now
      if output_folder and not outparent.is_dir(): outparent.mkdir()
      wh = Image.open(img).size # (width, height)
      magnif = ceil(sufficient_size / min(wh))
      if to_scale:
        if (max(wh) > dont_go_over or min(wh) > sufficient_size) and not forced: continue
        exstat = None
        pbar.set_postfix(magnif = f"{2 if forced else magnif}x{'!!' if magnif > 7 else ''}")
        set_title(f"Upscaling {img} by {2 if forced else magnif}x{'!!' if magnif > 7 else ''}")
      else:
        pbar.set_postfix(denoise = denoise_level)
        set_title(f"Denoising {img}")
      if not to_scale:
        exstat = run(f'{executable} -i "{img}" -o "{as_resized}" {args} 0', capture_output = True)
      elif magnif > 7:
        exstat = run(f'{executable} -i "{img}" -s {magnif} -o "{as_resized}" {args} 1', capture_output = True)
      elif magnif > 1:
        exstat = run(f'{executable} -i "{img}" -s {magnif} -o "{as_resized}" {args} 0', capture_output = True)
      elif forced: # force at least 2x resizing on all
        exstat = run(f'{executable} -i "{img}" -s 2 -o "{as_resized}" {args} 0', capture_output = True)
      
      if exstat is not None and exstat.returncode != 0:
        erroneous.append(("Resize Error", str(img), exstat.stderr, exstat.stdout))
    except Exception as err:
      trace = traceback.format_exc()
      erroneous.append(("Resize Error", str(img), err, trace))

print("File list exhausted")

if (ec := len(erroneous)) > 0:
  from pprint import pprint
  print(f"{ec} errors detected, erroneous files:")
  pprint(erroneous, compact = True)
else:
  print("No errors detected")

if Path("./cudnn_data").exists():
  from shutil import rmtree
  rmtree(Path("./cudnn_data"))
