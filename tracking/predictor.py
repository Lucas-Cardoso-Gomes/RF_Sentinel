import datetime
import logging
from dataclasses import dataclass
from typing import List, Optional

from skyfield.api import EarthSatellite, Topos, wgs84

from .tle import TLEManager


@dataclass
class SatellitePass:
    """Represents the details of a single satellite pass."""
    satellite_name: str
    rise_time: datetime.datetime
    culminate_time: datetime.datetime
    set_time: datetime.datetime
    max_elevation_deg: float

    @property
    def duration(self) -> datetime.timedelta:
        """The total duration of the pass."""
        return self.set_time - self.rise_time

    def is_active(self, now: Optional[datetime.datetime] = None) -> bool:
        """Checks if the pass is currently happening."""
        if now is None:
            now = datetime.datetime.now(datetime.timezone.utc)
        return self.rise_time <= now <= self.set_time


class PassPredictor:
    """
    Calculates upcoming satellite passes over a given ground station location.
    """

    def __init__(self, config, tle_manager: TLEManager):
        """
        Initializes the PassPredictor.

        Args:
            config (AppConfig): The application's configuration object.
            tle_manager (TLEManager): An instance of the TLEManager.
        """
        self.config = config
        self.tle_manager = tle_manager

        # Define the ground station's location as a skyfield Topos object
        self.station: Topos = wgs84.latlon(
            latitude_degrees=config.station.latitude,
            longitude_degrees=config.station.longitude,
            elevation_m=config.station.elevation_m
        )

        self.min_elevation = config.noaa.min_elevation_deg
        self.timescale = self.tle_manager.timescale

    def find_upcoming_passes(self, hours_ahead: int = 48) -> List[SatellitePass]:
        """
        Finds all valid upcoming passes for all tracked satellites.

        Args:
            hours_ahead (int): How many hours into the future to search for passes.

        Returns:
            A list of SatellitePass objects, sorted by their rise time.
        """
        if not self.tle_manager.satellites:
            logging.info("Satellites not loaded. Loading TLE data now.")
            self.tle_manager.load_satellites()

        t0 = self.timescale.now()
        t1 = self.timescale.from_datetime(
            t0.to_datetime() + datetime.timedelta(hours=hours_ahead)
        )

        all_passes: List[SatellitePass] = []
        for name, satellite in self.tle_manager.satellites.items():
            try:
                times, events = satellite.find_events(
                    self.station, t0, t1, altitude_degrees=self.min_elevation
                )

                # Group events by pass (rise=0, culmination=1, set=2)
                event_groups = []
                for t, event in zip(times, events):
                    if event == 0:  # A new pass starts with a rise event
                        event_groups.append({})
                    if event_groups:
                        event_groups[-1][event] = t

                # Create SatellitePass objects from complete groups
                for group in event_groups:
                    if 0 in group and 1 in group and 2 in group:
                        # Calculate the precise max elevation at culmination time
                        diff = satellite - self.station
                        alt, _, _ = diff.at(group[1]).altaz()

                        pass_obj = SatellitePass(
                            satellite_name=name,
                            rise_time=group[0].to_datetime(),
                            culminate_time=group[1].to_datetime(),
                            set_time=group[2].to_datetime(),
                            max_elevation_deg=alt.degrees,
                        )
                        all_passes.append(pass_obj)

            except Exception as e:
                logging.error(f"Could not predict passes for {name}: {e}")
                continue

        # Sort all passes chronologically
        all_passes.sort(key=lambda p: p.rise_time)

        logging.info(f"Found {len(all_passes)} upcoming valid passes in the next {hours_ahead} hours.")
        return all_passes