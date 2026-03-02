from ultralytics import YOLO
import cv2
import numpy as np
import time

model = YOLO('/home/marcos/projetos/pymice/proj-pymice_web/pymice-react/backend/temp/models/mice_hybrid_best.pt')

cap = cv2.VideoCapture('/home/marcos/projetos/tests/white.mp4')

fps = cap.get(cv2.CAP_PROP_FPS)
frame = None
width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

out = cv2.VideoWriter('out_mask.mp4', cv2.VideoWriter_fourcc(*'MP4V'), fps, (width, height))

while cap.isOpened():
    ret, frame = cap.read()

    results = model(frame)
    dest = frame

    try:
        mask = results[0].masks.data[0].cpu().numpy()
        mask = cv2.resize(mask, (width, height))

        mask_bgr = np.zeros((height, width, 3), dtype=np.uint8)
        mask_bgr[mask > 0] = (255, 0, 0)
        
        dest = cv2.addWeighted(frame, 0.7, mask_bgr, 0.3, 0.0)
        cv2.putText(dest, f'Class: {results[0].names}', (10, 30), cv2.FONT_HERSHEY_COMPLEX_SMALL, 1.4, (255, 0, 0), 2)
    except:
        print('Not found!')

    if not ret:
        break

    cv2.imshow('Window', dest)
    
    out.write(dest)

    if cv2.waitKey(1) & 0xff==27:
        break
    
    time.sleep(1/fps)

out.release()
cap.release()
cv2.destroyAllWindows()