import logging
import asyncio
import duckdb
import numpy.core.multiarray  # https://duckdb.org/docs/stable/clients/python/known_issues.html#numpy-import-multithreading
import pandas as pd
from langchain_core.tools import InjectedToolArg, tool

from typing import Union, Annotated

from collabgpt_lg.graph_types import ConfigSchema
from collabgpt_lg.endpoints import (
    ContainerEventsByID,
    ContainerEventsByIDDancer,
    CCUHires,
    FlightRequestApproval,
    FlightRequests,
    FlightsByDescription,
    FlightsByDescriptionVorSearch,
    GlobalDescriptionSearch,
    LogisticsSummaryReports,
    MovementRequestsByDescription,
    MovementRequestByID,
    PrioritiesByDescription,
    RoadTransportJobsByDescription,
    RoadTransportJobsVorSearch,
    ShipmentsByDescription,
    ShipmentsVorSearch,
    VorGlobalSearch,
    VoyageCargoManifestsByDescription,
    VoyageCargoManifestsByID,
    VoyagesByDescriptionVorSearch,
    VoyagesByID,
    WorkOrderByID
)


# All tools MUST return a dictionary.
# All tools MUST have a config (c) argument, though only some endpoint wrappers use it.
Config = Annotated[ConfigSchema, InjectedToolArg]


@tool('container_events_by_id')
def container_events_by_id_tool_wrapper(c: Config, container_id: str):
    """
    Always try this tool first if there are reference numbers which could be container IDs;
    For example, if a reference number is marked as both 'container' and 'shipment', try this tool first,
    and if not satisfied with the answer, then try find_shipments and global_search.
    Feel free to try other tools after it if the query is not about container events or locations.
    """
    api = ContainerEventsByID(c)
    return asyncio.run(api.query(container_id))


@tool('cargo_events_by_id')
def container_events_by_id_dancer_tool_wrapper(c: Config, container_id: str):
    """
    Find recent events for a given container.
    If there are reference numbers which could be container IDs, use this tool.
    You will probably want to use other tools as well, so use at least this one in that case.
    """
    api = ContainerEventsByIDDancer(c)
    return asyncio.run(api.query(container_id))


@tool('hired_containers')
def ccu_hires_tool_wrapper(c: Config, container_id_or_search_string: str):
    """
    Get info on the hired status of a given container or for multiple containers which mention the search string.
    If there are reference numbers which could be container IDs, use this tool.
    You will probably want to use other tools as well, so use at least this one in that case.
    """
    api = CCUHires(c)
    return asyncio.run(api.query(container_id_or_search_string))


@tool('find_flights')
def flights_tool_wrapper(c: Config,
    query: str = None, flight_number: str = None, status: str = None,                   # Key filters
    project_codes: str = None, movement_requests: str = None, manifest_id: str = None,  # Reference numbers
    origin: str = None, destination: str = None,                                        # Locations
    priority: bool = None, leg_number: str = None, item_count: str = None,              # Other features
    estimated_departure_date: str = None, actual_departure_date: str = None,            # Dates
    estimated_arrival_date: str = None, actual_arrival_date: str = None,
    further_processing: str = None):
    """
    Use to search for flights by id, number, description, or any of the various filters which are arguments to this tool.
    The status argument can only have the following values (or an alternation of them with '|'):
        'Scheduled', 'Cancelled', 'InFlight', 'Completed'.
    If the user asks for flight in a given time period without specifying what kind of date, use estimated_departure_date;
    this is especially important if the dates are in the future, as only estimated date types will be present.
    """
    api = FlightsByDescription(c)
    return api.query(
        query=query, flight_number=flight_number, status=status,                        # Key filters
        project_codes=project_codes, movement_requests=movement_requests,               # Reference numbers
        manifest_id=manifest_id,
        origin=origin, destination=destination,                                         # Locations
        priority=priority, leg_number=leg_number, item_count=item_count,                # Other features
        estimated_departure_date=estimated_departure_date,                              # Dates
        actual_departure_date=actual_departure_date,
        estimated_arrival_date=estimated_arrival_date,
        actual_arrival_date=actual_arrival_date,
        further_processing=further_processing)


