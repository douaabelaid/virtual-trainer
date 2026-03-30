from pydantic import BaseModel  
from typing import List, Optional
from enum import Enum

# --- Enums ---

class ExerciseType(str, Enum):
    SQUAT = "squat"
    PUSHUP = "pushup"
    LUNGE = "lunge"

class ExerciseStage(str, Enum):
    STANDING = "standing"
    DOWN = "down"
    TRANSITION = "transition"

class FeedbackSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

# --- Sub-models ---

class FeedbackFlag(BaseModel):
    code: str                      
    message: str                   
    severity: FeedbackSeverity     

class JointAngles(BaseModel):
    left_knee: Optional[float] = None
    right_knee: Optional[float] = None
    left_hip: Optional[float] = None
    right_hip: Optional[float] = None
    back: Optional[float] = None
    left_elbow: Optional[float] = None
    right_elbow: Optional[float] = None

class LandmarkPoint(BaseModel):
    x: float
    y: float

# --- Main contract ---

# NOTE: This schema is locked as of March 2026. No further changes are allowed without supervisor approval.
class ExerciseState(BaseModel):
    timestamp_ms: int                          
    exercise: ExerciseType                     
    stage: ExerciseStage                       
    rep_count: int                             
    joint_angles: JointAngles                  
    feedback_flags: List[FeedbackFlag] = []    
    landmarks_raw: dict = {}