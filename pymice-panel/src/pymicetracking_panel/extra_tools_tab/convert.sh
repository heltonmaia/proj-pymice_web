#!/bin/bash

# Loop through all mp4 files in the current directory
for file in *.mp4; do
    # Extract the base name without extension
    base_name="${file%.*}"
    
    # Define the output file name with the _low suffix
    output_file="${base_name}_low.mp4"
    
    # Run ffmpeg command to convert the video to low resolution
    ffmpeg -i "$file" -vf scale=640:-2 "$output_file"
done