@tool('find_flights')
def flights_vor_search_tool_wrapper(c: Config,
    search_term: str = None, date_ranges: str = None, sort: str = None,     # Key filters
    status: str = None, priority: bool = None,                              # Other features
    further_processing: str = None):
    """
    Search for flights by description or various filters.
    Use this tool instead of global search when you know you are looking for flights filtered by something more than
    just a search term (which is what global search would do).
    Field names you can use in date_ranges: estimatedDepartureDateTime, revisedEstimatedDepartureDateTime, actualDepartureDateTime,
        estimatedArrivalDateTime, revisedEstimatedArrivalDateTime, actualArrivalDateTime.
    Field names you can use in sort: the date_ranges ones, statusCodeType, flightNumber.
    Accepted values for status: Scheduled, Departed, Completed, Unknown.
    """
    api = FlightsByDescriptionVorSearch(c)
    return api.query(
        search_term=search_term, date_ranges=date_ranges, sort=sort,    # Key filters
        status=status, priority=priority,                               # Other features
        further_processing=further_processing)


@tool('approve_or_reject_flight_request')
def flight_request_approval_tool_wrapper(c: Config, approve: bool, request_id: str, comments: str):
    """
    Approve or reject a flight request. This is a mutating action; only use it when the user explicitly asks to approve or reject a request
    (not when they only want to list or search requests; that is handled elsewhere).
    Set approve to true for approval, false for rejection.
    Requires the request ID and a comment explaining the decision.
    """
    api = FlightRequestApproval(c)
    return asyncio.run(api.query(approve=approve, request_id=request_id, comments=comments))


@tool('flight_requests')
def flight_requests_tool_wrapper(c: Config, status: str = None):
    """
    Lists flight requests, optionally filtered by request state.
    Use this tool when the user asks about flight requests (additional sailings, air freight requests, etc.).
    This is NOT the same as searching for flights; use this specifically for requests that may need approval or review.
    Do not pass the status argument unless the user wants to filter by state; when you do, only these values are
    allowed, alone or alternated with '|': 'PENDING', 'APPROVED', 'REJECTED'.
    """
    api = FlightRequests(c)
    return asyncio.run(api.query(status=status))


@tool('global_search')
def global_search_wrapper(c: Config, query: str, further_processing: str = None):
    """
    Use to find items mentioning something when you are not sure about what type of item the user is looking for,
    for example where they are searching for a random object but without specifying the type of
    item it might be associated with, even only giving a reference number without any other detail.
    Note: do not pass dates to the query argument; if your goal involves dates there is probably a better tool for it,
    but if you really have to, mention date filtering in further_processing (to look for a single day you will want a 1-day range).
    Do not use this tool if the user is explicitly asking for
    flights, movement requests, road transport jobs, shipments, or voyages/manifests;
    use their tools instead, especially if projects or purchase orders are mentioned.
    Example queries could be 'where is my <item>?', or '<random-reference-id>', or 'is <item> in the supply chain?'.
    Make sure to only search for the item or reference number in the query, without surrounding words.
    """
    api = GlobalDescriptionSearch(c)
    return api.query(query=query, further_processing=further_processing)


@tool('logistics_summary')
def logistics_summary_tool_wrapper(c: Config, warning_type: str = None):
    """
    Retrieves logistics summary reports/warnings; no other tool returns this info, so if that is what you need, use only this one.
    Can use the warning_type argument to specify one of the following known types (no other value is accepted):
    'hcr transit time' for HCRs taking too long in transport,
    'hcr dwell time' for HCRs dwelling too long at location,
    'new cmrs' for new CMRs being created for given projects,
    'dangerous goods' for current dangerous goods.
    Calling this tool with no warning_type argument returns all of them, so do not call it again if you do not specify it.
    """
    api = LogisticsSummaryReports(c)
    return asyncio.run(api.query(_id=warning_type))


