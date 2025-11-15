"""
Detection functions for YOLO model loading and template matching
"""

import os
from typing import Optional, Tuple

import cv2 as cv
import numpy as np
from ultralytics import YOLO

DEFAULT_MODEL_NAME = "Default"
Point = Tuple[int,int]

def calculate_centroid(mask: np.ndarray) -> Optional[Point]:
    """
    Calculate the centroid of a mask.

    Args:
        mask (np.ndarray): Mask array.

    Returns:
        Point | None: Centroid coordinates (x, y) or None if no centroid is found.
    """

    moments = cv.moments(mask.astype(np.uint8))

    if moments["m00"] > 0:
        return (
            int(moments["m10"] / moments["m00"]),
            int(moments["m01"] / moments["m00"]),
        )

    return None


def template_matching(
    current_frame_gray: np.ndarray,
    background_frame: np.ndarray,
    roi_mask: Optional[np.ndarray] = None,
) -> Optional[Point]:
    """
    Perform template matching between current frame and background.

    Args:
        current_frame_gray: Current frame in grayscale
        background_frame: Background frame in grayscale
        roi_mask: Optional ROI mask to limit detection area

    Returns:
        Point | None: Centroid of detected object or None if not found
    """
    if background_frame is None:
        return None

    # Apply ROI mask if provided
    if roi_mask is not None:
        # Apply mask to the current frame gray
        masked_current_frame = cv.bitwise_and(
            current_frame_gray, current_frame_gray, mask=roi_mask
        )
        # Also apply the same mask to background for comparable processing
        masked_background = cv.bitwise_and(
            background_frame, background_frame, mask=roi_mask
        )

        # Compute absolute difference between masked current frame and masked background
        diff = cv.absdiff(masked_current_frame, masked_background)
    else:
        # Original behavior if no mask provided
        diff = cv.absdiff(current_frame_gray, background_frame)

    # Apply threshold to highlight significant differences
    _, thresh = cv.threshold(diff, 25, 255, cv.THRESH_BINARY)

    # Apply morphological operations to clean up the thresholded image
    kernel = np.ones((5, 5), np.uint8)
    thresh = cv.morphologyEx(thresh, cv.MORPH_OPEN, kernel, iterations=2)
    thresh = cv.morphologyEx(thresh, cv.MORPH_CLOSE, kernel, iterations=2)

    # Find contours in the thresholded image
    contours, _ = cv.findContours(thresh, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    # Get the largest contour
    largest_contour = max(contours, key=cv.contourArea)

    # Create a mask from the largest contour
    mask = np.zeros_like(current_frame_gray)
    cv.drawContours(mask, [largest_contour], -1, 255, -1)

    # Calculate centroid
    return calculate_centroid(mask)
