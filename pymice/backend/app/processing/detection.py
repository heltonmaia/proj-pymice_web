"""Detection utilities for tracking"""

import cv2
import numpy as np
from typing import Optional, Tuple

Point = Tuple[int, int]


def calculate_centroid(mask: np.ndarray) -> Optional[Point]:
    """
    Calculate centroid of a binary mask using image moments.

    Args:
        mask: Binary mask (uint8 array with 0 and 255 values)

    Returns:
        Tuple of (center_x, center_y) or None if mask is empty
    """
    moments = cv2.moments(mask.astype(np.uint8))

    if moments["m00"] > 0:
        center_x = int(moments["m10"] / moments["m00"])
        center_y = int(moments["m01"] / moments["m00"])
        return (center_x, center_y)

    return None


def template_matching(
    current_frame: np.ndarray,
    background_frame: np.ndarray,
    roi_mask: Optional[np.ndarray] = None,
    threshold: int = 25,
) -> Optional[Point]:
    """
    Detect animal using background subtraction and template matching.

    Args:
        current_frame: Current video frame (BGR)
        background_frame: Background reference frame (grayscale)
        roi_mask: Optional ROI mask to limit detection area
        threshold: Threshold for difference detection (default: 25)

    Returns:
        Tuple of (center_x, center_y) or None if no detection
    """
    # Convert current frame to grayscale
    gray_frame = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)

    # Apply ROI mask if provided
    if roi_mask is not None:
        gray_frame = cv2.bitwise_and(gray_frame, gray_frame, mask=roi_mask)
        masked_background = cv2.bitwise_and(background_frame, background_frame, mask=roi_mask)
    else:
        masked_background = background_frame

    # Calculate absolute difference
    diff = cv2.absdiff(gray_frame, masked_background)

    # Apply threshold
    _, binary = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)

    # Morphological operations to clean up
    kernel = np.ones((3, 3), np.uint8)

    # Remove small noise
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=2)

    # Fill small holes
    closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel, iterations=2)

    # Find contours
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    # Find largest contour (assumed to be the animal)
    largest_contour = max(contours, key=cv2.contourArea)

    # Create mask from largest contour
    mask = np.zeros_like(binary)
    cv2.drawContours(mask, [largest_contour], -1, 255, -1)

    # Calculate centroid
    return calculate_centroid(mask)