@tool('find_movement_requests')
def movement_requests_tool_wrapper(c: Config,
    query: str = None, status: str = None,                                              # Key filters
    mode_of_transport: str = None, stage: str = None,
    project_code: str = None, container_ids: str = None,                                # Reference numbers
    flights: str = None, road_transport_jobs: str = None, voyages: str = None,
    purchase_order: str = None, parents: str = None,
    destination: str = None, latest_event_location: str = None,                         # Locations
    hazmat: bool = None, hcr: bool = None, priority: bool = None,                       # Other features
    ros_date: str = None, latest_event_date: str = None,                                # Dates
    further_processing: str = None):
    """
    Use to search for movement requests by id, number, description, pack/tare, or any of the various filters which are arguments to this tool.
    If a purchase order is mentioned, always try both this tool and find_shipments (this tool first though).
    Other types of reference numbers can be used in the query argument (e.g. Kabal IDs).
    The allowed values for arguments below can also be passed as alternatives with | between them.
    Allowed mode_of_transport values: 'Land', 'Sea', 'Air'.
    Allowed stage values: 'Planned', 'In Progress', 'Delivered'.
    Always use mode_of_transport and stage as a pair rather than status, but if you need it, its values are:
    'Unknown', 'AwaitingPickup', 'PlannedOnVoyage', 'BookedShipment',
    'InProgress-OnTruck', 'InProgress-OnVessel', 'InProgress-OnAircraft', 'InProgress-StagedAtSupplyBase',
    'InProgress-WithTransportProvider', 'InProgress-Shipment',
    'Delivered-Road', 'Delivered-Marine', 'Delivered-Air', 'Delivered-Shipment'.
    If filtering for Barrow Island, use 'BWI|Barrow' as the relevant arg value.
    """
    api = MovementRequestsByDescription(c)
    return api.query(
        query=query, status=status, mode_of_transport=mode_of_transport, stage=stage,   # Key filters
        project_code=project_code, container_ids=container_ids,                         # Reference numbers
        flights=flights, road_transport_jobs=road_transport_jobs, voyages=voyages,
        purchase_order=purchase_order, parents=parents,
        destination=destination, latest_event_location=latest_event_location,           # Locations
        hazmat=hazmat, hcr=hcr, priority=priority,                                      # Other features
        ros_date=ros_date, latest_event_date=latest_event_date,                         # Dates
        further_processing=further_processing)


@tool('pack_or_tare')
def movement_requests_by_pack_or_tare_tool_wrapper(c: Config, query: str):
    """
    Only use this tool if a specific pack or tare ID is given in the reference number list.
    """
    api = MovementRequestByID(c)
    return asyncio.run(api.query(query))


@tool('find_priorities')
def priorities_tool_wrapper(c: Config,
    query: str = None, status: str = None,                                  # Key filters
    priority_type: int = None, mode_of_transport: str = None,
    destination: str = None,  # current_location: str = None,               # Locations
    ros_date: str = None, shipped_date: str = None,                         # Dates
    further_processing: str = None):
    """
    Use to search for priority items by description or any of the various filters which are arguments to this tool.
    Reference numbers can be used in the "query" argument (e.g. ST numbers).
    Priority might be given as 'P1'/'P2'; priority_type is the integer in those.
    Only possible argument values:
    - mode_of_transport: 'AIR', 'ROAD', 'IPEC', 'FREIGHT'
    - status: 'Sent', 'Cancelled', 'Incoming', 'At PSB', 'Completed'
    - destination: 'BWI', 'PLATFORM', 'ODC', 'WA OIL', 'KDC', 'THIRDPARTY', 'TVI', 'EXMOUTH'
    """  # the given mode_of_transport and status values are just keywords in the longer strings in the index
    api = PrioritiesByDescription(c)
    return api.query(
        query=query, status=status,                                         # Key filters
        priority_type=priority_type, mode_of_transport=mode_of_transport,
        destination=destination, # current_location=current_location,       # Locations
        ros_date=ros_date, shipped_date=shipped_date,                       # Dates
        further_processing=further_processing)


