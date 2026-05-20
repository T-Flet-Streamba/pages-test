from logging import Logger
import redis
import json
import math
from datetime import timedelta

from shared.cosmos import Locations
import config


# Chevron locations
loc_data = Locations(cache_mins_or_delta=timedelta(weeks=52))
if loc_res := loc_data.coords_by_org('CHEVRON'):
    all_loc_coords, loc_display_to_id = loc_res
else:
    raise RuntimeError('No information could be retrieved from Cosmos about Chevron locations.')


# Vessels' MMSI codes
# CURRENTLY HARDCODED; WILL FETCH A DYNAMICALLY UPDATED BLOB FILE WHEN ITS STRUCTURE IS FINALISED
#   See https://streamba.slack.com/archives/C026XKWLH6X/p1734522981954509?thread_ts=1734454948.239959&cid=C026XKWLH6X
# THE FULL PATH IS REQUIRED FOR DEPLOYMENT; UNCOMMENT THE PARTIAL ONE, WHICH IS FOR LOCAL TESTING
with open('collabgpt_get_vessels_in_transit_by_location/20241217-154119-vessel-mmsi-mappings.json', encoding='utf8') as f:
# with open('20241217-154119-vessel-mmsi-mappings.json', encoding='utf8') as f:
    all_vessels = json.load(f)                                     # vv these are the relevant ones, but no need to restrict
vessel_id_to_mmsi = {v['VesselId']: v['Mmsi'] for v in all_vessels}# if v['Source'] == 'VesselContract'}


def get_voyages_in_progress(logger: Logger, location=None, direction='either'):
    """
    Get voyages in progress from the redis cache; they can be filtered by a location (to it, from it, or either).
    Allowed direction values: 'to', 'from', or 'either'.
    Known locations are: 'Australian Marine Complex', 'Barrow Island MOF', 'Bunbury', 'Dampier', 'Q7000', 'Wheatstone Platform'.
    """
    if location and direction not in ['to', 'from', 'either']:
        raise ValueError("The location argument can only be 'to', 'from', or 'either'.")

    # No try-except; happy to raise directly for any stage
    rc = redis.from_url(config.redis.connection_str)
    data_raw = rc.get(config.redis.cvx.voyagesummary)
    voyages = json.loads(data_raw)

    if voyages:
        logger.info('%s voyages found in the cache', len(voyages))
    else:
        raise RuntimeError('No voyage summary data found in the redis cache.')

    if location:
        loc_filter = {'from': [0], 'to': [1], 'either': [0,1]}[direction]
        return sorted([v for v in voyages
                       if v['voyageState'] == 1  # i.e. in progress (0 is provisional and 2 is complete)
                       if location in [v['route'][i]['locationDisplayId'] for i in loc_filter]],
                      key=lambda v: v['departureDateTime'], reverse=True)
    else:
        return voyages


def coord_dist(lat_lon1: tuple[float, float], lat_lon2: tuple[float, float], r = 6371.0):
    """Return the distance in Km between two pairs of coordinates (the haversine formula).
    The default radius is the typically used global average radius of the Earth (in Km).
    """
    lat1, lon1, lat2, lon2 = map(math.radians, [*lat_lon1, *lat_lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    return c * r


