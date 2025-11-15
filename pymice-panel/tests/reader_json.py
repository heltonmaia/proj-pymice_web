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
        
        for i in img_list:    
            frame, center, radius = i
            center = tuple(map(int, center))
            radius = int(radius)
           
            # auxiliar images
            mice_out = mice.copy()

            # draw a circle on the image mice_out
            cv.circle(mice_out, center, radius, (0,0,0), -1)
            cv.circle(img, center, radius, (0,255,0), 2)

            mice_in = mice - mice_out

            mass_out = np.count_nonzero(mice_out)/float(mass_total)
            mass_in = np.count_nonzero(mice_in)/float(mass_total)
            
            print(mass_total/float(mass_total), mass_in, mass_out)
            
            if mass_out > 0.6:
                print("Mice jumped")
                cv.putText(img, "Jumped", (10,50), cv.FONT_HERSHEY_COMPLEX_SMALL, 0.5,  (0,255,0), 2)
            elif 0.3 <=mass_out <= 0.6:
                print("Mice standing")
                cv.putText(img, "Standing", (10,50), cv.FONT_HERSHEY_COMPLEX_SMALL, 0.5, (0,255,0), 2)
            else:
                print("Mice inside the circle")
                cv.putText(img, "Inside", (10,50), cv.FONT_HERSHEY_COMPLEX_SMALL, 0.5, (0,255,0), 2)
            # circle_mask to draw a circle
            # circle_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
            # cv.circle(circle_mask, center, radius, 255, -1)

            # frame = cv.bitwise_and(frame, mice)
            
            # applying mask to frame - mice inside the circle
            # frame = cv.bitwise_and(frame, frame, mask=circle_mask)
            
            # cv.imshow(f'Janela {j}', mice_out)
            # j+=1           

            return img
    except Exception as e:
        print(f"Error in GetArea Function: {e}")        
    
    
# img = cv.imread("rato_modelagem.png")    
# results = model.predict(img)  

# store mouse position  
mice = None

try:
    # capture video
    cap = cv.VideoCapture('2AF11_OF.mp4')
    
    # creating video file
    frame_width = int(cap.get(3))
    frame_height = int(cap.get(4))
    fps = cap.get(cv.CAP_PROP_FPS)
    fourcc = cv.VideoWriter_fourcc(*'mp4v') 
    out = cv.VideoWriter('output.mp4', fourcc, fps, (frame_width, frame_height))

 
    
    while True:
        ret, img = cap.read()
    
        if not ret: break
        
        if cv.waitKey(1) & 0xff==27: break
        
        results = model.predict(img)  
    
        x, y, w, h = results[0].boxes.xywh.cpu().numpy()[0]

        height, width, _ = img.shape
        center_point = np.array([(width)//2, (height)//2])

        # extract circle_mask and apply on the image 
        circle_mask_tensor = results[0].masks.data[0]
        circle_mask = circle_mask_tensor.cpu().numpy().astype(np.uint8) * 255
        circle_mask = cv.resize(circle_mask, (img.shape[1], img.shape[0]))
        mice = cv.bitwise_and(img, img, mask=circle_mask)
        img = get_area(img, mice, "tests/rois_data_example_1_circle.json")
        # cv.imshow('testing', img)
        out.write(img)
        
    cap.release()
    out.release()
    cv.destroyAllWindows()
    
except Exception as e:
    print(f"Error: {e}")
