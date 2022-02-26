#!/bin/bash
mkdir -p gifs
# FPS are modified to stay below 1000 frames each (google drive restriction)
# they should still remain a multiple of 60
ffmpeg -y -i media/videos/main/650p60/RecursiveEntityResolution.mp4 -vf "fps=30,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" -loop 0 gifs/rer.gif
ffmpeg -y -i media/videos/topk/740p60/TopkMaxThreshold.mp4 -vf "fps=20,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" -loop 0 gifs/topk.gif
