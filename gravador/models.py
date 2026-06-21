from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple


@dataclass
class Step:
    index: int
    timestamp: datetime
    step_type: str
    description: str
    click_position: Optional[Tuple[int, int]] = None
    keys_text: str = ""
    screenshot_path: Optional[str] = None
    comment_text: str = ""
