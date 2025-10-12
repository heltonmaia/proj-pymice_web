import json
import cv2 as cv
import numpy as np
import time

from ultralytics import YOLO

model = YOLO("src/pymicetracking_panel/tracking_tab/models/yolo_model.pt")

def get_area(img, mice, json_path):
    json_data = None

    img_list = []

    try:
        
        with open(json_path, "r") as file:
            json_data = json.load(file)

        # image, center and radius
        img_list = [[img.copy(), (json_data[i]['center_x'], json_data[i]['center_y']), json_data[i]['radius']] for i in range(len(json_data))]
                
        mass_total = np.count_nonzero(mice)
        print(f"Total: {mass_total}")

        j = 0
        
        for i in img_list:    
            frame, center, radius = i
            center = tuple(map(int, center))
            radius = int(radius)
            
            # circle_mask to draw a circle
            circle_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
            cv.circle(circle_mask, center, radius, 255, -1)
            
            # applying mask to frame
            frame = cv.bitwise_and(frame, frame, mask=circle_mask)

            # ideia: complementar - interseccao entre o rato e a imagem  
            frame = cv.bitwise_and(frame, mice)
            
            print(np.count_nonzero(frame)/np.count_nonzero(mice))
            
            
            cv.imshow(f'Janela {j}', frame)
            j+=1           
    
    except Exception as e:
        print(f"Error in GetArea Function: {e}")        
    
    
img = cv.imread("rato_modelagem.png")    
results = model.predict(img)  

# store mouse position  
mice = None

try:
    x, y, w, h = results[0].boxes.xywh.cpu().numpy()[0]

    height, width, _ = img.shape
    center_point = np.array([(width)//2, (height)//2])

    # extract circle_mask and apply on the image 
    circle_mask_tensor = results[0].masks.data[0]
    circle_mask = circle_mask_tensor.cpu().numpy().astype(np.uint8) * 255
    circle_mask = cv.resize(circle_mask, (img.shape[1], img.shape[0]))
    mice = cv.bitwise_and(img, img, mask=circle_mask)

except Exception as e:
    print(f"Error: {e}")

if mice is not None:
    cv.imshow("Rato", mice)

    get_area(img, mice, "tests/rois_data_example.json")

    while True:   
        if cv.waitKey(1) & 0xff==27:
            break
    cv.destroyAllWindows()