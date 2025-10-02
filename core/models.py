import datetime
from sqlalchemy import (Column, Integer, String, Float, DateTime, JSON,
                        ForeignKey)
from sqlalchemy.orm import relationship

from .database import Base

class Event(Base):
    """
    Represents a generic event in the system for logging and auditing.
    (e.g., application start/stop, major errors).
    """
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    event_type = Column(String, index=True)
    message = Column(String)

class Capture(Base):
    """
    Represents a single RF capture event, storing all its metadata.
    This can be a manual, priority, or idle-scan capture.
    """
    __tablename__ = "captures"

    id = Column(Integer, primary_key=True, index=True)
    # Using a UUID as a string for a public, unique identifier.
    uuid = Column(String, unique=True, index=True, nullable=False)

    mode = Column(String, index=True, comment="e.g., 'manual', 'priority', 'idle'")

    frequency_hz = Column(Integer)
    bandwidth_hz = Column(Integer)

    # Storing gains as a JSON object for flexibility
    gains = Column(JSON) # e.g., {"lna": 16, "vga": 20}

    timestamp_start = Column(DateTime, default=datetime.datetime.utcnow)
    timestamp_end = Column(DateTime)

    rssi_avg_dbm = Column(Float, nullable=True)

    # Store paths to associated files in a JSON object
    file_paths = Column(JSON, nullable=True) # e.g., {"iq": "/path/to/file.iq", "wav": "/path/to/file.wav"}

    notes = Column(String, nullable=True)

    # Relationship to a potential decoded NOAA image
    noaa_image = relationship("NOAAImage", back_populates="capture", uselist=False)

class NOAAImage(Base):
    """
    Represents a decoded NOAA APT image and its specific metadata.
    Each record is linked to a specific capture.
    """
    __tablename__ = "noaa_images"

    id = Column(Integer, primary_key=True, index=True)

    capture_id = Column(Integer, ForeignKey("captures.id"), nullable=False, unique=True)

    satellite_name = Column(String, index=True)

    image_path = Column(String, nullable=False, unique=True)

    # Pass metadata at the time of decoding
    max_elevation = Column(Float)
    azimuth = Column(Float)

    timestamp_decoded = Column(DateTime, default=datetime.datetime.utcnow)

    # Establish the one-to-one relationship back to the capture
    capture = relationship("Capture", back_populates="noaa_image")