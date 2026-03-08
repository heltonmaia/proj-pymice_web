import os
import cv2
import json
import torch
import numpy as np
import matplotlib.pyplot as plt

from datetime import datetime
from ultralytics import YOLO
from pprint import pprint

# load model
model = YOLO("/home/marcos/projetos/pymice/proj-pymice_web/pymice-react/backend/temp/models/yolov11s_pose.pt")
model.to("cuda")

path = "/home/marcos/Downloads/pulosOF.mp4"
# path = "/home/marcos/Downloads/test_mice.mp4"

count_jump = 0
count_not_jump = 0
center = None

cap = cv2.VideoCapture(path)

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

radius = 380
jumps = []
standing = []

center = (width//2-75, height//2-25)
count = 0

final_frame = np.zeros((height, width))

out = cv2.VideoWriter(filename="output.avi", fourcc=cv2.VideoWriter_fourcc(*"XVID"), fps=cap.get(cv2.CAP_PROP_FPS), frameSize=(width//2, height//2))

while True:
    ret, frame = cap.read()

    if not ret or not cap.isOpened():
        break

    result = model(
        source=frame,
        verbose=False,
        device="cuda"
        )

    cv2.circle(frame, center, radius, (0, 0, 255), 3)


    try:
        print(123)
    except Exception as e:
        print('Erro: ', e)

    cv2.circle(frame, center, radius, (255, 0, 0), 3)
    frame = cv2.resize(frame, (width//2, height//2))


    cv2.putText(frame, f"Quantidade de pulos: {len(jumps)}", (10, 30), cv2.FONT_HERSHEY_COMPLEX_SMALL, 1, (0, 255, 0), 2)
    # cv2.putText(frame, f"Em pé na borda: {len(standing)}", (10, 50), cv2.FONT_HERSHEY_COMPLEX_SMALL, 1, (0, 255, 0), 2)
    cv2.imshow('window', frame)
    out.write(frame)

    if cv2.waitKey(1) & 0xff==27:
        break


    count+=1

cv2.destroyAllWindows()
out.release()
cap.release()

print(f"Quantidades de pulo {len(jumps)}")
print(f"Frames em que houve pulo {jumps}")
print(f"Quantidades de pulo {len(standing)}")
print(f"Frames em que houve pulo {standing}")