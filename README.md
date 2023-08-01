# ResizeAll
ResizeAll: What it says on the tin!

## Requirements

- [`poetry install`](https://python-poetry.org/)
- [waifu2x ncnn vulkan](https://github.com/nihui/waifu2x-ncnn-vulkan)
  - (switched to this as w2x caffe wasn't being maintained, however this means we can only scale in powers of 2 up to 32x, so we overscale currently)
- Images to upscale!
  - A sense of shame is optional