@tool
def process_dataset_with_sql(c: Config, datasets: Annotated[dict[str, pd.DataFrame], InjectedToolArg],
                             full_data_key: str, sql_query: str) -> Union[list[dict], str]:
    """
    Use this tool to process a dataset with SQL.
    The full_data_key argument has to be either 'TopResultsDataset' or 'AllResultsDataset'.
    The sql_query argument is the processing you wish to carry out and has to be in the form of an SQL query
    in which the table name is 'dataset'.
    Example uses of this tool could be to compute counts, totals, averages, maxima, minima, etc. of entries
    in retrieved data, possibly filtered/sorted by one or more fields and/or grouped by one or more categorical fields.
    Do NOT bother using this tool if you are just doing a SELECT with no further processing.
    Make sure not to replicate data filtering which has already taken place.
    Do NOT use columns containing 'date' in your SQL; leave date filtering to other tools.
    """
    if (dataset := datasets.get(full_data_key, {})) is None:  # << this variable is invoked by the SQL
        return f'Could not retrieve key {full_data_key} from the data cache; if the key is wrong, try again.'

    try:
        logging.info('The process_dataset_with_sql tool was passed the following query '
                     'to run on a dataset of %s rows:\n\t%s', len(dataset), sql_query)
        output = duckdb.query(sql_query).to_df().to_dict('records')
        logging.info('process_dataset_with_sql output: %s', str(output)[:200] + '...' if len(str(output)) > 200 else output)
        return output                                       #### ^^ TRIMMING LOG LENGTH IF REQUIRED ^^ ####
    except Exception as e:  # no need to be more specific
        logging.warning(f'The SQL query could not be executed. Error: %s', str(e))  # vv SQL in the 3rd line is extracted in _sql_processing
        return f'The SQL query could not be executed; try again.\nError: {e}'


@tool('find_road_transport_jobs')
def road_transport_jobs_tool_wrapper(c: Config,
    query: str = None, status: str = None,                                      # Key filters
    project_codes: str = None, container_ids: str = None,                       # Reference numbers
    movement_requests: str = None, trip_id: str = None,
    pickup_location: str = None, delivery_location: str = None,                 # Locations
    priority: bool = None, dangerous: bool = None, hcr=None,                    # Other features
    # latest_event_date: str = None,                                            # Dates
    # planned_pickup_date: str = None, estimated_pickup_date: str = None,
    # planned_delivery_date: str = None, estimated_delivery_date: str = None,
    requested_pickup_date: str = None, actual_pickup_date: str = None,
    requested_delivery_date: str = None, actual_delivery_date: str = None,
    further_processing: str = None):
    """
    Use to search for road transport jobs by id, description, or any of the various filters which are arguments to this tool.
    The status argument can only have the following values (which occur in this order):
        'Trip Created', 'At Depot', 'Allocated', 'Collected', 'In Transit', 'Delivered'.
    """
    api = RoadTransportJobsByDescription(c)
    return api.query(
        query=query, status=status,                                             # Key filters
        project_codes=project_codes, container_ids=container_ids,               # Reference numbers
        movement_requests=movement_requests, trip_id=trip_id,
        pickup_location=pickup_location, delivery_location=delivery_location,   # Locations
        priority=priority, dangerous=dangerous, hcr=hcr,                        # Other features
        # latest_event_date=latest_event_date,                                  # Dates
        requested_pickup_date=requested_pickup_date,
        # planned_pickup_date=planned_pickup_date,
        # estimated_pickup_date=estimated_pickup_date,
        actual_pickup_date=actual_pickup_date,
        requested_delivery_date=requested_delivery_date,
        # planned_delivery_date=planned_delivery_date,
        # estimated_delivery_date=estimated_delivery_date,
        actual_delivery_date=actual_delivery_date,
        further_processing=further_processing)


