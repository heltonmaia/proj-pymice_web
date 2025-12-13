import cv2 as cv
import ffmpeg
import os

info = ffmpeg.probe("pymice-panel/e12fod05_epm_cut.mp4")
duration = float(info["format"]["duration"])

cap = cv.VideoCapture("pymice-panel/e12fod05_epm_cut.mp4")

# print('----------')
# print('Open CV')
# print(f'Qtd frames: {cap.get(cv.CAP_PROP_FRAME_COUNT)}\nFPS: {cap.get(cv.CAP_PROP_FPS)}\nDuração: {cap.get(cv.CAP_PROP_FRAME_COUNT)/cap.get(cv.CAP_PROP_FPS)}')
# print('----------\n')

# print('----------')
# print('Ffmpeg')
# print(f'Qtd frames: {}\nFPS: {}\nDuração: {duration}')
# print(info["format"])
# print('----------')
input_path = "pymice-panel/e12fod05_epm_cut.mp4"
output_path = "saida.mp4"

(
    ffmpeg
    .input(input_path)
    .output(output_path, c='copy')  # copia codec sem re-encodar
    .run()
)
