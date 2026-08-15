"""VehicleState value object.

Represents the reconciled state of one vehicle at one point in time. A
vehicle accumulates a *history* of these (not just a "latest" pointer) so
that a late event can insert a new, versioned entry into the past without
destroying the record of what was previously believed to be true.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class VehicleState:
    vehicle_id: str
    timestamp: datetime               # UTC
    version: int                      # monotonically increasing per (vehicle_id, timestamp)
    position: Optional[dict] = None   # e.g. {"x": .., "y": ..} - may be interpolated
    velocity: Optional[float] = None
    safety_state: str = "safe"        # safe|alert|danger
    source_of_truth: str = "sensor"   # which source's data determined safety_state
    decision_reason: str = ""
    superseded: bool = False          # True once a later-arriving (late) event
                                       # produces a newer version for this timepoint
    interpolated: bool = False        # True if position/velocity were interpolated
                                       # rather than directly observed

    def to_dict(self):
        d = asdict(self)
        d["timestamp"] = self.timestamp
        return d

    @staticmethod
    def from_dict(d):
        return VehicleState(
            vehicle_id=d["vehicle_id"],
            timestamp=d["timestamp"],
            version=d["version"],
            position=d.get("position"),
            velocity=d.get("velocity"),
            safety_state=d.get("safety_state", "safe"),
            source_of_truth=d.get("source_of_truth", "sensor"),
            decision_reason=d.get("decision_reason", ""),
            superseded=d.get("superseded", False),
            interpolated=d.get("interpolated", False),
        )
