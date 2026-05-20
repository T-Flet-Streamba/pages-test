# collabgpt_get_vessels_in_transit_by_location

Microservice to retrieve voyages, vessels, and, if requested, their coordinates, possibly filtered by location and direction w.r.t. it.

The request may contain the following OPTIONAL parameters:
- `location` - str: a location to restrict results by (if not provided, then vessel info for all in-transit voyages is returned).
  - known locations are 'Australian Marine Complex', 'Barrow Island MOF', 'Bunbury', 'Dampier', 'Q7000', 'Wheatstone Platform'.
- `direction` - str: one of 'to', 'from', or 'either' (the default).
- `get_ais` - str: 'true'/'yes'/'on' for true or anything else (or nothing) for false (the default);
    whether to retrieve ais data for the vessels in transit (will return the 'coordinates' field if True).
- `check_all_vessels` - str: 'true'/'yes'/'on' for true or anything else (or nothing) for false (the default);
    whether to check the distance to the given location for every vessel listed in the voyage summary
    (not just those on in-progress voyages to/from it).
    Note that this argument is used only if `get_ais` is true.
- `check_all_vessels_range` - float: the range to use to consider a vessel to be near the given location.
    Note that this argument is used only if `get_ais` and `check_all_vessels` are true.
- `vessel_id_or_mmsi` - str: a vessel id or mmsi to override the vessels to look up (as well as other options).
  - The vessels looked up otherwise are all those mentioned in the voyage summary (then possibly filtered by the other arguments).
  - This also overrides `check_all_vessels` and `get_ais` (it sets them to True), therefore `direction` will be ignored
      (distance-based location filtering will be applied if a `location` is given using the given or default `check_all_vessels_range`),
      and if something is returned it WILL include coordinates if available.

It returns a json string of a dictionary of dictionaries:
- `{vessel_id: {vessel_name: str, mmsi: str, voyages: list[str], coordinates: [latitude, longitude], distance: float}}`
- The `coordinates` field is only present if the get_ais argument is true.
- The `distance` field is only present if the get_ais argument is true and a `location` was given.

Note: the vessels' ais data is cached for 15 minutes, so on repeated calls only the first one will be slow.

The function runs when triggered by a get request here: https://vor-collabgpt-functions-dev.azurewebsites.net/api/collabgpt_get_vessels_in_transit_by_location
Can inspect live and stored invocation logs in the function app UI.


