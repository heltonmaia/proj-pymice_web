import json
import cv2 as cv
import numpy as np
import matplotlib.pyplot as plt

from ultralytics import YOLO

model = YOLO("src/pymicetracking_panel/tracking_tab/models/yolo_model.pt")


'''
    Distancia = distancia entre os centros dos ratos
    Quantidade de frames = 30 fps/ 1 s * limiar delimitado pelo usuário
    
    Velocidade média = distancia / tempo (com base na quantidade de frames)
    -> coletar 'n' frames, fazer diferença entre os centros, dividir por quantidade de frames,
    armazenar num array/lista, comparar com o item de iterator anterior, julgar se houve mudança
    brusca ou não de acordo com um limiar experimental estabelecido.
     
'''

cap = cv.VideoCapture("e12fod05_epm_cut.mp4")

centros = []
dist = []
num_frames = 0

FRAMES_MAX = int(cap.get(cv.CAP_PROP_FRAME_COUNT))

while True:
    ret, frame = cap.read()
    
    if not ret: 
        break
    

    if num_frames%10 == 0:
        result = model.predict(frame)

        x, y, w, h = map(int, result[0].boxes.xywh.cpu().numpy()[0])

        cv.rectangle(frame, ((x-w), (y-h)), ((x+w), (y+h)), (0, 255, 0), 2)
        cv.circle(frame, (x,y), 2, (0, 0, 255), 1)
        centros.append((x,y))       
        
        if len(centros) > 1:
            # manhattan distance
            dist_temp = abs(centros[-1][0] - centros[-2][0]) + abs(centros[-1][0] - centros[-2][1])
            dist.append(dist_temp)

    if len(centros) > 1:
        cv.putText(frame, str(centros[-1]), (10, 120), cv.FONT_HERSHEY_COMPLEX_SMALL, 1.5, (255, 0, 0), 2)
        
    if len(dist) > 1:
        cv.putText(frame, str(dist[-1]), (10, 180), cv.FONT_HERSHEY_COMPLEX_SMALL, 1.5, (255, 255, 0), 2)
        cv.putText(frame, str(dist[-2]), (10, 240), cv.FONT_HERSHEY_COMPLEX_SMALL, 1.5, (255, 255, 0), 2)
        
        # if abs(dist[-1] - dist[-2]) < 10000:
    #         cv.putText(frame, f'Diferencas nao significativa ' + str(dist[-1] - dist[-2]), (10, 300), cv.FONT_HERSHEY_COMPLEX_SMALL, 1.5, (255, 0, 255), 2)
    #     else:
    #         cv.putText(frame, f'Diferencas: ' + str(dist[-1] - dist[-2]), (10, 300), cv.FONT_HERSHEY_COMPLEX_SMALL, 1.5, (255, 0, 255), 2)
        
    cv.putText(frame, str(num_frames), (10,50), cv.FONT_HERSHEY_COMPLEX_SMALL, 1.5, (0, 0, 255), 2)    
    cv.imshow('Window', frame)

    print(f'Frame: {num_frames}')    
    
    if cv.waitKey(1) & 0xff == 27:
        break
    
    num_frames += 1
    
cv.destroyAllWindows()
cap.release()

frames = list(range(len(dist)))

plt.figure(figsize=(8, 4))
plt.bar(frames, dist)
plt.xlabel('Quantidade de frames')
plt.ylabel('Diferenca entre os centros')
plt.show()