import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logic.angle_utils import get_joint_angles
from shared.exercise_state_schema import (
    ExerciseState, ExerciseType, ExerciseStage,
    FeedbackFlag, FeedbackSeverity, JointAngles
)
import time

# --- Angle Thresholds ---

THRESHOLDS = {
    "squat": {
        "down":     {"left_knee": 95,  "right_knee": 95},
        "standing": {"left_knee": 160, "right_knee": 160},
    },
    "pushup": {
        "down":     {"left_elbow": 90,  "right_elbow": 90},
        "standing": {"left_elbow": 160, "right_elbow": 160},
    },
    "lunge": {
        "down":     {"left_knee": 90,  "right_knee": 90},
        "standing": {"left_knee": 160, "right_knee": 160},
    }
}


class ExerciseDetector:
    def __init__(self, exercise: str = "squat"):
        self.exercise = ExerciseType(exercise)
        self.stage = ExerciseStage.STANDING
        self.rep_count = 0
        self._was_down = False   # tracks that we reached DOWN in the current rep

    def reset(self):
        """Reset rep count and stage (e.g., when switching exercises or starting a new set)."""
        self.stage = ExerciseStage.STANDING
        self.rep_count = 0
        self._was_down = False

    def detect_stage(self, angles: dict) -> ExerciseStage:
        thresholds = THRESHOLDS[self.exercise.value]

        if self.exercise in (ExerciseType.SQUAT, ExerciseType.LUNGE):
            left_knee = angles.get("left_knee", 180)
            right_knee = angles.get("right_knee", 180)

            if self.exercise == ExerciseType.SQUAT:
                # Both legs bend equally — use the average
                avg_knee = (left_knee + right_knee) / 2
            else:
                # Lunge — only the front (most bent) leg matters
                avg_knee = min(left_knee, right_knee)

            if avg_knee < thresholds["down"]["left_knee"]:
                return ExerciseStage.DOWN
            elif avg_knee > thresholds["standing"]["left_knee"]:
                return ExerciseStage.STANDING
            else:
                return ExerciseStage.TRANSITION

        elif self.exercise == ExerciseType.PUSHUP:
            left_elbow = angles.get("left_elbow", 180)
            right_elbow = angles.get("right_elbow", 180)
            avg_elbow = (left_elbow + right_elbow) / 2

            if avg_elbow < thresholds["down"]["left_elbow"]:
                return ExerciseStage.DOWN
            elif avg_elbow > thresholds["standing"]["left_elbow"]:
                return ExerciseStage.STANDING
            else:
                return ExerciseStage.TRANSITION

        return ExerciseStage.STANDING

    def update(self, landmarks: dict) -> ExerciseState:
        # Step 1 — calculate angles
        angles = get_joint_angles(landmarks)

        # Step 2 — detect current stage
        new_stage = self.detect_stage(angles)

        # Step 3 — count rep: any DOWN stage followed by STANDING = 1 rep
        # Uses _was_down so DOWN → TRANSITION → STANDING also counts.
        if new_stage == ExerciseStage.DOWN:
            self._was_down = True
        if self._was_down and new_stage == ExerciseStage.STANDING:
            self.rep_count += 1
            self._was_down = False

        self.stage = new_stage

        # Step 4 — check for feedback
        feedback = self.check_feedback(angles)

        # Step 5 — build and return ExerciseState
        return ExerciseState(
            timestamp_ms=int(time.time() * 1000),
            exercise=self.exercise,
            stage=self.stage,
            rep_count=self.rep_count,
            joint_angles=JointAngles(**angles),
            feedback_flags=feedback,
            landmarks_raw=landmarks
        )

    def check_feedback(self, angles: dict) -> list:
        flags = []

        if self.exercise == ExerciseType.SQUAT:
            left_knee  = angles.get("left_knee")
            right_knee = angles.get("right_knee")

            # Knee alignment: warn if left and right diverge significantly
            if left_knee and right_knee:
                if abs(left_knee - right_knee) > 15:
                    flags.append(FeedbackFlag(
                        code="KNEE_CAVE",
                        message="Left knee caving inward",
                        severity=FeedbackSeverity.WARNING
                    ))

            # Depth check only when at the bottom of the movement
            if self.stage == ExerciseStage.DOWN:
                avg_knee = ((left_knee or 180) + (right_knee or 180)) / 2
                if avg_knee > 110:
                    flags.append(FeedbackFlag(
                        code="TOO_SHALLOW",
                        message="Squat not deep enough",
                        severity=FeedbackSeverity.WARNING
                    ))
                else:
                    flags.append(FeedbackFlag(
                        code="DEPTH_OK",
                        message="Good depth",
                        severity=FeedbackSeverity.INFO
                    ))

            # Back check only during active movement (not neutral standing)
            if self.stage in (ExerciseStage.DOWN, ExerciseStage.TRANSITION):
                back = angles.get("back")
                if back is not None and back < 150:
                    flags.append(FeedbackFlag(
                        code="BACK_ANGLE",
                        message="Keep your back straight",
                        severity=FeedbackSeverity.WARNING
                    ))

        elif self.exercise == ExerciseType.PUSHUP:
            left_elbow  = angles.get("left_elbow")
            right_elbow = angles.get("right_elbow")

            # Elbow symmetry check
            if left_elbow and right_elbow:
                if abs(left_elbow - right_elbow) > 15:
                    flags.append(FeedbackFlag(
                        code="ELBOW_FLARE",
                        message="Keep elbows even",
                        severity=FeedbackSeverity.WARNING
                    ))

            # Depth check only at the bottom of the push-up
            if self.stage == ExerciseStage.DOWN:
                avg_elbow = ((left_elbow or 180) + (right_elbow or 180)) / 2
                if avg_elbow > 110:
                    flags.append(FeedbackFlag(
                        code="PUSHUP_TOO_SHALLOW",
                        message="Go lower — chest closer to the ground",
                        severity=FeedbackSeverity.WARNING
                    ))
                else:
                    flags.append(FeedbackFlag(
                        code="DEPTH_OK",
                        message="Good depth",
                        severity=FeedbackSeverity.INFO
                    ))

        elif self.exercise == ExerciseType.LUNGE:
            left_knee  = angles.get("left_knee")
            right_knee = angles.get("right_knee")

            # Check both knees — whichever is the lead knee should not pass the ankle
            if left_knee is not None and left_knee < 80:
                flags.append(FeedbackFlag(
                    code="KNEE_TOO_FORWARD",
                    message="Front knee too far forward",
                    severity=FeedbackSeverity.WARNING
                ))
            if right_knee is not None and right_knee < 80:
                flags.append(FeedbackFlag(
                    code="KNEE_TOO_FORWARD",
                    message="Front knee too far forward",
                    severity=FeedbackSeverity.WARNING
                ))

        # Emit GOOD_FORM when in the DOWN stage with no active warnings or errors
        has_issue = any(
            f.severity in (FeedbackSeverity.WARNING, FeedbackSeverity.ERROR)
            for f in flags
        )
        if not has_issue and self.stage == ExerciseStage.DOWN:
            flags.append(FeedbackFlag(
                code="GOOD_FORM",
                message="Great form!",
                severity=FeedbackSeverity.INFO
            ))

        return flags


