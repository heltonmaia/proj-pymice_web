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

# paths = [os.path.join("/home/marcos/projetos/pymice/videos/mice_jumping_videos/mice_not_jumping", i) for i in os.listdir("/home/marcos/projetos/pymice/videos/mice_jumping_videos/mice_not_jumping")]
# paths = [os.path.join("/home/marcos/projetos/pymice/videos/mice_jumping_videos", i) for i in os.listdir("/home/marcos/projetos/pymice/videos/mice_jumping_videos")]
path = "/home/marcos/Downloads/pulosOF.mp4"
# path = "/home/marcos/Downloads/test_mice.mp4"

count_jump = 0
count_not_jump = 0
center = None

# for path in paths:

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


    keypoints = result[0].keypoints.data.cpu().numpy()
    kpts = keypoints[0]

    visible_kpts = kpts[:, 2]

    keypoints_data = [{"x": float(kpt[0]), "y": float(kpt[1]), "conf": float(kpt[2])} for kpt in kpts]

    if keypoints is not None:
        try: 
            x1, y1 = keypoints_data[0]['x'], keypoints_data[0]['y']
            # x2, y2 = keypoints_data[2]['x'], keypoints_data[2]['y']
            x2, y2 = keypoints_data[3]['x'], keypoints_data[3]['y']
            cv2.circle(frame, (int(x1), int(y1)), 3, (0, 0, 255), -1)
            cv2.circle(frame, (int(x2), int(y2)), 3, (0, 0, 255), -1)


            if np.sqrt((x1-center[0])**2 + (y1-center[1])**2) > (radius) and np.sqrt((x2-center[0])**2 + (y2-center[1])**2) > (radius):
                if len(jumps)==0:
                    jumps.append(count)
                    
                if (count - jumps[-1]) > 20:
                    jumps.append(count)

                print('+1 pulo')

            # if np.sqrt((x1-center[0])**2 + (y1-center[1])**2) > (radius) and np.sqrt((x2-center[0])**2 + (y2-center[1])**2) < (radius - 10):
            #     if len(standing)==0:
            #         standing.append(count)
                    
            #     if (count - standing[-1]) > 20:
            #         standing.append(count)
                
            #     print('+1 em pé')

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