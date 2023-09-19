from subprocess import run
from pathlib import Path
from ctypes import windll
from time import sleep
from math import log2, ceil
from sys import argv
import traceback

from tqdm import tqdm
from PIL import Image

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

def param(arg):
  a = argv.index(arg)
  return "" if a >= (len(argv) - 1) else argv[a + 1]

if "-?" in args or "?" in args or "-h" in args:
  print("w2x resize-all")
  print()
  print("args:")
  print("  w2x [-r] [-f] [--yes/no] [--redo] [--force/denoise] [-s int] [-d int] [-e /path/to/w2x] [-m /path/to/model/] [-j load:proc:save] [-o str] [-h -?]")
  print("    -r = Recursive image find")
  print('    --no = Autoanswer any questions with a "no", takes precedence over "--yes"')
  print('    --yes = Autoanswer any questions with a "yes"')
  print("    --redo = Overwrite already done images")
  print('    --always = Always resize at least 2x magnification on all images, even if they are "too big"')
  print("    --denoise = Denoise images only")
  print(f"    -x: int = Set the magnification for resizing, use one of {acceptable_magnifications} or 0 to disable, default: 0")
  print(f"    -s: int = Minimum sufficient dimension for an image in pixels, will scale by powers of 2 to reach this, default: {sufficient_size}px")
  print(f"    -d: int = Maximum dimension, ignore an image if one of the sides goes over, default: {dont_go_over}px")
  print(f"    -n: int = Set the denoise level used, negative to denoise with no resizing, default: {denoise_level}")
  print('    -f: "output/folder/" = Place output images in the given folder, relative to the processed image')
  print(f'    -o: "_append2.name" = Output marker appended to file name (before extension), to identify the results, default: "{marker}"')
  print(f'    -e: "/path/to/w2x" = Directory for your w2x executable, default: "{executable}"')
  print(f'    -m: "/path/to/model/" = Directory for your model, default: "{model}"')
  print(f'    -j: load:proc:save = Threads used by w2x, increasing may speedup processing but may use more memory, default: "{job_load}:{job_proc}:{job_save}"')
  print("    -h or -? or ? = Show this help page")
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
  print("You cannot set --denoise either --always or -x, as --denoise is without scaling")
  exit(1)

if forced and always:
  always = False # forced takes precedent

if "-s" in args and (size := int(param("-s"))) > 1:
  sufficient_size = size

if "-d" in args and (size := int(param("-d"))) > 1:
  dont_go_over = size

if "-n" in args and -1 <= abs(level := int(param("-n"))) <= 3:
  denoise_level = level

if forced and (size := int(param("-x"))):
  if size in acceptable_magnifications:
    forced_scale = int(size)
  else:
    print(f"Unfortunately, -x must be one of {acceptable_magnifications} (was {size})")
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

if "-f" in args and len(folder := param("-f")):
  output_folder = folder
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
pattern = "*.[pPjJtTbB][nNpPiImMgGfF][gGeEfFpPaAiI]*"
args = f'-f png -n {denoise_level} -j {job_load}:{job_proc}:{job_save} -m "{model}"' # -l png:jpg:jpeg:jfif:tif:tiff:bmp:tga

gifpattern = "*.[gGaAwW][iIpPeE][fFnNbB]*"
gifs = list(Path(".").rglob(gifpattern) if recursive else Path(".").glob(gifpattern))
# split gifs
if len(gifs) and not no and (yes or input("Magnify animated images? [y/N]: ").strip().lower() in ["y", "ye", "yes"]):
  for gif in gifs:
    if yes or input(f"Magnify {gif}? [y/N]: ").strip().lower() not in ["y", "ye", "yes"]:
      continue
    try:
      if (
        exstat := run(f'ffmpeg -v "warning" -i "{gif}" -vsync 0 -vf mpdecimate=frac=0.01 "{gif.parent}/{gif.stem}"%05d.png', capture_output = True)
      ).returncode:
        erroneous.append(("Animation conversion error", str(gif), exstat.stderr, exstat.stdout))
    except Exception as err:
      trace = traceback.format_exc()
      erroneous.append(("Animation conversion error", str(gif), err, trace))

sleep(0.5)
_unused = yes or no or input("Press [Enter/Return] to start conversion: ")
sleep(0.5)

# grab all dirs
files = dict([(str(p), p) for p in (Path(".").rglob(pattern) if recursive else Path(".").glob(pattern))])
fc = len(files)
if fc < 1:
  print("Found no files")
  exit()

images: list[Path] = []
for img in list(files.values()):
  try:
    imgname = img.parent / img.name
    outparent = img.parent / output_folder if output_folder else img.parent
    outname = outparent / f"{img.stem}{marker}"
    as_resized = f"{Path(outname)}.png"
    an_original = str(img.parent / (str(img.stem)[:-delimlen] + "".join(img.suffixes))) # possible original by trimming output delimiter
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
    if (max(wh) > dont_go_over or min(wh) > sufficient_size) and (not forced or not always):
      continue
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
      an_original = str(img.parent / (str(img.stem)[:-delimlen] + "".join(img.suffixes))) # possible original by trimming output delimiter
      ext = str(img.suffix).lower()
      
      if (as_resized in files and not redoing) \
        or (str(img.stem)[-delimlen:] == marker and an_original in files) \
        or img.resolve().parts[-2] == "w2x" \
        or (output_folder and outparent.is_file()) \
        or ext not in extensions:
        continue # might as well check twice now
      if output_folder and not outparent.is_dir():
        outparent.mkdir()
      
      wh = Image.open(img).size # (width, height)
      magnif = 1
      if to_scale:
        magnif = min(1 << (ceil(log2(sufficient_size / min(wh) - 1) + 1)), 32)
      if forced:
        magnif = forced_scale
      elif always:
        magnif = max(2, magnif)
      
      exstat = None
      if to_scale:
        if (max(wh) > dont_go_over or min(wh) > sufficient_size) and not forced:
          continue
        pbar.set_postfix(magnif = f"{forced_scale if forced else magnif}x{'!!' if magnif > 7 else ''}")
        set_title(f"Upscaling {img} by {forced_scale if forced else magnif}x{'!!' if magnif > 7 else ''}")
      else:
        pbar.set_postfix(denoise = denoise_level)
        set_title(f"Denoising {img}")
      
      if not to_scale:
        exstat = run(f'{executable} -i "{img}" -s 1 -o "{as_resized}" {args} -x 0', capture_output = True)
      elif magnif > 7:
        exstat = run(f'{executable} -i "{img}" -s {magnif} -o "{as_resized}" {args} -x 1', capture_output = True)
      elif magnif > 1:
        exstat = run(f'{executable} -i "{img}" -s {magnif} -o "{as_resized}" {args} -x 0', capture_output = True)
      
      if exstat and exstat.returncode != 0:
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