@tool('find_road_transport_jobs')
def road_transport_jobs_vor_search_tool_wrapper(c: Config,
    search_term: str = None, date_ranges: str = None, sort: str = None,     # Key filters
    priority: bool = None, dangerous: bool = None, hcr: bool = None,        # Other features
    further_processing: str = None):
    """
    Search for road transport jobs by description or various filters.
    Use this tool instead of global search when you know you are looking for road transport jobs filtered by something more than
    just a search term (which is what global search would do).
    Field names you can use in date_ranges include: latestEventDate, requestedPickupDateTime, plannedPickupDateTime,
        estimatedPickupDateTime, actualPickupDateTime, requestedDeliveryDateTime, plannedDeliveryDateTime,
        estimatedDeliveryDateTime, actualDeliveryDateTime, lastIndexedAt.
    Field names you can use in sort: the date_ranges ones, status, accountCode, jobNumber, serviceProvider, pickupLocation, deliveryLocation, latestEvent.
    """
    api = RoadTransportJobsVorSearch(c)
    return api.query(
        search_term=search_term, date_ranges=date_ranges, sort=sort,
        priority=priority, dangerous=dangerous, hcr=hcr,
        further_processing=further_processing)


@tool('find_shipments')
def shipments_tool_wrapper(c: Config,
    query: str = None, status: str = None,                                          # Key filters
    project_code: str = None, purchase_order: str = None, container_id: str = None, # Reference numbers
    origin: str = None, destination: str = None, weight: str = None,                # Other features
    added_date: str = None, eta_date: str = None,                                   # Dates
    # ros_date: str = None, transport_date: str = None,
    shipped_date: str = None, arrival_date: str = None,
    further_processing: str = None):
    """
    Use to search for shipments by id, description, or any of the various filters which are arguments to this tool.
    If a purchase order is mentioned, always try this tool and find_movement_requests.
    Some types of reference numbers with no filter and which should be put in the "query" argument are
    order reference numbers and shipment import/export numbers/code (SRC).
    Always use eta_date for time filtering unless explicitly asked for added, shipped, or arrival.
    The weight argument accepts the same range syntax (with ~) as the *_date ones, and the implicit unit it expects is kilos.
    The only accepted possible values of status are
    'Booked', 'InTransit', 'Completed', 'Cancelled', or 'Rejected'.
    """  # technically there are also 'InProgress' and 'Draft' statuses, but they should be ignored
    api = ShipmentsByDescription(c)
    return api.query(
        query=query, status=status, project_code=project_code,                      # Key filters
        purchase_order=purchase_order, container_id=container_id,                   # Reference numbers
        origin=origin, destination=destination, weight=weight,                      # Other Features
        added_date=added_date, eta_date=eta_date,                                   # Dates
        # ros_date=ros_date, transport_date=transport_date,
        shipped_date=shipped_date, arrival_date=arrival_date,
        further_processing=further_processing)


@tool('find_shipments')
def shipments_vor_search_tool_wrapper(c: Config,
    search_term: str = None, sort: str = None,                                          # Key filters
    # date_ranges: str = None,  # none at root level at the moment
    status: str = None, shipment_direction: str = None, mode_of_transport: str = None,  # Other Features
    # origin: str = None, destination: str = None,  # would require exact matches at the moment
    further_processing: str = None):
    """
    Search for shipments by description or various filters.
    Use this tool instead of global search when you know you are looking for shipments filtered by something more than
    just a search term (which is what global search would do).
    Field names you can use in sort: status, provider, modeOfTransport, shipmentDirection, origin, destination.
    Accepted values for other filters:
    - status: Booked, InTransit, Completed
    - shipment_direction: Import, Export
    - mode_of_transport: AIR, SEA
    """
    api = ShipmentsVorSearch(c)
    return api.query(
        search_term=search_term, sort=sort,                                                         # Key filters
        status=status, shipment_direction=shipment_direction, mode_of_transport=mode_of_transport,  # Other Features
        # origin=origin, destination=destination,
        further_processing=further_processing)


