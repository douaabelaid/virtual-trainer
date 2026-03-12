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
    
    def get_point(name):
        lm = landmarks.get(name)
        if lm is None:
            return None
        return [lm['x'], lm['y']]

    angles = {}

    # Left knee angle (hip -> knee -> ankle)
    left_hip = get_point('left_hip')
    left_knee = get_point('left_knee')
    left_ankle = get_point('left_ankle')
    if all([left_hip, left_knee, left_ankle]):
        angles['left_knee'] = calculate_angle(left_hip, left_knee, left_ankle)

    # Right knee angle
    right_hip = get_point('right_hip')
    right_knee = get_point('right_knee')
    right_ankle = get_point('right_ankle')
    if all([right_hip, right_knee, right_ankle]):
        angles['right_knee'] = calculate_angle(right_hip, right_knee, right_ankle)

    # Left hip angle (shoulder -> hip -> knee)
    left_shoulder = get_point('left_shoulder')
    if all([left_shoulder, left_hip, left_knee]):
        angles['left_hip'] = calculate_angle(left_shoulder, left_hip, left_knee)

    # Right hip angle
    right_shoulder = get_point('right_shoulder')
    if all([right_shoulder, right_hip, right_knee]):
        angles['right_hip'] = calculate_angle(right_shoulder, right_hip, right_knee)

    # Back angle (left shoulder -> left hip -> left knee)
    if all([left_shoulder, left_hip, left_knee]):
        angles['back'] = calculate_angle(left_shoulder, left_hip, left_knee)

    # Left elbow angle (shoulder -> elbow -> wrist)
    left_elbow = get_point('left_elbow')
    left_wrist = get_point('left_wrist')
    if all([left_shoulder, left_elbow, left_wrist]):
        angles['left_elbow'] = calculate_angle(left_shoulder, left_elbow, left_wrist)

    # Right elbow angle
    right_elbow = get_point('right_elbow')
    right_wrist = get_point('right_wrist')
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