import logging
import asyncio
import json
import pandas as pd
from collections import defaultdict
from datetime import datetime, timezone
from azure.functions import HttpRequest, HttpResponse

from collabgpt_get_vessels_in_transit_by_location.util import (vessel_id_to_mmsi, loc_display_to_id, all_loc_coords,
                                                               get_voyages_in_progress, coord_dist)
from shared.cosmos import AISData
from shared.slack import slack_logging


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logger.addHandler(ch)


ais_data_source = AISData(cache_mins_or_delta=15)


@slack_logging
def main(req: HttpRequest) -> HttpResponse:
    utc_timestamp = datetime.now(tz=timezone.utc)
    logger.info('collabgpt_get_vessels_in_transit_by_location function triggered at %s with inputs %s', utc_timestamp, dict(req.params))

    location = req.params.get('location')
    direction = req.params.get('direction', 'either')
    get_ais = req.params.get('get_ais') in ['true', 'yes', 'on']
    check_all_vessels = req.params.get('check_all_vessels') in ['true', 'yes', 'on']
    check_all_vessels_range = float(req.params.get('check_all_vessels_range', 50))
    safe_params = {k: v for k, v in req.params.items() if k != 'code'}
    id_or_mmsi_override = req.params.get('vessel_id_or_mmsi')

    # Only filter by voyage locations here if not going to filter all vessels by distance later
    voyages = get_voyages_in_progress(logger, *([] if get_ais and check_all_vessels else [location, direction]))

    voyages_by_vessel = defaultdict(list)
    for v in voyages:  # there *should* be at most one voyage in progress per vessel, but being safe (also for testing)
        voyages_by_vessel[v['vesselId']].append(v)  # if more than one, entries are sorted by reverse departureDateTime

    vessel_info = {vessel: dict(
                    vessel_name=v_voyages[0]['vesselDisplayId'],
                    mmsi=vessel_id_to_mmsi.get(vessel),
                    voyages=[v['voyageId'] for v in v_voyages]
                   ) for vessel, v_voyages in voyages_by_vessel.items()}
    logger.info('Vessels possibly of interest from the voyage summary cache: %s', list(vessel_info.keys()))

    status_code = 200
    if (vessel_info and get_ais) or id_or_mmsi_override:
        # Add the specific vessel to look-up to vessel_info (if there is one)
        mmsi_to_locate = None
        if id_or_mmsi_override:
            if id_or_mmsi_override.isnumeric():
                mmsi_to_locate = id_or_mmsi_override
                id_to_locate = found[0] if (found := [v for v, m in vessel_id_to_mmsi.items() if m == mmsi_to_locate]) else 'UNKNOWN'
            else:
                mmsi_to_locate = vessel_id_to_mmsi.get(id_or_mmsi_override)
                id_to_locate = id_or_mmsi_override
            if id_to_locate not in vessel_info:
                vessel_info[id_to_locate] = dict(vessel_name=id_to_locate, mmsi=mmsi_to_locate, voyages=[])

            # OVERRIDE: keep only the requested vessel (i.e. do not care about vessels from the voyage summary)
            vessel_info = {id_to_locate: vessel_info[id_to_locate]}
            logger.info('Overrode the vessels to look up to just the requested one: %s (MMSI: %s)', id_to_locate, mmsi_to_locate)

        # Query the ais cosmos collection
        ais_by_mmsi = ais_data_source.get_by_mmsi([info['mmsi'] for info in vessel_info.values() if info['mmsi']])  # retrieve in a single request; may not find all
        logger.info('AIS data retrieved for the following vessels: %s',
                    [f'{ais.get("VesselName")} (MMSI: {mmsi})' for mmsi, ais in ais_by_mmsi.items()])

        # Update outputs
        for vessel, info in vessel_info.items():
            is_the_override = id_or_mmsi_override and info['mmsi'] and info['mmsi'] == mmsi_to_locate
            info['ais'] = ais_by_mmsi.get(mmsi_to_locate if is_the_override else vessel_id_to_mmsi.get(vessel))
            info['coordinates'] = info['ais']['Position.Coordinates'][::-1] if info['ais'] else None
            if is_the_override and info['ais'] and (info['vessel_name'] == 'UNKNOWN' or not info['vessel_name']):
                info['vessel_name'] = info['ais'].get('VesselName')

        if no_coords := [vessel for vessel, info in vessel_info.items() if not info['ais']]:
            logger.warning('Could not retrieve ais data for the following vessels: %s', no_coords)
            # Report as "Partial data" regardless of whether the payload is going to be full or empty
            status_code = 206  # ^^ (would be empty if filtering by distance and all have no coords or are too far) ^^

        # Compute distances and, if successful, filter by them
        if location:
            if (loc_id := loc_display_to_id.get(location)) and (loc_coords := all_loc_coords.get(loc_id)):
                for vessel, info in vessel_info.items():
                    info['distance'] = coord_dist(info['coordinates'], loc_coords) if info['coordinates'] else None
                too_far = {k: vs for k, vs in vessel_info.items()  # keeping around just for inspection
                           if not (vs['distance'] and vs['distance'] <= check_all_vessels_range)}
                vessel_info = {k: vs for k, vs in vessel_info.items() if k not in too_far}
            else:
                logger.warning('Could not retrieve coordinates for location %s', location)
                for vessel, info in vessel_info.items():
                    info['distance'] = None

    if not vessel_info:
        logger.info('No results for the following arguments (vessels too far from location or no voyages in progress or no data): %s', safe_params)

    # Do not return full ais payloads
    out = {vessel: {k: v for k, v in info.items() if k != 'ais'} for vessel, info in vessel_info.items()}
    logger.info('Output: %s', json_out := json.dumps(out))
    return HttpResponse(json_out, mimetype='application/json', status_code=status_code)



# if __name__ == '__main__':
#     # vv removes the harmless but annoying 'RuntimeError: Event loop is closed' errors
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
#     out = main(HttpRequest(method='GET', url='', body='', params=(params := dict(
#         location='Barrow Island MOF',
#         # location='Wheatstone Platform',
#         # direction='either',
#         get_ais='true',
#         check_all_vessels='true',
#         check_all_vessels_range=5000,
#         # vessel_id_or_mmsi='503157850',
#         # vessel_id_or_mmsi='oceania',
#     ))))
#     out_dict = json.loads(out.get_body())
#     print(out.status_code, list(out_dict.keys()), out_dict)
#
#     # Test the faster response due to caching
#     out2 = main(HttpRequest(method='GET', url='', body='', params=params))
#     out_dict2 = json.loads(out2.get_body())
#     print(out2.status_code, list(out_dict2.keys()), out_dict2)


