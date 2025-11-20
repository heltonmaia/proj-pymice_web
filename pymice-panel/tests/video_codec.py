from pprint import pprint

import time
import numpy as np
import cv2 as cv
import ffmpeg
import json

# diagnosticar a diferenca entre o funcional e o nao-funcional
video_path = 'testar_codec.mp4'
video_path2 = '2AF11_OF.mp4'

# info = ffmpeg.probe(video_path)
# info2 = ffmpeg.probe(video_path2)

# video_stream = next( 
#                 (stream for stream in info['streams'] if stream['codec_type']=='video'),
#                 None
#                 )

# with open('video_compactado.json', 'w', encoding='utf-8') as file:
#     json.dump(info, file, indent=4)

# with open('video_funcional.json', 'w', encoding='utf-8') as file:
#     json.dump(info2, file, indent=4)

# (
#     ffmpeg
#     .input("testar_codec.mp4")
#     .output(
#         "testar_codec_fixed.mp4",
#         **{
#             "c:v": "copy",      # não altera o vídeo
#             # "c:a": "copy",      # mantém áudio (se quiser remover depois é fácil)
#             "an": None,
#             "movflags": "faststart",  # reconstrói o moov atom
#             "vsync": 2           # recria timestamps limpos
#         }
#     )
#     .overwrite_output()
#     .run()
# )


try:
    cap = cv.VideoCapture('E3MOD20 - Epm.mp4')
    total_frames = int(cap.get(cv.CAP_PROP_FRAME_COUNT))

    sample_ret, sample_frame = cap.read()

    # Reset video position
    cap.set(cv.CAP_PROP_POS_FRAMES, 0)
    print('check 1')

    # Initialize frame accumulator
    # sample_frame = cv.resize(sample_frame, YOLO_RESOLUTION)
    frame_count = 0
    median_accumulator = np.zeros_like(sample_frame, dtype=np.float32)
    print('check 2')

    # Sample frames to calculate background (not processing every frame for efficiency)
    # Use frame sampling to process approximately 200 frames
    total_samples = min(200, total_frames)
    frame_step = max(1, total_frames // total_samples)

    height, width, _ = sample_frame.shape

    current_frame = 0

    print('check 3')

    t_inicial = time.time()
    while current_frame < total_frames:
        print(f'Frame n°: {current_frame} de {total_frames}')
        # Set position to the current frame
        cap.set(cv.CAP_PROP_POS_FRAMES, current_frame)
        ret, frame = cap.read()

        if not ret:
            break

        # Convert to float and accumulate
        frame_float = frame.astype(np.float32)
        median_accumulator += frame_float
        frame_count += 1


        # Move to next frame to sample
        current_frame += frame_step

    cap.release()
    print('check 4')
    
    # Calculate the average (approximating median for efficiency)
    background = (median_accumulator / frame_count).astype(np.uint8)

    t_final = time.time()
    print(f'tempo de exec: {t_final - t_inicial}')
    while True:
        # Save the background image in models folder
        cv.imshow('background',background)
        
        if cv.waitKey(1) & 0xff == 27:
            break
    print('check 5')

except Exception as e:
    print(f"Background calculation error: {e}")
