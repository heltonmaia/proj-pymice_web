import json
import cv2 as cv
import numpy as np
import matplotlib.pyplot as plt

from pymicetracking_panel.tracking_tab.processing.detection import calculate_centroid
from pymicetracking_panel.tracking_tab.processing.tracking import process_frame

from scipy.signal import find_peaks
from ultralytics import YOLO

'''
    dist = entre os centers dos ratos
    Quantidade de frames = 30 fps/ 1 s * limiar delimitado pelo usuário
    
    Velocidade média = dist_manancia / tempo (com base na quantidade de frames)
    -> coletar 'n' frames, fazer diferença entre os centers, dividir por quantidade de frames,
    armazenar num array/lista, comparar com o item de iterator anterior, julgar se houve mudança
    brusca ou não de acordo com um limiar experimental estabelecido.
     
'''

model = YOLO("src/pymicetracking_panel/tracking_tab/models/yolo_model.pt")
FRAMES_SAMPLE = 500

cap = cv.VideoCapture("e12fod05_epm_cut.mp4")
centers = []
dist_man = []
dist_euc = []
num_frames = 0

#############################################################################################################################################################
def calculate_speed(frame: np.ndarray, num_frames: int):
    results = model.predict(frame)
    frame_height, frame_width, _ = frame.shape
    
    if results and len(results) > 0:
        if (
            hasattr(results[0], "masks")
            and results[0].masks is not None
            and len(results[0].masks) > 0
            and hasattr(results[0], "boxes")
            and results[0].boxes is not None
            and len(results[0].boxes.conf) > 0
        ):
            # Ensure we don't access beyond available masks
            conf_array = results[0].boxes.conf.cpu().numpy()
            num_masks = len(results[0].masks.data)
            
            # Only consider confidences for available masks
            if len(conf_array) > num_masks:
                conf_array = conf_array[:num_masks]
            
            if len(conf_array) > 0:
                best_idx = np.argmax(conf_array)
                
                if best_idx < num_masks:
                    best_mask_tensor = results[0].masks.data[best_idx].cpu()

                    best_mask = cv.resize(
                        best_mask_tensor.numpy(),
                        (frame_width, frame_height),
                        interpolation=cv.INTER_NEAREST,
                    )

                    binary_mask = (best_mask > 0.5).astype(np.uint8)
                    centroid = calculate_centroid(binary_mask)
                    
                    centers.append(centroid)
        
            if len(centers) > 1:
                # manhattan dist_manance
                dist_man_temp = abs(centers[-1][0] - centers[-2][0]) + abs(centers[-1][1] - centers[-2][1])
                dist_man.append(dist_man_temp)
                dist_euc_temp = ((centers[-1][0] - centers[-2][0])**2 + (centers[-1][1] - centers[-2][1])**2) ** (1/2)
                dist_euc.append(dist_euc_temp)
            
            if len(centers) > 1:
                cv.putText(frame, str(centers[-1]), (10, 120), cv.FONT_HERSHEY_COMPLEX_SMALL, 1.5, (255, 0, 0), 2)
                
            if len(dist_man) > 1:
                cv.putText(frame, str(dist_man[-1]), (10, 180), cv.FONT_HERSHEY_COMPLEX_SMALL, 1.5, (255, 255, 0), 2)
                cv.putText(frame, str(dist_man[-2]), (10, 240), cv.FONT_HERSHEY_COMPLEX_SMALL, 1.5, (255, 255, 0), 2)    
    
           
    return centroid 
#############################################################################################################################################################
frame, _ = cap.read()

x, y = 0, 0

while True:
    ret, frame = cap.read()
    
    if not ret: 
        break
    
    if num_frames%FRAMES_SAMPLE == 0:
        x, y = calculate_speed(frame, num_frames)
        
    cv.circle(frame, (x,y), 2, (0, 0, 255), 1)
    cv.putText(frame, str(num_frames), (10,50), cv.FONT_HERSHEY_COMPLEX_SMALL, 1.5, (0, 0, 255), 2)
    cv.imshow('Mice image', frame)
    
    if cv.waitKey(1) & 0xff == 27:
        break
    
    num_frames += 1
    
cv.destroyAllWindows()
cap.release()

frames = list(range(len(dist_man)))
dist_man = np.array(dist_man, dtype=np.float16)
dist_man = np.array(dist_man/np.max(dist_man))


fig, axis = plt.subplots(2,3, figsize=(8,4))

# picos_80 = []
# picos_40 = []
# for i in range(1,len(dist_euc)):
#     if abs(dist_euc[i-1] - dist_euc[i]) > 80:
#         print(f"PICO DE VELOCIDADE NO FRAME {i}")
#         picos_80.append(1)
#     else:
#         picos_80.append(0)
        
#     if abs(dist_euc[i-1] - dist_euc[i]) > 40:
#         print(f"PICO DE VELOCIDADE NO FRAME {i}")
#         picos_40.append(1)
#     else:
#         picos_40.append(0)

eixo_x = [c[0] for c in centers]
axis[0][0].bar(list(range(len(centers))), eixo_x, color='blue')
axis[0][0].set_xlabel(f'Quantidade de frames (em multiplos de {FRAMES_SAMPLE})')
axis[0][0].set_ylabel('X - Centro')

eixo_y = [c[1] for c in centers]
axis[0][1].bar(list(range(len(centers))), eixo_y, color='red')
axis[0][1].set_xlabel(f'Quantidade de frames (em multiplos de {FRAMES_SAMPLE})')
axis[0][1].set_ylabel('Y - Centro')

# # axis[0][2].bar(list(range(len(picos_80))), picos_80, color='pink')
# # axis[0][2].set_xlabel('Presenca de picos limiar = 80')
# # axis[0][2].set_ylabel('Valor')

# axis[1][0].bar(frames, dist_man, color='purple')
# axis[1][0].set_xlabel('Quantidade de frames (em multiplos de 15)')
# axis[1][0].set_ylabel('Distancia Manhattan entre os centers')

# axis[1][1].bar(frames, dist_euc, color='green')
# axis[1][1].set_xlabel('Quantidade de frames (em multiplos de 15)')
# axis[1][1].set_ylabel('Distancia Euclidiana entre os centers')

# # axis[1][2].plot(list(range(len(picos_40))), picos_40, color='pink')
# # axis[1][2].set_xlabel('Presenca de picos limiar = 40')
# # axis[1][2].set_ylabel('Valor')

dist_euc = np.array(dist_euc)
peaks_indices, _ = find_peaks(dist_euc, height=0.4)
peaks_indices = np.array(peaks_indices, dtype=int) #, dist_euc)
print(dist_euc[peaks_indices])

axis[1][2].plot(peaks_indices, dist_euc[peaks_indices], "x", color='red', label='picos')
axis[1][2].set_xlabel('Presenca de picos limiar = 40')
axis[1][2].set_ylabel('Valor')

plt.tight_layout()
plt.show()
