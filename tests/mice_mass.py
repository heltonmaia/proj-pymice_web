from ultralytics import YOLO
import numpy as np
import cv2 as cv
import torch

print("Teste de segmentacao")
model = YOLO("src/pymicetracking_panel/tracking_tab/models/yolo_model.pt")

def mice_position(img):
    results = model.predict(img)

    try:
        x, y, w, h = results[0].boxes.xywh.cpu().numpy()[0]

        height, width, _ = img.shape
        center_point = np.array([(width)//2, (height)//2])

        # extract mask and apply on the image 
        mask_tensor = results[0].masks.data[0]
        mask = mask_tensor.cpu().numpy().astype(np.uint8) * 255  # converte para [0,255]
        mask = cv.resize(mask, (img.shape[1], img.shape[0]))  # mesmo tamanho da img
        mice = cv.bitwise_and(img, img, mask=mask)

        # auxiliar images
        mice_out = mice.copy()

        cv.circle(mice_out, center_point, 150, (0,0,0), -1)

        mice_in = mice - mice_out

        mass_total = np.count_nonzero(mice)
        mass_out = np.count_nonzero(mice_out)
        mass_in = np.count_nonzero(mice_in)

        cv.putText(mice, 'Pixels count: ' + str(mass_total), (10,50), cv.FONT_HERSHEY_COMPLEX_SMALL, 0.7, (0, 255, 0))

        cv.putText(mice_out, 'Pixels count: ' + str(mass_out), (10,50), cv.FONT_HERSHEY_COMPLEX_SMALL, 0.7, (0, 255, 0))
        cv.putText(mice_out, 'Percentage: ' + str(mass_out/mass_total*100) +"%", (10,70), cv.FONT_HERSHEY_COMPLEX_SMALL, 0.7, (0, 255, 0))

        cv.putText(mice_in, 'Pixels count: ' + str(mass_in), (10,50), cv.FONT_HERSHEY_COMPLEX_SMALL, 0.7, (0, 255, 0))
        cv.putText(mice_in, 'Percentage: ' + str(mass_in/mass_total*100) + "%", (10,70), cv.FONT_HERSHEY_COMPLEX_SMALL, 0.7, (0, 255, 0))

        percentage_in, percentage_out =  str(mass_in/mass_total*100) + "%", str(mass_out/mass_total*100) +"%"
        # return mice, mice_out, mice_in
        return percentage_in, percentage_out
    
    except Exception as e:
        print("Rato nao identificado")
        return "no mice", "no mice"

cap = cv.VideoCapture("2AF11_OF.mp4")

if not cap.isOpened():
    print("Erro ao abrir o vídeo!")
    exit()

width = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv.CAP_PROP_FPS)

output = cv.VideoWriter('video_out.mp4',
                         cv.VideoWriter_fourcc(*'mp4v'),  # Codec MP4
                         fps,
                         (2*width, height),
                         isColor=True)

while True:
    
    ret, img = cap.read()
    
    if not ret:
        break
    
    in_, out_= mice_position(img)
    
    cv.putText(img, 'Percentage in: ' + in_, (10,50), cv.FONT_HERSHEY_COMPLEX_SMALL, 0.7, (0, 255, 0))
    cv.putText(img, 'Percentage out: ' + out_, (10,70), cv.FONT_HERSHEY_COMPLEX_SMALL, 0.7, (0, 255, 0))
    
    
    cv.imshow('Original image', img)
  
    output.write(img)


    if cv.waitKey(1) & 0xff==27:
        break

cap.release()
output.release()
cv.destroyAllWindows()    
