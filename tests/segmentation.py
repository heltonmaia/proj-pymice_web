from ultralytics import YOLO
import torch
import cv2 as cv
import numpy as np

print("Teste de segmentacao")
model = YOLO("src/pymicetracking_panel/tracking_tab/models/yolo_model.pt")

results = model.predict("rato.png")

# for result in results:
    # print(result)
    
img = cv.imread("rato.png")

height, width, _ = img.shape
center_point = np.array([(width+14)//2, (height-26)//2])
# print(img.shape)

# mascara de segmentacao
mask_tensor = results[0].masks.data[0]
mask = mask_tensor.cpu().numpy().astype(np.uint8) * 255  # converte para [0,255]
mask = cv.resize(mask, (img.shape[1], img.shape[0]))  # mesmo tamanho da img
# img = cv.bitwise_and(img, img, mask=mask)

# coordenadas
linhas, colunas = torch.nonzero(mask_tensor == 1, as_tuple=True)
coords = torch.stack([colunas, linhas], dim=1).cpu().numpy()

# distancias com o centro para comparar com o raio depois
distancias = np.linalg.norm(coords - center_point, axis=1)

# distancias calculadas - valor do raio, a mais proxima de 0 e a que leva às bordas
distancias = abs(distancias - 160)

# menor distancia para traçar o ponto na borda
print(f"Menor distancia: {distancias.min()}, index: {np.argmin(distancias)}, coord: {coords[np.argmin(distancias)]}")
                                  
ponto_na_borda =  coords[np.argmin(distancias)][0], coords[np.argmin(distancias)][1]
cv.circle(img, ponto_na_borda, 3, (0,0,255), 2)

proximos_r = np.where(np.isclose(distancias, 180, atol=10))[0]

# cv.circle(img, center_point, 79, (0,255,0), 3)
cv.circle(img, center_point, 160, (0,255,0), 2)



while True:
    cv.imshow("imagem", img)
    
    if cv.waitKey(1) & 0xff ==27:
        break
    
cv.destroyAllWindows()
