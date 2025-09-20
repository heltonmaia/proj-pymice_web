from ultralytics import YOLO
import torch
import cv2 as cv
import numpy as np

print("Teste de segmentacao")
model = YOLO("src/pymicetracking_panel/tracking_tab/models/yolo_model.pt")

results = model.predict("rato.png")

# for result in results:
    # print(result)

x, y, w, h = results[0].boxes.xywh.cpu().numpy()[0]

img = cv.imread("rato.png")

height, width, _ = img.shape
center_point = np.array([(width+14)//2, (height-26)//2])

# mascara de segmentacao
mask_tensor = results[0].masks.data[0]
mask = mask_tensor.cpu().numpy().astype(np.uint8) * 255  # converte para [0,255]
mask = cv.resize(mask, (img.shape[1], img.shape[0]))  # mesmo tamanho da img
rato = cv.bitwise_and(img, img, mask=mask)

# coordenadas
linhas, colunas = torch.nonzero(mask_tensor == 1, as_tuple=True)
coords = torch.stack([colunas, linhas], dim=1).cpu().numpy()

print(coords)

# distancias com o centro para comparar com o raio depois
distancias = np.linalg.norm(coords - center_point, axis=1)

# distancias calculadas - valor do raio, a mais proxima de 0 e a que leva às bordas
distancias = abs(distancias - 160)

# menor distancia para traçar o ponto na borda
print(f"Menor distancia: {distancias.min()}, index: {np.argmin(distancias)}, coord: {coords[np.argmin(distancias)]}")
                                  
# print()
# ponto_na_borda =  coords[np.argmin(distancias)][1], coords[np.argmin(distancias)][0]
# cv.circle(img, ponto_na_borda, 3, (0,0,255), 2)

# proximos_r = np.where(np.isclose(distancias, 160, atol=10))
# print(proximos_r)

# cv.circle(img, center_point, 79, (0,255,0), )
# cv.circle(img, center_point, 162, (0,0,0), -1)
# cv.imwrite("inner_circle.png", img)

inner_circle = cv.imread("inner_circle.png")
img_original = img
cp_img = img
img = img - inner_circle
cp_img = cp_img - img

mask_rato = np.all(img == rato, axis=-1)
and_img = np.zeros_like(img)
and_img[mask_rato] = img[mask_rato]

'''
    Descricao do que será feito:
    Processar a imagem original -> obter localização do polígono do rato
    Desenhar círculo interno -> subtrair da imagem -> rato que está fora do círculo
    Identificar qual parte do rato está dentro do círculo -> subtrair imagem rato fora do círculo da original
    Intersecção entre as coordenadas do polígono que estão fora e o rato
    
'''

while True:
    # cv.imshow("original", img_original)
    cv.imshow("interseccao do rato", and_img)
    cv.imshow("inner circle", img)
    cv.imshow("outer circle", cp_img)
    
    if cv.waitKey(1) & 0xff ==27:
        break
    
cv.destroyAllWindows()
