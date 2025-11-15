import json
import numpy as np
import matplotlib.pyplot as plt

def read_json_centers(json_path):
    
    with open(json_path,'r') as file:
        json_data = json.load(file)
        
        centers = [(roi['centroid_x'], roi['centroid_y']) for roi in json_data['tracking_data']]
        
    # print(centers)
    return centers
        
        
def calculate_speed():
    centers = read_json_centers('../tracking_data_2AF11_OF_low_1min.mp4_20251003T203317.json')
    
    dist = [0]
    # calculate manhattan distance
    for i in range(len(centers)-1):
        dist.append( np.sqrt((centers[i][0] - centers[i+1][0]) ** 2 + (centers[i][1] - centers[i+1][1]) ** 2) )
        
    dist = np.array(dist)
    
    # if number is less than 1 -> 0
    dist = np.where(dist<1, 0, dist)
    
    # analysis on mice movement
    mice_moving = np.where(dist>=1)
    mice_quiet = np.where(dist<1)
    
    movement_percentage = {'moving': np.count_nonzero(mice_moving), 'still': np.count_nonzero(mice_quiet)}
    
    fig, ax = plt.subplots(2,1, figsize=(10,5))
    ax[0].bar(range(len(dist)), dist)
    ax[0].set_title('Speed x Frames')
    ax[0].set_xlabel('Frames')
    ax[0].set_ylabel('Speed')
    
    ax[1].pie(movement_percentage.values(), labels=movement_percentage.keys(), autopct='%1.1f%%')
    ax[1].set_title('Mice movement')
    ax[1].legend(loc="best")
    plt.tight_layout()
    plt.show()
    
if __name__ == "__main__":
    calculate_speed()