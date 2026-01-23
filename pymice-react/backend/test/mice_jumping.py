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
paths = [os.path.join("/home/marcos/projetos/pymice/videos/mice_jumping_videos", i) for i in os.listdir("/home/marcos/projetos/pymice/videos/mice_jumping_videos")]

not_jumping = len(paths)
jumping = len(paths)

count_jump = 0
count_not_jump = 0

for path in paths:
    if not path.endswith(".mp4"):
        continue
    
    cap = cv2.VideoCapture(path)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    center = (width//2 - 80, height//2 - 20)
    radius = 375

    jump = False

    while True:
        ret, frame = cap.read()

        if not ret or not cap.isOpened():
            break

        result = model(
            source=frame,
            verbose=False,
            device="cuda"
            )

        keypoints = result[0].keypoints.data.cpu().numpy()
        kpts = keypoints[0]

        visible_kpts = kpts[:, 2]

        keypoints_data = [{"x": float(kpt[0]), "y": float(kpt[1]), "conf": float(kpt[2])} for kpt in kpts]

        if keypoints is not None:
            try: 
                x1, y1 = keypoints_data[0]['x'], keypoints_data[0]['y']
                x2, y2 = keypoints_data[3]['x'], keypoints_data[3]['y']
                cv2.circle(frame, (int(x1), int(y1)), 3, (0, 0, 255), -1)
                cv2.circle(frame, (int(x2), int(y2)), 3, (0, 0, 255), -1)


                if np.sqrt((x1-center[0])**2 + (y1-center[1])**2) > (radius + 10) and np.sqrt((x2-center[0])**2 + (y2-center[1])**2) > (radius + 10):
                    jump = True

            except Exception as e:
                print('Erro: ', e)

        cv2.circle(frame, center, radius, (255, 0, 0), 3)
        frame = cv2.resize(frame, (width//2, height//2))


        cv2.imshow('window', frame)

        if cv2.waitKey(1) & 0xff==27:
            break

    cv2.destroyAllWindows()
    cap.release()

    if(jump):
        print(f'{path} : pulou')
        count_jump +=1
        continue
    
    count_not_jump +=1
    print(f'{path} : nao pulou')

print(f"Acertos: {count_jump/jumping}")
# print(f"Acertos: {count_not_jump/not_jumping}")