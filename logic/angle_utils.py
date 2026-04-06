import numpy as np

def calculate_angle(a, b, c):
    
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)

    radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - \
              np.arctan2(a[1] - b[1], a[0] - b[0])
    
    angle = np.abs(radians * 180.0 / np.pi)
    
    if angle > 180.0:
        angle = 360 - angle
    
    return round(angle, 2)


def get_joint_angles(landmarks):
    """
    Compute key joint angles from a landmarks dict.
    Each landmark must have 'x' and 'y' keys (normalised 0-1 image coords).
    Returns a dict mapping angle name → degrees (float).
    """
    def get_point(name):
        lm = landmarks.get(name)
        if lm is None:
            return None        # MediaPipe provides a visibility score for each landmark.
        # If the joint is not reliably seen, ignore it.
        vis = lm.get('visibility', 1.0)
        if vis < 0.5:
            return None        return [lm['x'], lm['y']]

    angles = {}

    left_hip       = get_point('left_hip')
    left_knee      = get_point('left_knee')
    left_ankle     = get_point('left_ankle')
    right_hip      = get_point('right_hip')
    right_knee     = get_point('right_knee')
    right_ankle    = get_point('right_ankle')
    left_shoulder  = get_point('left_shoulder')
    right_shoulder = get_point('right_shoulder')
    left_elbow     = get_point('left_elbow')
    left_wrist     = get_point('left_wrist')
    right_elbow    = get_point('right_elbow')
    right_wrist    = get_point('right_wrist')

    # Knee angles (hip → knee → ankle)
    if left_hip is not None and left_knee is not None and left_ankle is not None:
        angles['left_knee'] = calculate_angle(left_hip, left_knee, left_ankle)
    if right_hip is not None and right_knee is not None and right_ankle is not None:
        angles['right_knee'] = calculate_angle(right_hip, right_knee, right_ankle)

    # Hip angles (shoulder → hip → knee)
    if left_shoulder is not None and left_hip is not None and left_knee is not None:
        angles['left_hip'] = calculate_angle(left_shoulder, left_hip, left_knee)
    if right_shoulder is not None and right_hip is not None and right_knee is not None:
        angles['right_hip'] = calculate_angle(right_shoulder, right_hip, right_knee)

    # Back / torso inclination angle
    # Measures how upright the spine is: 180° = perfectly vertical, decreases as torso leans forward.
    # Uses mid-shoulder → mid-hip vs a virtual point directly below mid-hip (image y↓).
    if left_shoulder is not None and right_shoulder is not None and left_hip is not None and right_hip is not None:
        mid_shoulder  = [(left_shoulder[0] + right_shoulder[0]) / 2,
                         (left_shoulder[1] + right_shoulder[1]) / 2]
        mid_hip       = [(left_hip[0] + right_hip[0]) / 2,
                         (left_hip[1] + right_hip[1]) / 2]
        virtual_below = [mid_hip[0], mid_hip[1] + 0.1]
        angles['back'] = calculate_angle(mid_shoulder, mid_hip, virtual_below)
    elif left_shoulder is not None and left_hip is not None:
        # Fallback to single-side estimate when one side is occluded
        virtual_below = [left_hip[0], left_hip[1] + 0.1]
        angles['back'] = calculate_angle(left_shoulder, left_hip, virtual_below)

    # Elbow angles (shoulder → elbow → wrist)
    if all([left_shoulder, left_elbow, left_wrist]):
        angles['left_elbow'] = calculate_angle(left_shoulder, left_elbow, left_wrist)
    if all([right_shoulder, right_elbow, right_wrist]):
        angles['right_elbow'] = calculate_angle(right_shoulder, right_elbow, right_wrist)

    return angles


# --- TEST ---
if __name__ == "__main__":
    # A straight line should give 180 degrees
    a = [0, 0]
    b = [1, 0]
    c = [2, 0]
    print(f"Straight line angle (expect 180): {calculate_angle(a, b, c)}")

    # A right angle should give 90 degrees
    a = [0, 1]
    b = [0, 0]
    c = [1, 0]
    print(f"Right angle (expect 90): {calculate_angle(a, b, c)}")

    # Simulate a squat position
    print("\n--- Simulated Squat Landmarks ---")
    fake_landmarks = {
        "left_hip":      {"x": 0.42, "y": 0.51},
        "left_knee":     {"x": 0.41, "y": 0.65},
        "left_ankle":    {"x": 0.40, "y": 0.80},
        "right_hip":     {"x": 0.58, "y": 0.51},
        "right_knee":    {"x": 0.57, "y": 0.65},
        "right_ankle":   {"x": 0.56, "y": 0.80},
        "left_shoulder": {"x": 0.42, "y": 0.35},
        "right_shoulder":{"x": 0.58, "y": 0.35},
        "left_elbow":    {"x": 0.35, "y": 0.50},
        "left_wrist":    {"x": 0.30, "y": 0.65},
        "right_elbow":   {"x": 0.65, "y": 0.50},
        "right_wrist":   {"x": 0.70, "y": 0.65},
    }

    angles = get_joint_angles(fake_landmarks)
    for joint, angle in angles.items():
        print(f"  {joint}: {angle}°")