@tool('vor_global_search')
def vor_global_search_wrapper(c: Config, query: str, result_type: str = None, further_processing: str = None):
    """
    This tool finds entities based on IDs, locations, descriptions, and any text mentioned in them.
    Important note: by default, the query argument looks for exact (though case-insensitive) matches, so if you give it
    a string with multiple words, only results which have them in a row will be found.
    To instead find results matching multiple strings independently, use a "¦" to separate the subqueries
    (not a "|" because still limited to matching ALL of them, just not necessarily in a row).
    A typical example of this is when looking for two separate features,
    e.g. a location and an item, when you should write "LOCATION NAME¦ITEM NAME".
    Results can be filtered by entity type, so if you know the type(s?) you are looking for, pass one or more of the
    allowed types to the result_type argument; do not use this argument if you do not know.
    The accepted result_type values are listed elsewhere, and if you need to filter by more than one,
    do not make separate calls, but just pass the ones you need in a single string separated by a "|".
    Do not use this tool if you are looking for results of a specific type AND filtered by time AND there is another
    tool providing such filtering for that entity type.
    """
    api = VorGlobalSearch(c)
    return api.query(query, result_type, further_processing=further_processing)


@tool('find_voyage_cargo_manifests')
def voyage_cargo_manifests_tool_wrapper(c: Config,
    query: str = None, status: str = None,                                      # Key filters
    project_code: str = None, container_id: str = None, vessel: str = None,     # Reference numbers
    origin: str = None, destination: str = None,                                # Locations
    hcr: bool = None,                                                           # Other features
    total_teu: str = None, utilisation_percentage: str = None,
    total_tonnage: str = None,
    departure_date: str = None, eta_date: str = None, ros_date: str = None,     # Dates
    further_processing: str = None):
    """
    Use to search for voyages and their cargo manifests by id, description, or any of the various filters which are arguments to this tool.
    The user may say "shipment" when they mean container or movement request, so do try this tool in that case too.
    This is the only tool with info on manifests, therefore you MUST use (as your first choice) it if the query mentions manifests at all,
    even if asking to find things (on manifests) which would normally be looked up with a different tool,
    e.g. asking for movement requests in provisional manifests, or to see manifests with a specific container.
    The only accepted possible values of status are 'Provisional', 'In Progress', and 'Complete'.
    The total_teu, utilisation_percentage, and total_tonnage arguments accept the same range syntax (with ~) as the *_date ones.
    Some known vessels are: aurigaastrolabe, aurigainvestigator, gosirius, normandskimmer, skimmertide.
    It's possible that the cargo line data is too long to be parsed and will be truncated, the data will mention this if it happened,
    detail on this is not important, just let the user know they can see the full list on the voyage page.
    """
    # Note for reference: the above docstring is THE MAXIMUM number of tokens allowed for tool descriptions
    api = VoyageCargoManifestsByDescription(c)
    return api.query(
        query=query, status=status,                                             # Key filters
        project_code=project_code, container_id=container_id, vessel=vessel,    # Reference numbers
        origin=origin, destination=destination,                                 # Locations
        hcr=hcr,                                                                # Other features
        total_teu=total_teu, utilisation_percentage=utilisation_percentage,
        total_tonnage=total_tonnage,
        departure_date=departure_date, eta_date=eta_date, ros_date=ros_date,    # Dates
        further_processing=further_processing)


@tool('find_voyages')
def voyages_tool_wrapper(c: Config,
    search_term: str = None, date_ranges: str = None, sort: str = None,     # Key filters
    status: str = None, hcr: bool = None, priority: bool = None,            # Other features
    further_processing: str = None):
    """
    Search for voyages by description or various filters.
    Use this tool instead of global search when you know you are looking for voyages filtered by something more than
    just a search term (which is what global search would do).
    Field names you can use in date_ranges: plannedDepartureDateTime, actualDepartureDateTime.
    Field names you can use in sort: the date_ranges ones, voyageDisplayId, vesselName, state.
    Accepted values for status: Upcoming, Active, Completed.
    """
    api = VoyagesByDescriptionVorSearch(c)
    return api.query(
        search_term=search_term, date_ranges=date_ranges, sort=sort,    # Key filters
        status=status, hcr=hcr, priority=priority,                      # Other features
        further_processing=further_processing)


@tool('voyages_by_number')
def voyage_cargo_manifest_by_number_wrapper(c: Config, number: str):
    """
    Use this tool to find a voyage by its 4-digit number.
    """  # This tool is only used in the notification agent node (normally the endpoint wrapper is used indirectly)
    api = VoyageCargoManifestsByID(c)
    return asyncio.run(api.query(number))


@tool('work_orders_by_id')
def work_orders_by_id_wrapper(c: Config, wo_digits: str):
    """
    Useful for finding movement requests or shipments related to a given work order ID.
    Pass only the digits from the ID to this tool, i.e. do not pass the 'WO' prefix.
    Results might also contain information about relevant dates, projects, and involved packs/tares or containers.
    If a work order is involved in the query, you should always look it up with this tool
    (you may use other ones in addition to it, e.g. the global search tool or one of the find_* tools for more
    specific results, but this tool is a must).
    """
    api = WorkOrderByID(c)
    return asyncio.run(api.query(wo_digits))



# #### Tool-related functions ####

non_index_api_dispatcher_by_org = {
    'CHEVRON': dict(
        find_flights=FlightsByDescription,
        find_movement_requests=MovementRequestsByDescription,
        find_priorities=PrioritiesByDescription,
        find_road_transport_jobs=RoadTransportJobsByDescription,
        find_shipments=ShipmentsByDescription,
        # voyage cargo manifests do not need further lookup
    ),
    'Shell UK': dict(
        find_flights=FlightsByDescriptionVorSearch,
        find_voyages=VoyagesByDescriptionVorSearch,
    ),
    'ExxonMobilGuyana': dict(
        find_flights=FlightsByDescriptionVorSearch,
        find_shipments=ShipmentsVorSearch,
        find_voyages=VoyagesByDescriptionVorSearch,
    ),
}


def non_index_data_retriever(c: Config, original_tool: str, index_results: list[dict], params: dict):
    """Invoke the non_index_data_pipeline method of the appropriate class to retrieve entries matching those from the index.
    NOTE: this function will look up all the data it is passed; count limits should be pre-applied to index_results.
    """
    api_dispatcher = non_index_api_dispatcher_by_org.get(c['org'], {})
    if api := api_dispatcher.get(original_tool):
        try:                                                            # vv trust the input to this function is limited
            return api(c).non_index_data_pipeline(index_results, params, limit=len(index_results))
        except:
            logging.warning(f'A call to the non_index_data_pipeline method of {original_tool} tool failed.')
            return index_results
    else:
        return index_results


# #### Tool data structures ####

# IMPORTANT NOTE: this is one of two configs w.r.t. tool-org relationships. This one determines which tools each org SEES.
#   The other config happens in each class of endpoints.py, and determines whether it is ALLOWED to run for a given org.
tools_by_org = {
    'CHEVRON': {
        'retrieval': [
            container_events_by_id_tool_wrapper,
            flights_tool_wrapper,
            global_search_wrapper,
            logistics_summary_tool_wrapper,
            movement_requests_tool_wrapper,
            movement_requests_by_pack_or_tare_tool_wrapper,
            priorities_tool_wrapper,
            road_transport_jobs_tool_wrapper,
            shipments_tool_wrapper,
            voyage_cargo_manifests_tool_wrapper,
            work_orders_by_id_wrapper,
        ],
        'action': [],
    },
    'Shell UK': {
        'retrieval': [
            container_events_by_id_tool_wrapper,
            flights_vor_search_tool_wrapper,
            flight_requests_tool_wrapper,
            vor_global_search_wrapper,
            voyages_tool_wrapper,
        ],
        'action': [flight_request_approval_tool_wrapper],
    },
    'ExxonMobilGuyana': {
        'retrieval': [
            ccu_hires_tool_wrapper,
            container_events_by_id_dancer_tool_wrapper,
            flights_vor_search_tool_wrapper,
            shipments_vor_search_tool_wrapper,
            vor_global_search_wrapper,
            voyages_tool_wrapper,
        ],
        'action': [],
    },
}
tool_maps_by_org = {
    org: {kind: {tool.name: tool for tool in tools} for kind, tools in by_kind.items()}
    for org, by_kind in tools_by_org.items()
}

sql_tool_map = {tool.name: tool for tool in [process_dataset_with_sql]}


