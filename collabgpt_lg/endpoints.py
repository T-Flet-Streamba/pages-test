import copy
import logging
import asyncio
import re
import json
import pandas as pd
from collections import defaultdict, Counter
from more_itertools import unique_justseen
from datetime import date, datetime
from aiohttp import ClientSession, TCPConnector

from langchain_community.chat_message_histories import ChatMessageHistory

from collabgpt_lg.graph_types import ConfigSchema
from collabgpt_lg.endpoints_base import (
    AISearchBaseClass,
    CustomerAPIBaseClass,
    DataEnhancerAPIBaseClass,
    LangFlowBaseClass,
    RedisBaseClass,
    VorSearchBaseClass
)
from collabgpt_lg.org_config import vor_search_result_filters, vor_url_list
from collabgpt_lg.utils import localise_dt, sort_dicts, format_message_history, common_dict_entries, words_from_misc_case

from shared.ids.all_regexes import id_filter, REGEX_MAPPING
from shared.utils import filter_dataframe
import config



class ContainerEventsByID(CustomerAPIBaseClass):
    def __init__(self, c: ConfigSchema, session=None):
        super().__init__(c, supported_orgs=['CHEVRON', 'Shell UK'])
        self.url_endpoint = config.customer_api.url.container_events
        self.session = session

    def _data_mapping(self, data) -> dict:
        """Method to reduce the customer API data and extract useful fields."""
        mapped_data = {}
        keys = [  # Expand this list if more fields are added to "Events" in the API
            'EventDescription',
            'EventOccurredTimestamp',  # no dt localisation operation required since the UseLocalTime header is respected
            'Location'
        ]

        now = localise_dt(datetime.now().isoformat(), self.c['timezone'])
        if (events := data.get('Events')) is not None:  # reduce data to only the required keys
            mapped_data['Events'] = [{key: e.get(key) for key in keys} for e in events]
            for e in mapped_data['Events']:  # vv same-timezone ISO-datetimes can be sorted lexicographically
                if localise_dt(e['EventOccurredTimestamp'], self.c['timezone'], assume_local_if_no_tz=True) > now:
                    e['IsFutureEvent'] = True  # no need to add this field to past events; save the tokens

        if (container_id := data.get('CcuId')) is not None:
            mapped_data['url'] = self.vor_url.container(container_id)

        return mapped_data

    async def query(self, _id: str, event_count_limit=5, verbose=True, **kwargs) -> dict:
        """Send query to endpoint and fetch data."""
        data = await self._send_request(session=self.session, verbose=verbose,
                                        params=dict(id=_id, eventCountLimit=event_count_limit))
        return self._data_mapping(data) if data else dict(status="no data available")

class ContainerEventsByIDDancer(DataEnhancerAPIBaseClass):
    def __init__(self, c: ConfigSchema, session=None):
        super().__init__(c, supported_orgs=['ExxonMobilGuyana'])
        self.url_endpoint = config.data_enhancer.url.cargo_events_by_id
        self.session = session

    def _data_mapping(self, data, localised_datetimes=True) -> dict:
        """Method to reduce the Data Enhancer API data and extract useful fields."""
        # The data is a list of long almost-identical dicts; separating fixed and varying entries
        common_data = common_dict_entries(data)
        events = [{k: v for k, v in d.items() if k not in common_data} for d in data]

        # Drop unwanted and null fields (likely many)
        bad_keys = [  # I.e. fields which are redundant, need special handling, or are not of interest
            'containerDisplayName',
            'organization',
            'subjectEntityId',
            'sourceFileName',
            'sourceFileLineNumber'
        ]
        mapped_data = {k: v for k, v in common_data.items() if k not in bad_keys and v}

        # Clarify common-fields situation to the AI
        mapped_data['NOTE_ON_COMMON_FIELDS'] = ('Note that any field not inside individual entries of "events" '
                                                'is identical for all of them (e.g. if "eventType" is at the top level '
                                                'and not in each event, then all events are of that type)')

        # Drop personal or unnecessary location info
        if loc_name := (mapped_data.get('location') or {}).get('locationName'):
            mapped_data['location'] = loc_name
        else:  # ^^ and vv : the location field CAN actually exist AND be None, hence this caution
            for e in events:
                if loc_name := (e.get('location') or {}).get('locationName'):
                    e['location'] = loc_name

        # Drop redundant single-event fields
        for e in events:
            e.pop('entityId', None)
            e.pop('eventTimestampUtc', None)

        if localised_datetimes:
            for e in events:
                for k in ['eventTimestamp', 'createdAtDateTime', 'lastUpdatedAtDateTime']:
                    if k in e:
                        e[k] = localise_dt(e[k], self.c['timezone'])

        mapped_data['events'] = events[:config.ai_behaviour.default_limit]

        mapped_data['url'] = self.vor_url.container_details(common_data['containerId'])

        return mapped_data

    async def query(self, _id: str, verbose=True, localised_datetimes=True, **kwargs) -> dict:
        """Send query to endpoint and fetch data."""
        data = await self._send_request(session=self.session, verbose=verbose,
                                        params=dict(containerId=_id, organization=self.c['org']))
        return self._data_mapping(data, localised_datetimes=localised_datetimes) if data else dict(status='no data available')


class CCUHires(DataEnhancerAPIBaseClass):
    def __init__(self, c: ConfigSchema, session=None):
        super().__init__(c, supported_orgs=['ExxonMobilGuyana'])
        self.url_endpoint = config.data_enhancer.url.active_ccu_hires
        self.session = session

    def _data_mapping(self, data: list[dict], id_or_other_ref: str, localised_datetimes=True) -> dict:
        """Method to reduce the Data Enhancer API data and extract useful fields."""
        bad_keys = [  # I.e. fields which are redundant, need special handling, or are not of interest
            'organization',
            'sourceFileName',
            'sourceFileLineNumber'
        ]

        mapped_data = []
        for ccu in data:
            # Drop unwanted and null fields (likely many)
            mapped_ccu = {k: v for k, v in ccu.items() if k not in bad_keys and v}

            # Convert key/value pairs to a standard dictionary
            mapped_ccu['additionalData'] = {pair['key']: pair['value'] for pair in mapped_ccu['additionalData']}
            mapped_ccu['references'] = {pair['key']: pair['value'] for pair in mapped_ccu['references']}

            if localised_datetimes:
                for k in ['createdAtDateTime', 'lastUpdatedAtDateTime']:
                    if k in mapped_ccu:
                        mapped_ccu[k] = localise_dt(mapped_ccu[k], self.c['timezone'])

                if last_time := mapped_ccu.get('lastSeenLocation', {}).get('recordedAt'):
                    mapped_ccu['lastSeenLocation']['recordedAt'] = localise_dt(last_time, self.c['timezone'])

                # Spot and localise datetimes among the arbitrary nested fields
                for k, v in mapped_ccu['additionalData'].items():
                    if isinstance(v, str) and re.match(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', v):
                        mapped_ccu['additionalData'][k] = localise_dt(v, self.c['timezone'])

            mapped_data.append(mapped_ccu)

        return self._package_data(mapped_data[:config.ai_behaviour.default_limit], all_results=mapped_data,
                                  applied_filters=dict(id_or_other_ref=id_or_other_ref))

    async def query(self, id_or_other_ref: str, verbose=True, localised_datetimes=True, **kwargs) -> dict:
        """Send query to endpoint and fetch data."""
        data = await self._send_request(session=self.session, verbose=verbose, params=dict(organization=self.c['org']))

        # Remove coordinates since their digits may match queried reference numbers
        for d in data:
            if (loc := d.get('lastSeenLocation')) and loc.get('coordinates'):
                del d['lastSeenLocation']['coordinates']
            if 'additionalData' in d:
                d['additionalData'] = [a for a in d['additionalData'] if a['key'] not in ['Latitude', 'Longitude']]

        # Find the hired CCUs which contain every word in the search string
        search_words = [re.compile(re.escape(quoted_word)) for word in id_or_other_ref.split()
                        if (quoted_word := f"'{word}'" if all(c == '$' for c in word) else word)]
                        # ^^ put single quotes around words which are just dollar signs ($, $$, and $$$), i.e. the cost
        matches = [d for d in data if (str_d := str(d)) if all(word.search(str_d) for word in search_words)]

        return self._data_mapping(matches, id_or_other_ref=id_or_other_ref, localised_datetimes=localised_datetimes) if matches else dict(status='no data available')


class FlightsByDescription(AISearchBaseClass):
    """Uses the flights AI search service to find items based on their description."""

    def __init__(self, c: ConfigSchema):
        super().__init__(c, supported_orgs=['CHEVRON'])
        self.url_endpoint = config.ai_search.url.flights

    def query(self, query: str = None, flight_number: str = None, status: str = None,       # Key filters
        project_codes: str = None, movement_requests: str = None, manifest_id: str = None,  # Reference numbers
        origin: str = None, destination: str = None,                                        # Locations
        priority: bool = None, leg_number: str = None, item_count: str = None,              # Other features
        estimated_departure_date: str = None, actual_departure_date: str = None,            # Dates
        estimated_arrival_date: str = None, actual_arrival_date: str = None,
        further_processing: str = None) -> dict:
        """Search for an item in the index."""
        query = query if query else '*'

        search_results = self._send_request(params=(params := dict(
            organisation=self.c['org'],                                                     # Key filters
            query=query, flight_number=flight_number, status=status,
            project_codes=project_codes, movement_requests=movement_requests,               # Reference numbers
            manifest_id=manifest_id,
            origin=origin, destination=destination,                                         # Locations
            priority=priority, leg_number=leg_number, item_count=item_count,                # Other features
            estimated_departure_date=self.make_iso(estimated_departure_date),               # Dates
            actual_departure_date=self.make_iso(actual_departure_date),
            estimated_arrival_date=self.make_iso(estimated_arrival_date),
            actual_arrival_date=self.make_iso(actual_arrival_date),
        )))

        if fallback := self.by_id_fallback('flight_id', FlightsByID, search_results, params):
            return fallback

        search_results = sort_dicts(search_results, [('estimated_departure_date', True)])
        non_index_data = [] if further_processing else self.non_index_data_pipeline(search_results, params)

        return self._package_data(non_index_data, limit=len(non_index_data), all_results=search_results,
                                  applied_filters=params, further_processing=further_processing)

    def non_index_data_pipeline(self, search_results: list, params: dict, limit: int = config.ai_behaviour.default_limit):
        """Retrieve data from the Data Enhancer and enhance and/or reduce it as required."""
        return asyncio.run(self.get_data(search_results, FlightsByID, limit=limit))


class FlightsByDescriptionVorSearch(VorSearchBaseClass):
    """Uses the flights Vor Search service to find items based on their flight number or description."""

    def __init__(self, c: ConfigSchema):
        super().__init__(c, supported_orgs=['CHEVRON', 'ExxonMobilGuyana', 'Shell UK'])
        self.url_endpoint = config.vor_search.url.flights_search

    def query(self, search_term: str = None, date_ranges: str = None, sort: str = None,
        status: str = None, hcr: bool = None, priority: bool = None,
        further_processing: str = None) -> dict:
        """Search voyages via the Vor Search API, enrich from Data Enhancer, and package results."""
        return self._query_pipeline(search_term, date_ranges, sort,
            other_filters=dict(
                statusCodeType=status,
                containsPriorityFreight=priority
            ),
            date_fields=[
                'estimatedDepartureDateTime', 'revisedEstimatedDepartureDateTime', 'actualDepartureDateTime',
                'estimatedArrivalDateTime', 'revisedEstimatedArrivalDateTime', 'actualArrivalDateTime', 'lastIndexedAt'
            ],
            by_id_fallback_patterns=['flight_id', 'flight_number'],
            by_id_endpoint_class=FlightsByID,
            further_processing=further_processing
        )

    def non_index_data_pipeline(self, search_results: list, params: dict, limit: int = config.ai_behaviour.default_limit):
        """Retrieve voyage details from the Data Enhancer for each search hit."""
        return super().non_index_data_pipeline(search_results, params, FlightsByID, 'flightId', limit)


class FlightsByID(DataEnhancerAPIBaseClass):
    def __init__(self, c: ConfigSchema, session=None):
        super().__init__(c, supported_orgs=['CHEVRON', 'Shell UK', 'ExxonMobilGuyana'])
        self.url_endpoint = config.data_enhancer.url.flights_by_id
        self.session = session

    def _data_mapping(self, data, localised_datetimes=True) -> dict:
        """Method to reduce the Data Enhancer API data and extract useful fields."""
        org = data['organization']  # shorthand here to highlight that there are differences by org further down

        good_keys = [  # I.e. fields which are of interest and already in the required format
            'entityId',
            'organization',
            'flightNumber',  # this is the id users will be looking up, but it is not unique
            'flightManifestId',
            'statusCodeType',  # values: Scheduled|Cancelled|InFlight|Completed
            'flightDate',
            'containsPriorityFreight',
        ]
        mapped_data = {k: v for k, v in data.items() if k in good_keys}

        refs = {val for ref in data.get('references', []) if (val := ref.get('value'))}
        if mrs := {ref for ref in refs if ref[1:3] == 'MR'}:
            mapped_data['movementRequests'] = ' '.join(mrs)
        if other_refs := refs.difference(mrs):
            mapped_data['references'] = ' '.join(other_refs)

        mapped_data.update(dict(  # vv extract MRs here if present to have the field near the top; removed later if not Chevron
            projects=' '.join({pr for fr in data.get('airFreight', []) if (pr := fr.get('projectCode'))}),
            itemDescriptions='\n'.join([f'{no}: {descr}' for fr in data.get('airFreight', [])
                if (no := fr.get('cargoItemNumber', ''), descr := fr.get('itemDescription', '')) if no or descr]),
            estimatedDepartureDateTime=data.get('revisedEstimatedDepartureDateTime') or data.get('estimatedDepartureDateTime'),
            actualDepartureDateTime=data.get('actualDepartureDateTime'),
            estimatedArrivalDateTime=data.get('revisedEstimatedArrivalDateTime') or data.get('estimatedArrivalDateTime'),
            actualArrivalDateTime=data.get('actualArrivalDateTime'),
        ))

        if legs := data.get('flightLegs'):
            mapped_data['flightLegs'] = []
            for leg in legs:
                mapped_data['flightLegs'].append(dict(
                    legNumber = leg.get('legNumber'),
                    startLocation = leg.get('startLocation', {}).get('locationName'),
                    endLocation = leg.get('endLocation', {}).get('locationName'),
                    estimatedDepartureDateTime=leg.get('revisedEstimatedDepartureDateTime') or leg.get('estimatedDepartureDateTime'),
                    actualDepartureDateTime=leg.get('actualDepartureDateTime'),
                    estimatedArrivalDateTime=leg.get('revisedEstimatedArrivalDateTime') or leg.get('estimatedArrivalDateTime'),
                    actualArrivalDateTime=leg.get('actualArrivalDateTime')
                ))

            ordered_locations = [loc for leg in mapped_data['flightLegs'] for loc in [leg['startLocation'], leg['endLocation']] if loc]
            mapped_data.update(dict(
                origin=ordered_locations[0] if ordered_locations else None,
                destination=ordered_locations[-1] if ordered_locations else None,
                route=' -> '.join(unique_justseen(ordered_locations)),
                legNumber=len(legs),
                cargoItemCount=legs[0]['cargoItemCount']
            ))

        if org == 'Shell UK' and (_id := data.get('flightManifestId')):
            mapped_data['url'] = self.vor_url.helicopter(_id)
        elif _id := data.get('entityId'):
            mapped_data['url'] = self.vor_url.flight(_id)

        if mrs:
            mapped_data['movementRequestUrls'] = [self.vor_url.movement_request(mr) for mr in mrs]

        # datetime localisation
        keys_to_localise = [
            'estimatedDepartureDateTime',
            'actualDepartureDateTime',
            'estimatedArrivalDateTime',
            'actualArrivalDateTime'
        ]
        if localised_datetimes:
            # top level items
            for k in keys_to_localise:
                if k in mapped_data:
                    mapped_data[k] = localise_dt(mapped_data[k], self.c['timezone'])

            # nested in flight legs
            for leg in mapped_data.get('flightLegs') or []:
                for k in keys_to_localise:
                    if k in leg:
                        leg[k] = localise_dt(leg[k], self.c['timezone'])

        return mapped_data

    async def query(self, _id: str, verbose=True, localised_datetimes=True, **kwargs) -> dict:
        """Send query to endpoint and fetch data."""
        prefs = {'dawinci': 'DaWinci', 'helipass': 'Helipass'}  # this endpoint is case-sensitive
        formatted_id = next((caps + _id[len(raw):] for raw, caps in prefs.items() if re.match(raw, _id, flags=re.IGNORECASE)), _id)
        data = await self._send_request(session=self.session, verbose=verbose,
                                        params=dict(id=formatted_id, organization=self.c['org']))
        return self._data_mapping(data, localised_datetimes=localised_datetimes) if data else dict(status='no data available')


class FlightRequests(CustomerAPIBaseClass):
    _ALLOWED_STATES = frozenset({'PENDING', 'APPROVED', 'REJECTED'})

    def __init__(self, c: ConfigSchema, session=None):
        super().__init__(c, supported_orgs=['Shell UK'])
        self.url_endpoint = config.customer_api.url.flight_request
        self.session = session

    @staticmethod
    def _trim_sailing(sailing: dict) -> dict:
        """Compact a ProposedSailing or ApprovedProposedSailing object."""
        if not sailing:
            return sailing

        good_keys = [
            'Id', 'SailingDateTime', 'EstimatedArrivalDateTime', 'TimeDifference',
            'EstimatedCost', 'ClusterOrder', 'EditReason',
            'EstimatedCostWithLocation', 'EstimatedCostWithoutLocation'
        ]

        trimmed = {k: v for k, v in sailing.items() if k in good_keys and (v or v is False or v == 0)}
        if locations := sailing.get('Location'):
            trimmed['Location'] = [loc.get('LocationDisplayName', loc) for loc in locations]
        if reqs := sailing.get('Requirements'):
            req_keys = ['id', 'location', 'arrivalDateTime', 'priority', 'lifts',
                        'clustername', 'clientname', 'startTime', 'endTime']
            trimmed['Requirements'] = [{k: r[k] for k in req_keys if k in r} for r in reqs]

        return trimmed

    @staticmethod
    def _trim_line_items(items: list[dict], bad_keys: list[str]) -> list[dict]:
        """Remove unwanted keys and null values from a list of line-item dicts."""
        return [{k: v for k, v in item.items() if k not in bad_keys and (v or v is False or v == 0)} for item in items] if items else []

    def _data_mapping(self, data: list[dict]) -> list[dict]:
        """Reduce each flight request item to useful fields."""
        bad_keys = [
            'DeletedAt', 'DeletedBy', 'Duration', 'EmailRecipients',
            'FlightDate', 'LatestArrivalDateTime', # yes, these are not for flight requests (while 'ArrivalDateTime' is)
            'IsDeleted', 'Lifts', 'ProposedSailingsOptionsIds', 'Quantity', 'QuantitySupplied',
            'SeenByUsersHistory', 'SharedWith', 'Version',
        ]
        dt_keys = [
            'ArrivalDateTime', 'LatestArrivalDateTime', 'CreatedAt', 'UpdatedAt',
            'ApprovedAt', 'RejectedAt', 'RescindedAt', 'FlightDate',
            'LogisticsApprovedAt', 'LogisticsAllocatedAt', 'ResolvedAt',
            'DeliveryDateTime', 'ReceiptedAt', 'MarkedDeliveredAt', 'MobDateTime',
            'ScopeExecutionDate',
        ]

        mapped = []
        for item in data:
            entry = {k: v for k, v in item.items() if k not in bad_keys and (v or v is False or v == 0)}

            # # MEANT FOR SAILING REQUESTS; KEEPING AROUND IF WE GET TO THEM
            # if proposed := item.get('ProposedSailings'):
            #     entry['ProposedSailings'] = [self._trim_sailing(s) for s in proposed]
            # if approved := item.get('ApprovedProposedSailing'):
            #     entry['ApprovedProposedSailing'] = self._trim_sailing(approved)
            #
            # # Trim item fields
            # entry['LcoLineItems'] = self._trim_line_items(item.get('LcoLineItems', []), ['LastUpdatedDateTime', 'VendorContactName', 'VendorContactNumber'])
            # entry['CcuItems'] = self._trim_line_items(item.get('CcuItems', []), ['LastUpdatedDateTime', 'LastUpdatedBy'])
            # entry['StorageItems'] = self._trim_line_items(item.get('StorageItems', []), ['LastUpdatedDateTime'])
            # for list_key in ['LcoLineItems', 'CcuItems', 'StorageItems']:
            #     if not entry.get(list_key):
            #         entry.pop(list_key, None)
            #
            # if storage_details := item.get('StorageDetails'):
            #     if good_details := {k: v for k, v in storage_details.items() if (v or v is False or v == 0)}:
            #         entry['StorageDetails'] = good_details

            # AirFreightLineItems: compress dimensions into a single field
            dim_fields = ['LengthInCm', 'WidthInCm', 'HeightInCm']
            air_freight = []
            for af in item.get('AirFreightLineItems', []):
                mapped_af = {k: v for k, v in af.items() if k not in dim_fields and (v or v is False or v == 0)}
                if any(af.get(x) for x in dim_fields):
                    mapped_af['Dimensions_LWH'] = 'x'.join([str(af.get(x, '')) for x in dim_fields]) + ' cm'
                air_freight.append(mapped_af)
            if air_freight:
                entry['AirFreightLineItems'] = air_freight

            # Localise datetimes
            for k in dt_keys:
                if k in entry:
                    entry[k] = localise_dt(entry[k], self.c['timezone'])

            # Add URLs
            if request_id := item.get('RequestId'):
                entry['url'] = self.vor_url.request(request_id)
            if flight_id := item.get('FlightId'):
                entry['flight_url'] = self.vor_url.flight(flight_id)
            if plan_sailing_id := item.get('PlanSailingId'):
                entry['voyage_url'] = self.vor_url.voyage(plan_sailing_id + 'outbound')

            mapped.append(entry)
        return mapped

    async def query(self, status: str = None, verbose=True, **kwargs) -> dict:
        """Fetch all flight requests for the organisation; grouped by State (PENDING, APPROVED, REJECTED).
        If status is set, it must use only those values, optionally several alternated with '|' (e.g. 'PENDING|APPROVED');
        the returned dict then contains only the requested keys (empty list if none in that state).
        Keys not in the allowed set are dropped; if none remain, all states are returned (same as omitting status).
        """
        # Accept _id as an alias of status for subscription pipeline standardisation purposes
        _id = kwargs.pop('_id', None)
        if status is None and _id is not None:
            status = _id

        data = await self._send_request(session=self.session, verbose=verbose, params=dict(organization=self.c['org']))
        if not isinstance(data, list):
            return dict(status='no data available')

        mapped = self._data_mapping(data)
        by_status = defaultdict(list)
        for r in mapped:
            by_status[r['State']].append(r)

        if ((status := (status or '').strip()) and
            (filtered := [p for p in (part.strip() for part in status.split('|')) if p and p in self._ALLOWED_STATES])):
            return {k: by_status.get(k, []) for k in filtered}
        return dict(by_status)


class FlightRequestApproval(CustomerAPIBaseClass):
    def __init__(self, c: ConfigSchema, session=None):
        super().__init__(c, supported_orgs=['Shell UK'])
        self.url_endpoint_base = config.customer_api.url.flight_request
        self.session = session

    async def query(self, approve: bool, request_id: str, comments: str, verbose=True, **kwargs) -> dict:
        """Approve or reject a flight request."""
        suffix, base_verb, participle, at, by = [  # instead of the ternary `... if approve else ...` everywhere
            ('/Reject', 'reject', 'rejected', 'RejectedAt', 'RejectedBy'),
            ('/Approve', 'approve', 'approved', 'ApprovedAt', 'ApprovedBy')
        ][approve]

        if '@' not in (user_responsible := self.c['user_id']):
            return dict(status='The current user is not allowed to approve/reject flight requests; they should ask to'
                               'list their subscriptions and they will be prompted to bind their email to this account.')

        self.url_endpoint = self.url_endpoint_base + suffix
        params = dict(
            organization=self.c['org'],
            requestId=request_id,
            comments=comments,
            userResponsible=user_responsible,
        )
        data = await self._send_request(method='POST', session=self.session, verbose=verbose, params=params)

        if isinstance(data, dict) and data.get('State') == participle.upper():
            out = {k: v for k, v in data.items() if k in ['RequestId', 'State', at, by, 'Rescinded', 'RescindedAt', 'RescindedBy']}

            notes = []
            if out.get('Rescinded'):
                notes.append(f'This request was rescinded, so it being {participle} is now inconsequential.')

            # Check whether the state change is not due to this request (i.e. older than 10s or by someone else)
            already_done = out.get(by) != user_responsible
            if done_at := out.get(at):
                try:
                    done_at_dt = datetime.fromisoformat(done_at)  # vv tzinfos need to be both present or both absent
                    now_dt = datetime.now(done_at_dt.tzinfo) if done_at_dt.tzinfo else datetime.now()
                    already_done |= (now_dt - done_at_dt).total_seconds() > 10
                except (TypeError, ValueError):
                    pass
            if already_done:
                notes.append(f'This request was already {participle}.')

            if notes:
                out['Note'] = '\n'.join(notes)

            return out
        else:
            return dict(status=f'Could not {base_verb} flight request {request_id}; likely an incorrect ID.')


class GlobalDescriptionSearch(AISearchBaseClass):
    """Perform a search across all search indexes."""

    def __init__(self, c: ConfigSchema):
        super().__init__(c, supported_orgs=['CHEVRON'])
        self.url_endpoint = config.ai_search.url.global_search
        self.lookup_classes = dict(
            # AI Search type names
            flights=FlightsByID,
            movement_requests=MovementRequestByID,
            priorities=MovementRequestByID,  # they are just MRs
            road_transport_jobs=RoadTransportJobsByID,
            shipments=ShipmentsByID,
            voyage_cargo_manifests=VoyageCargoManifestsByID,
            # VOR Search type names
            Container=ContainerEventsByID,
            Flight=FlightsByID,
            MovementRequest=MovementRequestByID,
            RoadTransportJob=RoadTransportJobsByID,
            Shipment=ShipmentsByID,
            Voyage=VoyagesByID,
            WorkOrder=WorkOrderByID
        )

    async def get_data(self, data: list[dict], limit=config.ai_behaviour.default_limit, concurrent_requests_limit=20, verbose=True):
        """Overrides the base class method to handle multiple object types."""
        async def async_wrapper(x):
            return x

        async with ClientSession(connector=TCPConnector(limit=concurrent_requests_limit)) as session:
            apis = {object_type: _class(self.c, session) for object_type, _class in self.lookup_classes.items()}

            tasks = []
            for item in data[:limit]:
                if object_type := item.get('object_type') or item.get('type'):
                    if not (_id := item['movement_request' if object_type == 'priorities' else 'id']):
                        tasks.append(async_wrapper(item))  # priority items may have None as their MR
                    elif api := apis.get(object_type):
                        tasks.append(api.query(_id=_id, verbose=verbose, unnest_singletons=True))

            return await asyncio.gather(*tasks)

    async def call_both_searches(self, query: str):
        """Call both the global AI search and VOR Search in parallel"""
        return await asyncio.gather(
            asyncio.to_thread(self._send_request, params=dict(organisation=self.c['org'], query=query)),
            asyncio.to_thread(VorGlobalSearch(c=self.c).query, query, keep_all_and_no_lookups=True)
        )

    def query(self, query: str, call_vor_search_too: bool = True, further_processing: str = None) -> dict:
        """Search for an item in the index."""
        params = dict(organisation=self.c['org'], query=query)

        if call_vor_search_too:  # if calling both, do it in parallel
            search_results, vor_search_results = asyncio.run(self.call_both_searches(query))
        else:
            search_results = self._send_request(params=params)

        sort_key = dict(
            flights='estimated_departure_date',
            movement_requests='ros_date',
            priorities='ros_date',
            road_transport_jobs='requested_delivery_date',
            shipments='eta_date',  # no ros for shipments; eta is close
            voyage_cargo_manifests='eta_date'  # more reliable than earliest/latest ros, which are often absent
        )
        search_results = sorted(search_results, reverse=True,  # vv datetimes can be sorted lexicographically
                                key=lambda x: (x['@search.score'], x[sort_key[x['object_type']]] or ''))

        if call_vor_search_too:
            # Remove duplicates and combine
            just_ids = {r['id'].lower() for r in search_results}
            vor_search_results = [r for r in vor_search_results if r['id'].lower() not in just_ids]
            search_results = search_results + vor_search_results

        if search_results:
            top_results = [] if further_processing else asyncio.run(self.get_data(search_results))
            return self._package_data(top_results, all_results=search_results,
                                      applied_filters=params, further_processing=further_processing)
        else:
            return dict(status='no data available')


class LogisticsSummaryReports(RedisBaseClass):
    """Load LS reports from Redis, process known types, return by type (processed if known, raw otherwise)."""

    # Config for filtering and flattening known LS report types to item level
    _LS_REPORT_CONFIG = {
        'RoadTransportJobHCRTransitTimeExceededWarning': {
            'simplified_name': 'hcr transit time',  # the API removes spaces and forces lowercase
            'fields_to_keep': [
                'displayId', 'accountCode', 'clientRequestReference', 'assetIds', 'itemDescriptions',
                'hcrWarningTimeInHours', 'actualPickupDateTime', 'serviceType', 'transitTime', 'location'
            ],
            'datetime_fields': ['actualPickupDateTime'],
            'items_field': 'freights',
            'location_field': 'locationName',
            'threshold_field': 'hcrWarningTimeInHours',
            'threshold_unit': 'hours',
            'url_types_for_fields': {
                'displayId': 'road_transport_job',
                'assetIds': 'container',
                'clientRequestReference': 'movement_request',
            },
        },
        'HcrDwellTimeExceededAtLocation': {
            'simplified_name': 'hcr dwell time',  # the API removes spaces and forces lowercase
            'fields_to_keep': [
                'unit', 'materialDescription', 'origin', 'destination', 'projectCode', 'unitStatus', 'referenceNumbers',
                'totalDaysDwellTime', 'locationName', 'plannedDepartureDate', 'plannedVoyage', 'plannedVoyageUrl'
            ],
            'datetime_fields': ['plannedDepartureDate'],
            'items_field': 'units',
            'location_field': 'locationId',
            'threshold_field': 'totalDaysDwellTime',
            'threshold_unit': 'days',
            'url_types_for_fields': {
                'unit': 'container',
                'referenceNumbers': {'movement_request'},
            },
        },
        'DangerousGoodsWarning': {
            'simplified_name': 'dangerous goods',  # the API removes spaces and forces lowercase
            'fields_to_keep': [
                'movementRequestNumber', 'location', 'requestDescription', 'statusDisplayName',
                'ccuId', 'finalDestination', 'severity', 'dgNames'
            ],
            'datetime_fields': [],
            'items_field': 'items',
            'location_field': 'lastSeenLocation',
            'url_types_for_fields': {
                'movementRequestNumber': 'movement_request',
                'ccuId': 'container',
            },
        },
        'NewMovementRequests': {
            'simplified_name': 'new cmrs',  # the API removes spaces and forces lowercase
            'fields_to_keep': ['projectCode', 'chargeToDepartmentName', 'movementRequestNumber', 'statusDisplayName',
                               'createdDateTime', 'requiredOnSiteDate', 'finalDestination', 'requestDescription',
                               'dgNames', 'materialsDescription', 'isPriority', 'isHCR'],
            'datetime_fields': ['createdDateTime', 'requiredOnSiteDate'],
            'items_field': 'movementRequests',
            'url_types_for_fields': {
                'movementRequestNumber': 'movement_request',
            },
        },
    }

    def __init__(self, c: ConfigSchema, session=None):
        super().__init__(c, supported_orgs=['CHEVRON'], cache_path=f'{config.redis.logistics_summary}::{c['org']}')
        self.all_reports = []
        self.processed_reports = {}

    def _data_mapping(self, items: list, type_to_filter: str = None, filters: dict = None) -> dict:
        """Process known report types; not extracting a specific type at this stage, but discarding unknown ones.
        Note: 'location' and 'threshold' fields are added automatically (the latter only if supported for that type).
        """
        if not items:
            return {}

        # "Unpack" new-CMR reports for different projects into the list of all LS reports
        unpacked = []
        for ls_report in items:
            if ls_report.get('type') == 'NewMovementRequests':
                unpacked.extend([dict(type='NewMovementRequests', **child) for child in ls_report.get('projectCodeItems', [])])
            else:
                unpacked.append(ls_report)

        known, unknown = defaultdict(list), defaultdict(list)
        for ls_report in unpacked:
            report_type = ls_report.get('type')
            if (type_config := self._LS_REPORT_CONFIG.get(report_type)) is None:
                unknown[report_type].append({k: v for k, v in ls_report.items() if k != 'type'})
                continue

            # Work on a copy so the original variable (i.e. self.all_reports) is not modified
            ls_report = copy.deepcopy(ls_report)

            # Flatten to item level
            if not (item_list := ls_report.pop(type_config.get('items_field'), None)):
                continue
            units_df = pd.DataFrame(item_list)
            shared_df = pd.DataFrame([ls_report], index=units_df.index)  # identical rows of shared info to concat to
            df = pd.concat([units_df, shared_df], axis=1)

            # Standardise the location column name
            df.rename(columns={type_config.get('location_field'): 'location'}, inplace=True)

            # Set the threshold value to filter by
            if thresh_val := type_config.get('threshold_field'):
                df['threshold'] = df[thresh_val] = df[thresh_val].astype(float)

            # Filter if necessary
            if report_type == type_to_filter:
                df = filter_dataframe(df, filters=filters or {})

            # Extract only the columns of interest and convert rows to dictionaries
            df = df[df.columns.intersection(type_config.get('fields_to_keep'))]
            if df.empty:
                continue
            df = df.where(pd.notna(df), None)  # NaN/NA to None (prevents later issues, e.g. rejection by strict JSON parsers)
            out_dicts = df.to_dict(orient='records')

            # Localise datetimes and add urls fields if possible
            for out_d in out_dicts:
                for dt_field in type_config.get('datetime_fields', ()):
                    if dt_str := out_d.get(dt_field):
                        out_d[dt_field] = localise_dt(dt_str, self.c['timezone'])
                for id_field, id_type in type_config.get('url_types_for_fields', {}).items():
                    if _id := out_d.get(id_field):
                        # Extract multiple ids if present (could be in an iterable or inside a string with separators)
                        ids = _id if isinstance(_id, (set, list)) else [_id]
                        ids = [___id for __id in ids if isinstance(__id, str) for ___id in re.split(r',|\s+', __id) if ___id]

                        # Generate urls and add field if successful
                        urls = [url for __id in ids if (url := self.vor_url.parametrised(self.c['org'], __id, id_type))]
                        if len(urls) == 0:
                            continue            # vv because want to keep it a singleton list if _id was an iterable
                        if len(urls) == 1 and not isinstance(_id, (set, list)):
                            out_d[f'{id_field}_url'] = urls[0]
                        else:
                            out_d[f'{id_field}_urls'] = urls

            known[report_type].extend(out_dicts)

        return dict(known=dict(known), unknown=dict(unknown))

    async def query(self, _id: str = None, filters: dict = None, report_type_is_simplified = True, verbose = True, **kwargs) -> dict:
        """Return the logistics summary reports: the given type if specified (that is what _id is for), all if not.
        Note: _id is not just called report_type for consistency with other ByID endpoints since called in batches for subscriptions.
        Also note: by default the _id is expected to be a simplified report type, not the actual cached name (see self._LS_REPORT_CONFIG).
        The filters variable is only used if _id is present, and it is a dict of that report's payload
        field names (plus the often automatically added 'location' and 'threshold' fields)
        mapped to conditions: a scalar for equality, a list for inclusion, or a comparison operator tuple (e.g. ('>=', 1)).
        """
        if _id and report_type_is_simplified:
            if match := [wt for wt, fields in self._LS_REPORT_CONFIG.items() if fields['simplified_name'] == _id]:
                _id = match[0]
            else:
                raise ValueError(f'Unsupported simplified LS report type: {_id}')
        data = self._cache.get_entries()
        self.all_reports = data.get('', {}).get('items') or []
        self.processed_reports = self._data_mapping(self.all_reports, _id, filters)
        out = {_id: self.processed_reports['known'].get(_id, [])} if _id else self.processed_reports['known']
        out['url'] = vor_url_list(self.c['org'])['logisticsSummary']
        return out


class MovementRequestsByDescription(AISearchBaseClass):
    """Uses the movement requests AI search service to find items based on their description."""

    def __init__(self, c: ConfigSchema):
        super().__init__(c, supported_orgs=['CHEVRON'])
        self.url_endpoint = config.ai_search.url.mrs

    def query(self, query: str = None, status: str = None,                          # Key filters
        mode_of_transport: str = None, stage: str = None,
        project_code: str = None, container_ids: str = None,                        # Reference numbers
        flights: str = None, road_transport_jobs: str = None, voyages: str = None,
        purchase_order: str = None, parents: str = None,
        destination: str = None, latest_event_location: str = None,                 # Locations
        hazmat: bool = None, hcr: bool = None, priority: bool = None,               # Other features
        ros_date: str = None, latest_event_date: str = None,                        # Dates
        further_processing: str = None) -> dict:
        """Search for an item in the index."""
        query = query if query else '*'

        allowed_statuses = ['Delivered', 'InProgress', 'Planned', 'Booked',  # << shorthands allowed; not in prompt since duplicating other filters
            'Delivered-Road', 'Delivered-Marine', 'Delivered-Air', 'Delivered-Shipment',
            'AwaitingPickup', 'PlannedOnVoyage', 'BookedShipment', 'InProgress-OnTruck',
            'InProgress-OnVessel', 'InProgress-OnAircraft', 'InProgress-StagedAtSupplyBase',
            'InProgress-WithTransportProvider', 'InProgress-Shipment', 'Unknown'
        ]
        if status and not set(statuses := status.split('|')).issubset(allowed_statuses):  # protect against hallucinated status
            disambiguation = {'Upcoming': 'Planned|Booked|AwaitingPickup', 'In Progress': 'InProgress', 'Finished': 'Delivered'}
            status = '|'.join([fixed_s for s in statuses if (fixed_s := s if s in allowed_statuses else disambiguation.get(s))])
            status = status or None  # if not there, do not filter by status at all (instead of causing an API error)

        if purchase_order:  # vv strip the PO prefix if the AI forgot to remove it on its own
            if not purchase_order.isnumeric() and (match := re.search(r'\d+', purchase_order)):
                purchase_order = match.group(0)
            query = f'PO{purchase_order}|{purchase_order}' if query == '*' else f'{query} {purchase_order}'

        search_results = self._send_request(params=(params := dict(
            organisation=self.c['org'],                                             # Key filters
            query=query, status=status,
            mode_of_transport=mode_of_transport, stage=stage,
            project_codes=project_code, container_ids=container_ids,                # Reference numbers
            flights=flights, road_transport_jobs=road_transport_jobs,
            voyages=voyages, parents=parents,
            destination=destination, latest_event_location=latest_event_location,   # Locations
            hazmat=hazmat, hcr=hcr, priority=priority,                              # Other features
            ros_date=self.make_iso(ros_date),                                       # Dates
            latest_event_date=self.make_iso(latest_event_date),
        )))

        if fallback := self.by_id_fallback('movement_request', MovementRequestByID, search_results, params):
            return fallback

        search_results = sort_dicts(search_results, [('ros_date', True)])
        non_index_data = [] if further_processing else self.non_index_data_pipeline(search_results, params)

        return self._package_data(non_index_data, limit=len(non_index_data), all_results=search_results,
                                  applied_filters=params, further_processing=further_processing)

    def non_index_data_pipeline(self, search_results: list, params: dict, limit: int = config.ai_behaviour.default_limit):
        """Retrieve data from the Customer API and enhance and/or reduce it as required."""
        return asyncio.run(self.get_data(search_results, MovementRequestByID, limit=limit, unnest_singletons=True))


class MovementRequestByID(CustomerAPIBaseClass):
    status_to_mode_and_stage = {
        # 'Unknown': ('Land|Sea|Air', 'Planned|In Progress|Delivered'),     # << this is how they are indexed
        'Unknown': ('Unknown', 'Unknown'),                                  # << this is how to show them
        'In Progress - Staged At Supply Base': ('Unknown', 'In Progress'),
        'Awaiting Pickup': ('Land', 'Planned'),
        'In Progress - With Transport Provider': ('Land', 'In Progress'),
        'In Progress - On Truck': ('Land', 'In Progress'),
        'Delivered - Road': ('Land', 'Delivered'),
        'Booked Shipment': ('Sea', 'Planned'),
        'Planned On Voyage': ('Sea', 'Planned'),
        'In Progress - Shipment': ('Sea', 'In Progress'),
        'In Progress - On Vessel': ('Sea', 'In Progress'),
        'Delivered - Shipment': ('Sea', 'Delivered'),
        'Delivered - Marine': ('Sea', 'Delivered'),
        'In Progress - On Aircraft': ('Air', 'In Progress'),
        'Delivered - Air': ('Air', 'Delivered')
    }

    def __init__(self, c: ConfigSchema, session=None):
        super().__init__(c, supported_orgs=['CHEVRON'])
        self.url_endpoint = config.customer_api.url.movement_request
        self.required_fields = [
            'LastUpdatedAtDateTime',
            'Organization',
            'Lines',
            'Status',
            'HasEvents'
        ]
        self.session = session

    def _data_mapping(self, data) -> dict:
        """Method to reduce the customer API data and extract useful fields."""
        redundant_fields = [
            'MovementRequestNumber',  # renamed to id
            'MovementRequestSearchReference',  # the input which was passed to the endpoint
            'Consignee',  # personal info
            'HasEvents',
            'LatestEvent',  # Also the first item in the Events field
            'ReceiverLocation',  # personal info
            'Status',  # 'StatusDisplayName' is present
            'StatusDisplayName',  # Renamed to 'Status' in the output
            'SenderLocation',  # personal info
        ]
        good_event_fields = [
            'CcuDisplayId',
            'IsLooseItem',
            'DateTime',
            'DetailedStatus',
            'LastSeenLocation',
            'Origin',
            'Destination',
            'VoyageId',
            'Vessel',
            'JobId',  # renaming it RoadTransportJobId later
            'FlightId',
        ]

        # Summarise fields of interest from cargo lines
        descriptions, pos, hcr, hazmat, order_ref_nos, split_child_requests, split_parent_requests, reverse_parent, packs, tares = \
            None, [], None, None, [], [], [], [], [], []
        if lines := data.pop('Lines', None):
            descriptions = set(descr for line in lines if (descr := line.get('matDescription')))
            descriptions = ' '.join(set(descr.strip().replace('\n', ' ') for descr in descriptions))  # some pos are '0' vv
            order_ref_nos = set(orn for line in lines if (orn := line.get('orderRefNo')))  # these are MRs as well
            pos = {po for line in lines for po in (line.get('poNumber') or '').replace(' ', '').split(',') if po and len(po) > 5}
            hcr = any(line.get('IsHCR') for line in lines)
            hazmat = any(line.get('HAZMAT') for line in lines)
            split_child_requests = set(scr for line in lines if (scr := line.get('splitChildRequests')))
            split_parent_requests = set(spr for line in lines if (spr := line.get('splitParentRequests')))
            reverse_parent = set(rpc for line in lines if (rpc := line.get('reverseParentCMR')))
            packs = set(pack for line in lines if (pack := line.get('extItemRefNo')))
            tares = set(tare for line in lines if (tare := line.get('tareLabel')))

        # Streamline parent info if present
        if parents := data.pop('Parents', None):
            parents = sorted([(p['HierarchyLevel'], p['MovementRequestNumber']) for p in parents
                              if p and {'HierarchyLevel', 'MovementRequestNumber'}.issubset(p.keys())])
            # Remove hierarchy level since now sorted, and remove self if present
            parents = [p[1] for p in parents if p[1] != data['MovementRequestNumber']]

        # Reference numbers from events
        projects, voyages, rtjs, flights, mapped_events = [], [], [], [], []
        if events := data.pop('Events', None):
            flights = set(flight for event in events if (flight := event['FlightId']))
            projects = set(proj for event in events if (proj := event['ProjectCode']))
            rtjs = set(rtj for event in events if (rtj := event.get('JobId')))
            for event in events:  # needed until https://dev.azure.com/streambadev/VOR/_workitems/edit/8478
                if event.get('VoyageId'):
                    event['VoyageId'] = re.sub('inbound|outbound', '', event['VoyageId'])
            voyages = set(voy for event in events if (voy := event['VoyageId']))
            mapped_events = [{'RoadTransportJobId' if k == 'JobId' else k: v
                              for k, v in event.items() if k in good_event_fields if v} for event in events]

        status = data.get('StatusDisplayName')
        mode, stage = self.status_to_mode_and_stage.get(status, self.status_to_mode_and_stage['Unknown'])

        mapped_data = dict(
            id=data['MovementRequestNumber'],
            Status=status,
            ModeOfTransport=mode,
            Stage=stage,
            Parents=parents,
            Flights=list(flights),
            Projects=list(projects),
            RoadTransportJobs=list(rtjs),
            Voyages=list(voyages),
            MaterialDescriptions=descriptions,
            OrderReferenceNumbers=list(order_ref_nos),
            PONumbers=list(pos),
            HCR=hcr,
            Hazmat=hazmat,
            Events=mapped_events[:5],  # some MRs can have hundreds of events,
            SplitChildRequests=list(split_child_requests),
            SplitParentRequests=list(split_parent_requests),
            ReverseParent=list(reverse_parent),
            Packs=list(packs),
            Tares=list(tares),
        )
        mapped_data.update({k: v for k, v in data.items() if k not in redundant_fields})  # add back other fields last

        # Convert list fields to strings for better SQL processing
        #   Events, PlannedEvents, and TransportPlan are lists of dicts worth unnesting in caching
        for k in ['Parents', 'Project', 'MovementRequestEtaJustification']:
            mapped_data[k] = ' '.join(mapped_data.get(k) or [])

        # Add urls for related entities (do not add fields if they would be empty)
        mapped_data['url'] = self.vor_url.movement_request(data['MovementRequestNumber'])
        if order_ref_nos:                                   # ^^ would work for packs/tares as well, but using the MR
            orn_urls = [self.vor_url.movement_request(orn) for orn in order_ref_nos if orn.upper().startswith(('CMR', 'LMR'))]
            if orn_urls:
                mapped_data['order_reference_nos_urls'] = ' '.join(orn_urls)
        if ccu := mapped_data.get('CcuId'):
            mapped_data['container_url'] = self.vor_url.container(ccu)
        if shipment_details := mapped_data.pop('ShipmentDetails', None):
            mapped_data.update(shipment_details)  # Unnest shipment details if present
            if shipment_id := shipment_details.get('ShipmentNo'):
                mapped_data['shipment_url'] = self.vor_url.shipment(shipment_id)
        if flight_urls := [self.vor_url.flight(flight) for flight in flights]:
            mapped_data['flight_urls'] = ' '.join(flight_urls)
        if rtjs:
            # The pattern needs to be checked because the field can also contain values like '578120911-Leg-1'
            rtj_urls = [self.vor_url.road_transport_job(f'ignition-sr{match.group(1)}') for rtj in rtjs
                        if (match := re.fullmatch(r'(?:(?:ignition-)?sr)?(\d{5})', rtj, flags=re.IGNORECASE))]
            if rtj_urls:
                mapped_data['road_transport_jobs_urls'] = ' '.join(rtj_urls)
        if voyages_urls := [self.vor_url.voyage(voy) for voy in voyages]:
            mapped_data['voyages_urls'] = ' '.join(voyages_urls)

        # Note: no dt localisation operation is required here since this endpoint respects the UseLocalTime header

        return mapped_data

    def _validate_fields(self, data: dict) -> bool:
        """Dumb validation method to check at least one of the required fields exists for a movement request.
        Should be replaced with a more robust model in future (pydantic).
        """
        return any([data.get(key) for key in self.required_fields])

    async def query(self, _id: str, verbose=True, unnest_singletons=False, **kwargs) -> dict:
        """Send query to endpoint and fetch data.
        The unnest_singletons argument is meant for cases in which it is already known that only single results will be
        returned, i.e. when looking up directly by MR id (usually in a batch of requests to then be grouped up into a df).
        """
        data = await self._send_request(
            session=self.session,
            verbose=verbose,
            params=dict(
                movementRequestNumber=_id,
                role=self.c['org'])
        )
        if data and self._validate_fields(data[0]):
            if unnest_singletons:
                if len(data) > 1:
                    logging.warning('The MR retrieval was told to (expect and) unnest a singleton result for input %s, '
                                    'but %s results were retrieved. Returning the first one unnested, but warning about it '
                                    'since this is meant to be a structural issue, not something which can happen randomly.',
                                    _id, len(data))
                return self._data_mapping(data[0])
            else:
                return {mr['MovementRequestNumber']: self._data_mapping(mr) for mr in data}
        else:
            return {"status": "no data available, it may be that the movement request is not yet in the system"}


class NotificationAgent(LangFlowBaseClass):
    """Run the Notification Agent."""

    def __init__(self, c: ConfigSchema):
        super().__init__(c, supported_orgs=['CHEVRON', 'Shell UK', 'ExxonMobilGuyana'])
        self.flow_id = config.langflow.notification_agent

    def query(
        self,
        org: str,
        user_id: str,
        messaging_account: str,
        user_display_name: str,
        query: str,
        message_history: ChatMessageHistory
    ):
        payload = dict(
            session_id='cgpt-' + re.sub(r'[@._]', '-', messaging_account),
            tweaks={  # i.e. overrides to any input to any component in the flow
                # Very useful note on the keys of tweaks: they can be either the arbitrary name given to that node or
                # the one generated automatically (i.e. the generic name plus a few random chars, visible in the node or
                # when generating tweaks with the UI under Publish > API Access > Tweaks).
                'Inputs': {
                    'organisation': org,
                    'current_user_id': user_id,
                    'current_user_name': user_display_name,
                    'current_user_messaging_account': messaging_account,
                    'instructions': query,
                    'message_history': '\n'.join(format_message_history(message_history))
                }
            }
        )
        response = self._send_request(payload=payload)
        if response:
            return response
        else:
            return ('Apologies; unfortunately the Notification Agent seems to be unreachable. '
                    'The developers have been notified. '
                    'May I help you on some other topic for the moment?')


class PrioritiesByDescription(AISearchBaseClass):
    """Uses the priorities AI search service to find items based on their description."""

    def __init__(self, c: ConfigSchema):
        super().__init__(c, supported_orgs=['CHEVRON'])
        self.url_endpoint = config.ai_search.url.priorities

    def query(self, query: str = None, status: str = None,                              # Key filters
        priority_type: int = None, mode_of_transport: str = None,
        destination: str = None, # current_location: str = None,                        # Locations
        ros_date: str = None, shipped_date: str = None,                                 # Dates
        further_processing: str = None) -> dict:
        """
        Search for an item in the index
        """
        query = query if query else '*'

        search_results = self._send_request(params=(params := dict(
            organisation=self.c['org'],                                                 # Key filters
            query=query, status=status,
            priority_type=priority_type, mode_of_transport=mode_of_transport,
            destination=destination, # location=current_location,                       # Locations
            ros_date=self.make_iso(ros_date),                                           # Dates
            shipped_date=self.make_iso(shipped_date),
        )))
        search_results = sort_dicts(search_results, [('ros_date', True)])

        non_index_data = [] if further_processing else self.non_index_data_pipeline(search_results, params)

        return self._package_data(non_index_data, limit=len(non_index_data), all_results=search_results,
                                  applied_filters=params, further_processing=further_processing,
                                  metadata=dict(extra='Do not ignore results with no movement_request'))

    def non_index_data_pipeline(self, search_results: list, params: dict, limit: int = config.ai_behaviour.default_limit):
        """Retrieve data from the Customer API and enhance and/or reduce it as required."""
        # Not all priority results have a linked movement request, and some movement requests are in multiple results.
        results_with_mrs = defaultdict(list)  # MR -> list of search_results indices in which it appears
        for i, res in enumerate(search_results):
            if mr := res.get('movement_request'):
                results_with_mrs[mr].append(i)

        top_results = search_results[:limit].copy()

        # Look up and inject MR data into the top_results which mention one
        if mrs_within_limit := [mr for mr, indices in results_with_mrs.items() if any(i < limit for i in indices)]:
            mr_data = asyncio.run(self.get_data(mrs_within_limit, MovementRequestByID, limit, unnest_singletons=True))
            mr_data = {mr_d['id']: mr_d for mr_d in mr_data}
            for mr, mr_d in mr_data.items():
                for i in results_with_mrs[mr]:  # again, because multiple results might reference the same MR
                    top_results[i]['movement_request_details'] = mr_d

        return top_results


class RoadTransportJobsByDescription(AISearchBaseClass):
    """Uses the road transport jobs AI search service to find items based on their description."""

    def __init__(self, c: ConfigSchema):
        super().__init__(c, supported_orgs=['CHEVRON'])
        self.url_endpoint = config.ai_search.url.road_transport

    def query(self, query: str = None, status: str = None,                          # Key filters
        project_codes: str = None, container_ids: str = None,                       # Reference numbers
        movement_requests: str = None, trip_id: str = None,
        pickup_location: str = None, delivery_location: str = None,                 # Locations
        priority: bool = None, dangerous: bool = None, hcr: bool = None,            # Other features
        # latest_event_date: str = None,                                            # Dates
        # planned_pickup_date: str = None, estimated_pickup_date: str = None,
        # planned_delivery_date: str = None, estimated_delivery_date: str = None,
        requested_pickup_date: str = None, actual_pickup_date: str = None,
        requested_delivery_date: str = None, actual_delivery_date: str = None,
        further_processing: str = None) -> dict:
        """Search for an item in the index."""
        query = query if query else '*'

        search_results = self._send_request(params=(params := dict(
            organisation=self.c['org'],                                             # Key filters
            query=query, status=status,
            project_codes=project_codes, container_ids=container_ids,               # Reference numbers
            movement_requests=movement_requests, trip_id=trip_id,
            pickup_location=pickup_location, delivery_location=delivery_location,   # Locations
            priority=priority, dangerous=dangerous, hcr=hcr,                        # Other features
            # latest_event_date=self.make_iso(latest_event_date),                   # Dates
            requested_pickup_date=self.make_iso(requested_pickup_date),
            # planned_pickup_date=self.make_iso(planned_pickup_date),
            # estimated_pickup_date=self.make_iso(estimated_pickup_date),
            actual_pickup_date=self.make_iso(actual_pickup_date),
            requested_delivery_date=self.make_iso(requested_delivery_date),
            # planned_delivery_date=self.make_iso(planned_delivery_date),
            # estimated_delivery_date=self.make_iso(estimated_delivery_date),
            actual_delivery_date=self.make_iso(actual_delivery_date)
        )))

        if fallback := self.by_id_fallback('road_transport_job', RoadTransportJobsByID, search_results, params):
            return fallback

        search_results = sort_dicts(search_results, [('requested_delivery_date', True)])
        non_index_data = [] if further_processing else self.non_index_data_pipeline(search_results, params)

        return self._package_data(non_index_data, limit=len(non_index_data), all_results=search_results,
                                  applied_filters=params, further_processing=further_processing)

    def non_index_data_pipeline(self, search_results: list, params: dict, limit: int = config.ai_behaviour.default_limit):
        """Retrieve data from the Data Enhancer and enhance and/or reduce it as required."""
        return asyncio.run(self.get_data(search_results, RoadTransportJobsByID, limit))


class RoadTransportJobsByID(DataEnhancerAPIBaseClass):
    def __init__(self, c: ConfigSchema, session=None):
        super().__init__(c, supported_orgs=['CHEVRON'])
        self.url_endpoint = config.data_enhancer.url.road_transports_by_id
        self.session = session

    def _data_mapping(self, data, localised_datetimes=True) -> dict:
        """Method to reduce the Data Enhancer API data and extract useful fields."""
        good_keys = [  # I.e. fields which are of interest and already in the required format
            'actualDeliveryDateTime',
            'actualPickupDateTime',
            'clientProjectCode',
            'containsHighCostRental',
            'containsPriorityFreight',
            'displayId',
            'estimatedDeliveryDateTime',
            'estimatedPickupDateTime',
            'intermediateAddresses',
            'jobStatus',
            'notes',
            'organization',
            'plannedDeliveryDateTime',
            'plannedPickupDateTime',
            'requestedDeliveryDateTime',
            'requestedPickupDateTime',
            'serviceProvider',
            'tripId'
        ]
        mapped_data = {k: v for k, v in data.items() if k in good_keys}

        mapped_data['pickupLocation'] = (data.get('pickupAddress') or {}).get('locationName')
        mapped_data['deliveryLocation'] = (data.get('deliveryAddress') or {}).get('locationName')

        if _id := data.get('entityId'):
            mapped_data['url'] = self.vor_url.road_transport_job(_id)

        if mrs := data.get('clientRequestReference'):
            # Example reformatting: 'LMR100704 - 100784' -> 'LMR100704, LMR100784'
            mrs = [mrs[:3] + mr if mr[1:3] != 'MR' else mr for mr in mrs.split(' - ')]
            mapped_data['movementRequests'] = ' '.join(mrs)
            mapped_data['movementRequestUrls'] = ' '.join(self.vor_url.movement_request(mr) for mr in mrs)

        if items := data.get('consignmentItems'):
            mapped_data['containerIds'] = []
            mapped_data['containerUrls'] = []
            mapped_data['containsDangerousGoods'] = False
            mapped_data['consignmentItems'] = []
            dim_fields, weight_fields = ['length', 'width', 'height', 'dimensionUnits'], ['weight', 'weightUnits']
            bad_item_keys = ['itemId', 'manifestId', 'itemDescription', 'dgInfo', 'comments'] + dim_fields + weight_fields
            for item in items:
                mapped_item = {k: item[k] for k in item if k not in bad_item_keys}

                if mr := item.get('manifestId'):
                    mapped_item['movementRequest'] = mr

                # Non-ccu strings can end up in the itemId field atm; therefore checking below
                if ccu := [x for x in id_filter(item.get('itemId') or '') if re.fullmatch(REGEX_MAPPING[self.c['org']]['container'], x)]:
                    mapped_item['containerId'] = ccu[0]  # if there is a match there can only be one ccu per item
                    mapped_data['containerIds'].append(ccu[0])
                    mapped_data['containerUrls'].append(self.vor_url.container(ccu[0]))

                mapped_item['description'] = item.get('itemDescription', '')
                if dgInfo := item.get('dgInfo'):  # keep only some info if present
                    details = [f"{info.get('quantity', '')} {info.get('properShippingName', '')}" for info in dgInfo]
                    mapped_item['description'] += ('; ' if mapped_item['description'] else '') + ', '.join(details)

                if (comments := item.get('comments')) and comments != item.get('itemId'):  # often just the ccu again
                    mapped_item['comments'] = comments

                if set(dim_fields).issubset(item.keys()):
                    mapped_item['dimensions'] = 'x'.join([str(item[x]) for x in dim_fields[:3]]) + item['dimensionUnits']

                if set(weight_fields).issubset(item.keys()):
                    mapped_item['weight'] = str(item['weight']) + item['weightUnits']

                if item.get('isDangerousGoods'):
                    mapped_data['containsDangerousGoods'] = True

                mapped_data['consignmentItems'].append(mapped_item)
            mapped_data['containerIds'] = ' '.join(mapped_data['containerIds'])
            mapped_data['containerUrls'] = ' '.join(mapped_data['containerUrls'])

        if events := data.get('events', []):
            good_e_keys = ['eventType', 'eventTimestamp', 'eventClassification']
            mapped_data['events'] = [{k: event[k] for k in event if k in good_e_keys} for event in events]

        if localised_datetimes:
            for k in ['actualDeliveryDateTime', 'actualPickupDateTime', 'plannedDeliveryDateTime', 'plannedPickupDateTime',
                      'requestedDeliveryDateTime', 'requestedPickupDateTime', 'estimatedPickupDateTime', 'estimatedDeliveryDateTime']:
                if k in mapped_data:
                    mapped_data[k] = localise_dt(mapped_data[k], self.c['timezone'])
            if 'events' in mapped_data:  # not compressing these two lines into a .get because need to edit the values
                for e in mapped_data['events']:
                    e['eventTimestamp'] = localise_dt(e['eventTimestamp'], self.c['timezone'])

        return mapped_data

    async def query(self, _id: str, verbose=True, localised_datetimes=True, **kwargs) -> dict:
        """Send query to endpoint and fetch data."""
        formatted_id = _id if _id.startswith('ignition-') else 'ignition-' + _id.lower()
        data = await self._send_request(session=self.session, verbose=verbose,
                                        params=dict(id=formatted_id, organization=self.c['org']))

        return self._data_mapping(data, localised_datetimes=localised_datetimes) if data else dict(status='no data available')


class RoadTransportJobsVorSearch(VorSearchBaseClass):
    """Uses the road transport jobs Vor Search service to find jobs by description and structured filters."""

    def __init__(self, c: ConfigSchema):
        super().__init__(c, supported_orgs=['CHEVRON'])
        self.url_endpoint = config.vor_search.url.road_transport_jobs_search

    def query(self, search_term: str = None, date_ranges: str = None, sort: str = None,
        priority: bool = None, dangerous: bool = None, hcr: bool = None,
        further_processing: str = None) -> dict:
        """Search road transport jobs via the Vor Search API, enrich from Data Enhancer, and package results."""
        return self._query_pipeline(search_term, date_ranges, sort,
            other_filters=dict(
                containsPriorityFreight=priority,
                isDangerous=dangerous,
                containsHighCostRental=hcr,
            ),
            date_fields=[
                'latestEventDate', 'requestedPickupDateTime', 'plannedPickupDateTime',
                'estimatedPickupDateTime', 'actualPickupDateTime', 'requestedDeliveryDateTime', 'plannedDeliveryDateTime',
                'estimatedDeliveryDateTime', 'actualDeliveryDateTime', 'lastIndexedAt'
            ],
            by_id_fallback_patterns=['road_transport_job'],
            by_id_endpoint_class=RoadTransportJobsByID,
            further_processing=further_processing
        )

    def non_index_data_pipeline(self, search_results: list, params: dict, limit: int = config.ai_behaviour.default_limit):
        """Retrieve road transport job details from the Data Enhancer for each search hit."""
        return super().non_index_data_pipeline(search_results, params, RoadTransportJobsByID, 'jobNumber', limit)


class ShipmentsByDescription(AISearchBaseClass):
    """Uses the shipments AI search service to find shipments based on their description."""

    def __init__(self, c: ConfigSchema):
        super().__init__(c, supported_orgs=['CHEVRON'])
        self.url_endpoint = config.ai_search.url.shipments

    def query(self, query: str = None, status: str = None,                                  # Key filters
        project_code: str = None, purchase_order: str = None, container_id: str = None,     # Reference numbers
        origin: str = None, destination: str = None, weight: str = None,                    # Other features
        added_date: str = None, eta_date: str = None,                                       # Dates
        # ros_date: str = None, transport_date: str = None,
        shipped_date: str = None, arrival_date: str = None,
        further_processing: str = None) -> dict:
        """Search for an item in the index."""
        query = query if query else '*'

        if purchase_order:  # vv strip the PO prefix if the AI forgot to remove it on its own
            if not purchase_order.isnumeric() and (match := re.search(r'\d+', purchase_order)):
                purchase_order = match.group(0)
            query = f'PO{purchase_order}|{purchase_order}' if query == '*' else f'{query} {purchase_order}'

        if status == 'InProgress':  # just in case it hallucinates it from InTransit (since it is a valid MR status)
            status = 'InTransit'

        search_results = self._send_request(params=(params := dict(
            organisation=self.c['org'],                                                     # Key filters
            query=query, status=status,
            project_codes=project_code, container_ids=container_id,                         # Reference numbers
            origin=origin, destination=destination, weight=weight,                          # Other Features
            added_date=self.make_iso(added_date),                                           # Dates
            eta_date=self.make_iso(eta_date),
            # ros_date=self.make_iso(ros_date),  # seems to be always null; keeping in case this changes
            # transport_date=self.make_iso(transport_date),
            shipped_date=self.make_iso(shipped_date),
            arrival_date=self.make_iso(arrival_date),
        )))

        if fallback := self.by_id_fallback('shipment', ShipmentsByID, search_results, params):
            return fallback

        search_results = sort_dicts(search_results, [('added_date', True)])
        non_index_data = [] if further_processing else self.non_index_data_pipeline(search_results, params)

        return self._package_data(non_index_data, limit=len(non_index_data), all_results=search_results,
                                  applied_filters=params, further_processing=further_processing)

    def non_index_data_pipeline(self, search_results: list, params: dict, limit: int = config.ai_behaviour.default_limit):
        """Retrieve data from the Customer API and enhance and/or reduce it as required."""
        return asyncio.run(self.get_data(search_results, ShipmentsByID, limit))


class ShipmentsByID(CustomerAPIBaseClass):
    def __init__(self, c: ConfigSchema, session=None):
        super().__init__(c, supported_orgs=['CHEVRON', 'ExxonMobilGuyana'])
        self.url_endpoint = config.customer_api.url.shipment
        self.session = session

    def _data_mapping(self, data, localised_datetimes=True) -> dict:
        """Method to reduce the customer API data and extract useful fields."""
        mapped_data = {}
        keys = [
            "Buyer",
            "Consignee",
            "ContainerNumbers",
            "Dates",
            "Goods",
            "Organization",
            "Path",
            "PoDetails",
            "ProjectCode",
            "Provider",
            "ShipmentNo",
            "ShipmentPriority",
            "ShipmentProduct",
            "ShipmentServiceLevel",
            "ShipmentStatus",
            "Supplier",
            "TechnicalDetails",
            "TimelineEvents",
            "Transport",
            "VorShipmentCategory"
        ]
        shipments = data.get("ShipmentsInRange")
        if shipments is not None:
            # reduce data to only the required keys (if present)
            mapped_data = {k: v for k, v in shipments[0].items() if k in keys and v}

            if shipment_id := mapped_data.get('ShipmentNo'):
                mapped_data['url'] = self.vor_url.shipment(shipment_id)

            if ccus := mapped_data.get('ContainerNumbers', []):
                mapped_data['ContainerUrls'] = [self.vor_url.container(ccu) for ccu in ccus]

            if refs := shipments[0].get('ReferenceNumbers'):
                # reformat the reference numbers to a clearer structure
                refs_clean = defaultdict(list)
                for pair in refs:
                    key = pair.get("Key")
                    val = pair.get("Value")
                    if key and val:
                        refs_clean[key].append(val)

                mapped_data['ReferenceNumbers'] = dict({k: ' '.join(v) for k, v in refs_clean.items()})

            # Drop missing dates (there can be many)
            if 'Dates' in mapped_data:
                mapped_data['Dates'] = {k: v for k, v in mapped_data['Dates'].items() if v}

            # Convert list fields to strings for better SQL processing
            #   PoDetails and TimelineEvents are lists of dicts worth unnesting in caching
            mapped_data['ContainerNumbers'] = ' '.join(ccus)
            mapped_data['ContainerUrls'] = ' '.join(mapped_data.get('ContainerUrls', []))
            mapped_data['TimelineEvents'] = mapped_data['TimelineEvents'][::-1]  # most recent first

        # Note: this endpoint does NOT respect the UseLocalTime header, and it behaves differently depending on the provider:
        #   - DB Schenker has timezones for everything so localisation can take place normally.
        #   - DSV has timezones for NOTHING, and every date is local to where it happened, making automated localisation problematic.
        #       Difficult to get and assign timezones based on origin and destination, so just warn the AI instead.
        if mapped_data['Provider']:
            mapped_data['Provider'] = re.sub('DSV Panalpina', 'DSV', mapped_data['Provider'], flags=re.IGNORECASE)
        if 'DSV' in mapped_data['Provider'] or 'Blue Water' in mapped_data['Provider']:
            mapped_data['TIMEZONE_INFO'] = ('Every datetime field in this shipment data structure is localised to where its '
                                            'event happened. Mention this as a note towards the beginning of your answer.')
        elif localised_datetimes:
            mapped_data['TIMEZONE_INFO'] = (f'The timezone of every datetime field in this shipment data structure is consistent '
                                            f'({self.c['timezone'].key}), even for those in TimelineEvents and VesselDetails, '
                                            f'where other locations are listed beside them. '
                                            f'Mention this as a note towards the beginning of your answer.')
            if 'Dates' in mapped_data:
                for date in mapped_data['Dates']:
                    mapped_data['Dates'][date] = localise_dt(mapped_data['Dates'][date], self.c['timezone'])
            if 'TimelineEvents' in mapped_data:
                for event in mapped_data['TimelineEvents']:
                    for k in ['EstimatedEventDateTime', 'ActualEventDateTime']:
                        if k in event:
                            event[k] = localise_dt(event[k], self.c['timezone'])
            if 'Transport' in mapped_data and 'VesselDetails' in mapped_data['Transport']:
                for vessel in mapped_data['Transport']['VesselDetails']:
                    for k in ['EstimatedDeparture', 'EstimatedArrival']:
                        if k in vessel:
                            vessel[k] = localise_dt(vessel[k], self.c['timezone'])

        return mapped_data

    async def query(self, _id: str, verbose=True, localised_datetimes=True, **kwargs) -> dict:
        """Send query to endpoint and fetch data."""
        data = await self._send_request(session=self.session, verbose=verbose, params=dict(ShipmentNumber=_id.upper()))
        return self._data_mapping(data, localised_datetimes=localised_datetimes) if data else dict(status="no data available")


class ShipmentsVorSearch(VorSearchBaseClass):
    """Uses the shipments Vor Search service to find shipments by description and structured filters."""

    def __init__(self, c: ConfigSchema):
        super().__init__(c, supported_orgs=['ExxonMobilGuyana'])
        self.url_endpoint = config.vor_search.url.shipments_search

    def query(self, search_term: str = None, date_ranges: str = None, sort: str = None,
        status: str = None, shipment_direction: str = None, mode_of_transport: str = None,
        # origin: str = None, destination: str = None,    # would require exact matches at the moment
        further_processing: str = None) -> dict:
        """Search shipments via the Vor Search API, enrich from the Customer API, and package results."""
        res = self._query_pipeline(search_term, date_ranges, sort,
            other_filters=dict(
                status=status,
                shipmentDirection=shipment_direction,
                modeOfTransport=mode_of_transport,
                # origin=origin,
                # destination=destination,
            ),
            date_fields=['lastIndexedAt'],
            by_id_fallback_patterns=['shipment'],
            by_id_endpoint_class=ShipmentsByID,
            further_processing=further_processing
        )

        # Localise the nested date fields in the index search results
        if not (df := res.get('AllResultsDataset', {}).get('dataframe', pd.DataFrame())).empty:
            date_col_names = re.compile(r'milestones\.\d+\.(?:estimate|actual)')
            for col in [c for c in df.columns if date_col_names.fullmatch(c)]:
                df[col] = df[col].map(lambda x: localise_dt(x, self.c['timezone']))

        return res

    def non_index_data_pipeline(self, search_results: list, params: dict, limit: int = config.ai_behaviour.default_limit):
        """Retrieve shipment details from the Customer API for each search hit."""
        return super().non_index_data_pipeline(search_results, params, ShipmentsByID, 'shipmentNumber', limit)


class TransferRequestsByID(CustomerAPIBaseClass):
    def __init__(self, c: ConfigSchema, session=None):
        super().__init__(c, supported_orgs=['ExxonMobilGuyana'])
        self.url_endpoint = config.customer_api.url.transfer_request
        self.session = session

    def _data_mapping(self, data) -> dict:
        """Method to reduce the customer API data and extract useful fields."""
        bad_keys = [  # redundant/unnecessary fields or fields requiring further processing
            'ScheduledDeliveryDateTime',
            'EmailRecipients',
			'From',
            'Items',
            'RequestId',
			'To',
            'Type',
            'UserActionHistory',
        ]
        mapped_data = {k: v for k, v in data.items() if k not in bad_keys}

        if scheduled := data.get('ScheduledDeliveryDateTime'):
            mapped_data['ScheduledDeliveryDateTime'] = localise_dt(scheduled, self.c['timezone'])

        dim_fields = ['LengthInFt', 'WidthInFt', 'HeightInFt']
        bad_item_keys = ['Vendor'] + dim_fields
        for item in data.get('Items', []):
            mapped_item = {k: v for k, v in item.items() if k not in bad_item_keys}
            if any(item.get(x) for x in dim_fields):
                mapped_item['Dimensions_LWH'] = 'x'.join([str(item.get(x, '')) for x in dim_fields]) + ' ft'

        mapped_data['History'] = [(item['Type'], localise_dt(item['Timestamp'], self.c['timezone']))
                                  for item in data.get('UserActionHistory', {}).get('UserActionsList', [])
                                  if item['Type'] != 'Updated']

        mapped_data['url'] = self.vor_url.request(data['RequestId'])
        mapped_data['url_note'] = 'When making a hyperlink, use the friendly identifier'

        return mapped_data

    async def query(self, _id: str, event_count_limit=5, verbose=True, **kwargs) -> dict:
        """Send query to endpoint and fetch data."""
        ######## vv Do a VOR Search lookup UNTIL AN ENDPOINT WHICH ACCEPTS THE TR\d{10} id format is ready vv ########
        if re.fullmatch(REGEX_MAPPING[self.c['org']]['transfer_request'], _id):
            if res := VorGlobalSearch(self.c).query(_id, result_type='TransferRequest', keep_all_and_no_lookups=True):
                _id = res[0]['id']
            else:
                return dict(status='no data available')
        ######## ^^ Do a VOR Search lookup UNTIL AN ENDPOINT WHICH ACCEPTS THE TR\d{10} id format is ready ^^ ########

        data = await self._send_request(session=self.session, verbose=verbose,
                                        params=dict(organization=self.c['org'], requestId=_id))
        return self._data_mapping(data) if data else dict(status='no data available')


class VorGlobalSearch(VorSearchBaseClass):
    """VOR global search API class."""
    def __init__(self, c: ConfigSchema):
        super().__init__(c, supported_orgs=['CHEVRON', 'Shell UK', 'ExxonMobilGuyana'])
        self.url_endpoint = config.vor_search.url.global_search
        self.lookup_classes = {
            'CHEVRON': dict(
                Container=ContainerEventsByID,
                Flight=FlightsByID,
                MovementRequest=MovementRequestByID,
                RoadTransportJob=RoadTransportJobsByID,
                Shipment=ShipmentsByID,
                Voyage=VoyagesByID,
                WorkOrder=WorkOrderByID
            ),
            'Shell UK': dict(
                Container=ContainerEventsByID,
                Flight=FlightsByID,
                Voyage=VoyagesByID
            ),
            'ExxonMobilGuyana': dict(
                Flight=FlightsByID,
                # Probably no need for a "Material" result class
                Shipment=ShipmentsByID,
                TransferRequest=TransferRequestsByID,
                Voyage=VoyagesByID,
                WorkOrder=WorkOrderByIDDancer
            )
        }[self.c['org']]

    async def get_data(self, data: list[dict], limit=config.ai_behaviour.default_limit, concurrent_requests_limit=20, verbose=True):
        """Overrides the base class method to handle multiple object types."""
        async def async_wrapper(x):
            return x

        async with ClientSession(connector=TCPConnector(limit=concurrent_requests_limit)) as session:
            apis = {object_type: _class(self.c, session) for object_type, _class in self.lookup_classes.items()}

            tasks = []
            for item in data[:limit]:
                if object_type := item.get('type'):
                    if api := apis.get(object_type):
                        tasks.append(api.query(_id=item['id'], verbose=verbose))
                    else:
                        tasks.append(async_wrapper(item))

            return await asyncio.gather(*tasks)

    @staticmethod
    def vor_global_search_reducer(result: dict):
        """Mapping the VOR global search results into a more compact form."""
        # add each item, keeping only a specific subset
        keys = [
            "type",
            "mostRelevantTimestamp",
            "subtitle",
            "title",
            "url",
        ]
        matched_highlights = result.get("matchedHighlights")
        search_matches = None

        # reducing the matched highlights into a single string of values
        if matched_highlights:
            matched_strings = matched_highlights[0].get("matches")
            search_matches = ", ".join(matched_strings)

        # extract the JSON metadata if possible (for further_processing or to have some info in non-lookup-able entities)
        try:
            metadata = json.loads(result["metadata"])
            if isinstance(metadata, list):
                metadata = dict(entries=metadata)  # only seen this for container events, but being general with "entries"
        except Exception as e:  # no need to be more specific
            metadata = dict(metadata=result["metadata"]) if result.get("metadata") else {}

        # grab only the subset of keys from above
        output = {
            "id": result["entityId"],
            **{k: v for k, v in result.items() if k in keys},
            "search_matches": search_matches
        }
        output.update(metadata)
        return output

    def query(self, query: str, result_type: str = None,
              keep_all_and_no_lookups: bool = False, further_processing: str = None) -> dict | list:
        """Look up items in the VOR global search.
        The keep_all_and_no_lookups is meant for when results need to be integrated with those from the global search
        before culling and lookup, thus returning the full lightly-processed list of results.
        """
        # Handle possible result type filters
        result_type = list(set(result_type.split('|'))) if result_type else []
        if bad_types := [t for t in result_type if t not in vor_search_result_filters[self.c['org']]]:
            result_type = [t for t in result_type if t not in bad_types]

        # Make the requests
        sub_results = []
        for sub_query in (sub_queries := query.split('¦')):
            params = dict(searchTerm=sub_query)
            if result_type:
                params['entityTypeFilter'] = result_type

            response = self._send_request(
                params=dict(organization=self.c['org']),
                json=params
            )
            sub_results.append(response['results'] if response else [])

        # Combine the results (intersection ordered by average rank)
        if any(not res for res in sub_results):
            combined_results = []  # info on whether any sub_query yielded results is preserved in the output
        elif len(sub_results) == 1:
            combined_results = sub_results[0]
        else:
            # Combine the ordering of common results from each sub_result
            #   Not using the 'score' field because it is not comparable between different searches
            common_ids = set.intersection(*[set(r['id'] for r in res) for res in sub_results])
            rank_sums = defaultdict(int)
            for res in sub_results:
                rank = 1
                for r in res:
                    if r['id'] in common_ids:
                        rank_sums[r['id']] += rank
                        rank += 1
            by_id = {r['id']: r for r in sub_results[0] if r['id'] in common_ids}
            combined_results = [by_id[_id] for _id in sorted(common_ids, key=lambda _id: rank_sums[_id])]

        # Process the results
        if combined_results:
            processed = [self.vor_global_search_reducer(r) for r in combined_results]
            for r in processed:
                if r['id'].startswith(pref := 'chevronvoyagemanifest-') or r['id'].startswith(pref := 'ignition-'):
                    r['id'] = r['id'][len(pref):]

            if keep_all_and_no_lookups:
                return processed
            else:
                # Look up only the top few results
                top_results = [] if further_processing else asyncio.run(self.get_data(processed[:config.ai_behaviour.default_limit]))

                # Return indexed fields for failed lookups
                for i in range(len(top_results)):  # by index rather than zip since modifying data
                    if top_results[i].get('status') == 'no data available':
                        top_results[i] = processed[i]

                # Package up the data
                params['searchTerm'] = query  # put back the individual sub_queries for the record
                if bad_types:
                    params['NOTE'] = f'The following entity types were requested as a filter but were ignored because not recognised: {bad_types}'
                    logging.warning(params['NOTE'])
                return self._package_data(top_results, all_results=processed,
                                          applied_filters=params, further_processing=further_processing)
        else:
            if keep_all_and_no_lookups:
                return []
            out = dict(status='no data available')
            if len(sub_queries) > 1:
                if had_results := [sub_query for sub_query, res in zip(sub_queries, sub_results) if res]:
                    out['note'] = (f'There were no results for the combined query "{query}", '
                                   f'but the following sub-queries did have some results: {had_results}. '
                                   f'If some of them are not location names (which always have results), tell the user.')
                else:
                    out['note'] = f'None of the sub-queries of "{query}" had results.'
            return out

    def simple_query(self, query: str) -> dict[str, dict[str, str]]:
        """Returns a single string for each result (with title, subtitle, most relevant timestamp, and url), and groups them entity type.
        This method is intended for the subscriptions pipeline, so it returns only entities for which we have a by-id
        lookup class, and it converts the entity type name to separate lowercase words.
        """
        subscribeable_entities = list(self.lookup_classes.keys())
        results = self.query(query, keep_all_and_no_lookups=True)
        grouped = defaultdict(dict)
        for r in results:
            if r['type'] not in subscribeable_entities:
                continue
            entity_type = ' '.join(words_from_misc_case(r['type']))  # e.g. RoadTransportJob -> road transport job
            grouped[entity_type][r['id']] = f'{r['title']} - {r['subtitle']}'
            if (r['mostRelevantTimestamp'] or {}).get('value'):
                grouped[entity_type][r['id']] += f' - {r['mostRelevantTimestamp']['description']}: {r['mostRelevantTimestamp']['value']}'
            grouped[entity_type][r['id']] += f' - {r['url']}'
        return grouped



class VorSearchPOEntities(VorGlobalSearch):
    """Wrapper of the VorGlobalSearch class, taking in only PO numbers and returning only shipments and MRs related to it."""

    def query(self, po: str) -> dict:
        """Note: this search does not perform any further lookups from primary sources, as its purpose is to get IDs and little more."""
        if not po.isnumeric() and (match := re.search(r'\d+', po)):
            po = match.group(0)

        raw_results = super().query(po, keep_all_and_no_lookups=True)
        shipments = [f"{r['id']} ({r['subtitle']})" for r in raw_results if r['type'] == 'Shipment']
        mrs = [r['id'] for r in raw_results if r['type'] == 'MovementRequest']

        if shipments or mrs:
            return dict(shipments=shipments, movement_requests=mrs)
        else:
            return dict(status='no data available')


class VoyageCargoManifestsByDescription(AISearchBaseClass):
    """Uses the voyage cargo manifests AI search service to find voyages based on manifest item descriptions."""

    def __init__(self, c: ConfigSchema):
        super().__init__(c, supported_orgs=['CHEVRON'])
        self.url_endpoint = config.ai_search.url.voyage_cargo_manifests

    async def get_data(self, data: list[dict], limit=config.ai_behaviour.default_limit):
        """Since the corresponding by-id class uses index data as well, this method is async for consistency but
        performs no additional lookups; it just performs the post-lookup processing.
        """
        api = VoyageCargoManifestsByID(self.c)
        return await asyncio.gather(*[api.query(item['id'], already_retrieved=item) for item in data[:limit]])

    def query(self, query: str = None, status: str = None,                          # Key filters
        project_code: str = None, container_id: str = None, vessel: str = None,     # Reference numbers
        origin: str = None, destination: str = None,                                # Locations
        hcr: bool = None,                                                           # Other features
        total_teu: str = None, utilisation_percentage: str = None,
        total_tonnage: str = None,
        departure_date: str = None, eta_date: str = None, ros_date: str = None,     # Dates
        further_processing: str = None) -> dict:
        """Search for an item in the index."""
        query = query if query else '*'

        search_results = self._send_request(params=(params := dict(
            organisation=self.c['org'],                                             # Key filters
            query=query, status=status,
            project_codes=project_code, container_ids=container_id, vessel=vessel,  # Reference numbers
            origin=origin, destination=destination,                                 # Locations
            hcr=hcr,                                                                # Other features
            total_teu=total_teu, utilisation_percentage=utilisation_percentage,
            total_tonnage=total_tonnage,
            departure_date=self.make_iso(departure_date),                           # Dates
            eta_date=self.make_iso(eta_date),
            ros_date=self.make_iso(ros_date),
        )))

        if fallback := self.by_id_fallback('voyage_cargo_manifest', VoyagesByID, search_results, params):
            return fallback

        search_results = sort_dicts(search_results, [('eta_date', True)])
        search_results = asyncio.run(self.get_data(search_results, limit=len(search_results)))  # do all since no extra lookup
        top_results = [] if further_processing else search_results[:config.ai_behaviour.default_limit]

        return self._package_data(top_results, limit=len(top_results), all_results=search_results,
                                  applied_filters=params, further_processing=further_processing)


class VoyageCargoManifestsByID(AISearchBaseClass):
    def __init__(self, c: ConfigSchema, session=None):  # session is not used; here for uniformity with other by-id endpoints
        super().__init__(c, supported_orgs=['CHEVRON'])
        self.url_endpoint = config.ai_search.url.voyage_cargo_manifests_by_id

    async def query(self, _id: str, verbose=True, already_retrieved: dict = None, **kwargs) -> dict:
        response = already_retrieved or self._send_request(params=dict(key=_id, organisation=self.c['org']), verbose=verbose)

        if not response:
            return dict(status='no data available')
        elif not isinstance(response, list):  # already a list only for id_number searches with multiple results
            response = [response]

        for data in response:
            data['url'] = self.vor_url.voyage(data['id'])

            # Add mr urls to the projects-mrs-containers hierarchy and remove redundant fields
            #   (they are required for filtering but distract the AI away from the hierarchy)
            if hierarchy_json := data['project_to_mr_to_ccu_hierarchy']:
                try:
                    hierarchy = json.loads(hierarchy_json)
                    data['mrs_and_containers_grouped_by_projects_urls'] = str({
                        proj: {mr: dict(url=self.vor_url.movement_request(mr), containers=containers)
                               for mr, containers in mrs.items()}
                        for proj, mrs in hierarchy.items()
                    })
                    for k in ['project_to_mr_to_ccu_hierarchy', 'project_codes', 'reference_numbers', 'container_ids']:
                        del data[k]
                except:  # if not possible, just generate some mr urls
                    mrs = [ref for ref in ' '.split(data['reference_numbers']) if ref[:3] in ['CMR', 'LMR']]
                    data['movement_requests'] = {mr: self.vor_url.movement_request(mr) for mr in mrs}

        return response[0] if len(response) == 1 else dict(multiple_matches=response)


class VoyagesByDescriptionVorSearch(VorSearchBaseClass):
    """Uses the voyages Vor Search service to find voyages by description and structured filters."""

    def __init__(self, c: ConfigSchema):
        super().__init__(c, supported_orgs=['ExxonMobilGuyana', 'Shell UK'])
        self.url_endpoint = config.vor_search.url.voyages_search

    def query(self, search_term: str = None, date_ranges: str = None, sort: str = None,
        status: str = None, hcr: bool = None, priority: bool = None,
        further_processing: str = None) -> dict:
        """Search voyages via the Vor Search API, enrich from Data Enhancer, and package results."""
        # Allow shortcut search by voyage number (looks up generated IDs); completely unrelated results otherwise
        if search_term and search_term.strip().isdigit():
            result = asyncio.run(VoyagesByID(self.c).query(search_term.strip()))
            if result.get('status') != 'no data available':
                return result

        return self._query_pipeline(search_term, date_ranges, sort,
            other_filters=dict(
                state=status,
                transportingHighCostRentalCargo=hcr,
                transportingPriorityCargo=priority,
            ),
            date_fields=['plannedDepartureDateTime', 'actualDepartureDateTime', 'lastIndexedAt'],
            by_id_fallback_patterns=['voyage_id', 'voyage'],
            by_id_endpoint_class=VoyagesByID,
            further_processing=further_processing
        )

    def non_index_data_pipeline(self, search_results: list, params: dict, limit: int = config.ai_behaviour.default_limit):
        """Retrieve voyage details from the Data Enhancer for each search hit."""
        return super().non_index_data_pipeline(search_results, params, VoyagesByID, 'voyageId', limit)


class VoyagesByID(DataEnhancerAPIBaseClass):
    def __init__(self, c: ConfigSchema, session=None):
        super().__init__(c, supported_orgs=['CHEVRON', 'Shell UK', 'ExxonMobilGuyana'])
        self.url_endpoint = config.data_enhancer.url.voyages_by_id
        self.session = session
        self.id_prefix = {
            'CHEVRON': 'chevronvoyagemanifest-',
            'Shell UK': 'wels-',
            'ExxonMobilGuyana': 'exxonmobilsupplychaindatahub-'
        }[self.c['org']]

    def _data_mapping(self, data, cargo_lines_limit=10, localised_datetimes=True) -> dict:
        """Method to reduce the Data Enhancer API data and extract useful fields."""
        good_keys = [  # I.e. fields which are of interest and already in the required format
            'voyageId',
            'voyageDisplayId',
            # 'statusDescription',  # does not show 'Completed' but stays at 'Active' (and eventually back to 'Inactive'?)
            'state',  # this is the one which will say 'Completed'
            'vesselName',  # 'vesselId' is best for cross-referencing, but no need here if using the Dancer index
            'outboundDeckUtilisation',
            'inboundDeckUtilisation',
            # 'vesselActivities',  # this info WILL be available soon
            # 'latestVesselBulks',  # this info is not applicable to ABU and SUK (fluid cargo in the hull)
        ]
        mapped_data = {k: v for k, v in data.items() if k in good_keys}

        mapped_data['departureDateTime'] = data.get('actualDepartureDateTime') or data.get('plannedDepartureDateTime')

        if _id := data.get('voyageId'):  # vv the outbound suffix will not be necessary in the future for Shell either
            mapped_data['url'] = self.vor_url.voyage(_id if self.c['org'] == 'CHEVRON' else _id + 'outbound')

        good_stages_keys = [
            'orderWithinVoyage',
            'activityType',
            'description',
            'percentageDeckSpaceAfter'
        ]
        if stages := data.get('stages'):
            mapped_data['stages'] = []
            for stage in stages:
                mapped_stage = {k: v for k, v in stage.items() if k in good_stages_keys}

                # Dates
                mapped_stage['startDateTime'] = stage.get('actualStartDateTime') or stage.get('plannedStartDateTime')
                mapped_stage['endDateTime'] = stage.get('actualEndDateTime') or stage.get('plannedEndDateTime')

                # Locations
                mapped_stage['origin'] = (_from := stage.get('fromLocation', {})).get('locationName')
                mapped_stage['originType'] = _from.get('locationType')
                mapped_stage['destination'] = (_to := stage.get('toLocation', {})).get('locationName')
                mapped_stage['destinationType'] = _to.get('locationType')

                mapped_data['stages'].append(mapped_stage)

        good_manifest_keys = [
            'manifestId',
            'classification',  # Provisional|Final. Note: each manifest list will only have one kind present
            'status',  # Upcoming|Started|Completed but can also switch to Provisional|Final
            'direction',  # Inbound|Outbound
            # 'bulkLines'  # ABU and SUK do not have these (fluids as cargo)
        ]
        all_mrs, all_projects = set(), set()
        for manifests in ['outboundManifests', 'inboundManifests']:
            mapped_data[manifests] = []
            for man in data.get(manifests, []):
                mapped_man = {k: v for k, v in man.items() if k in good_manifest_keys}
                mapped_man['cargoLines'] = []

                # append cargo lines up to a limit
                for line in man.get('cargoLines', [])[:cargo_lines_limit]:
                    mapped_line = dict(
                        container=line.get('containerId'),
                        project=(project := line.get('projectCode')),
                        status=line.get('status'),
                        weight=line.get('actualWeight') or line.get('expectedWeight'),
                        remainsOnBoard=line.get('isRob')
                    )
                    if project:
                        all_projects.add(project)

                    # Only add destination data if present
                    d_strs = [(dest := line.get('destination', {})).get('locationType') or '', dest.get('locationName') or '']
                    if d_str := [d_str for d_str in d_strs if d_str]:
                        mapped_line['destination'] = ' - '.join(d_str)

                    # Reference numbers
                    mrs, other_refs = [], []
                    for pair in line.get('references', []):
                        if val := pair.get('value'):  # the 'key' is non-informative
                            (mrs if val.upper()[:3] in ['LMR', 'CMR'] else other_refs).append(val)
                    if mrs:  # do not add the field if empty (only there for Chevron anyway)
                        mapped_line['movementRequests'] = ' '.join(mrs)
                        all_mrs.update(mrs)
                    mapped_line['referenceNumbers'] = ' --- '.join(other_refs)  # because single - is used in Shell UK

                    # Contents
                    descriptions, dangerous = [], False
                    for content in line.get('materialLines', []):
                        dangerous |= line.get('isDangerousGoods', False)
                        if (descr := content.get('description', '')).lower() not in ['', 'skip']:
                            descriptions.append(descr)
                    mapped_line.update(dict(
                        contentDescriptions='\n'.join(descriptions),
                        isDangerousGoods=dangerous
                    ))

                    mapped_man['cargoLines'].append(mapped_line)
                    mapped_man['cargoLines_truncated'] = len(man.get('cargoLines', [])) > cargo_lines_limit
                mapped_data[manifests].append(mapped_man)


        # Collected reference numbers
        if all_projects:
            mapped_data['projects'] = list(all_projects)
        if all_mrs:
            mapped_data['movementRequestUrls'] = {mr: self.vor_url.movement_request(mr) for mr in all_mrs}

        if localised_datetimes:
            for k in ['departureDateTime']:
                if k in mapped_data:
                    mapped_data[k] = localise_dt(mapped_data[k], self.c['timezone'])
            if 'stages' in mapped_data:
                for stage in mapped_data['stages']:
                    for k in ['startDateTime', 'endDateTime']:
                        if k in stage:
                            stage[k] = localise_dt(stage[k], self.c['timezone'])

        return mapped_data

    async def query(self, _id: str, verbose=True, localised_datetimes=True, **kwargs) -> dict:
        """Send query to endpoint and fetch data."""
        _id = re.sub(r'inbound|outbound|/|\s', '', _id.lower())
        if not (digits := re.search(r'\d+', _id)):
            return dict(status='no data available')

        ids = [_id]
        if self.c['org'] == 'Shell UK':
            # Look up probable ids if _id is partial (e.g. for "look up voyage 82" it should find abz08225)
            year_suffixes = [str(year := date.today().year)[-2:], str(year - 1)[-2:]]  # try this year and last year
            if _id == digits.group():
                if len(_id) <= 2:
                    _id = _id.zfill(3)  # pad to 3 digits in any case

                if len(_id) <= 4:
                    ids = [f'{pre}{_id}{yy}' for pre in ['abz', 'lwk'] for yy in year_suffixes]
                else:
                    ids = [f'{pre}{_id}' for pre in ['abz', 'lwk']]
            elif len(digits.group()) <= 4:
                ids = [f'{_id}{yy}' for yy in year_suffixes]

        for _id in ids:
            data = await self._send_request(
                session=self.session,
                verbose=verbose,
                path_variables=dict(id=('' if _id.startswith(self.id_prefix) else self.id_prefix) + _id),
                params=dict(organization=self.c['org'])
            )
            if data:  # return on first successful retrieval
                return self._data_mapping(data, localised_datetimes=localised_datetimes)
        return dict(status='no data available')


class WorkOrderByID(CustomerAPIBaseClass):
    def __init__(self, c: ConfigSchema, session=None):
        super().__init__(c, supported_orgs=['CHEVRON'])
        self.url_endpoint = config.customer_api.url.work_orders
        self.session = session

    def _data_mapping(self, data, localised_datetimes=True) -> dict:
        """Method to reduce the customer API data and extract useful fields."""
        status_labels = {
            'Label Issued': '05 10 15',
            'Packed': '20 25 30 40',
            'Shipped': '50',
            'Delivered': '60 65 70 75',
            'Closed': '98 99',
            'Cancelled': '95'
        }  # vv flip ^^ so that it is from each int str to its label
        status_labels = {v: k for k, vs in status_labels.items() for v in vs.split()}

        # Extract top-level fields
        mapped_data = dict(
            work_order_id=data.get('WorkOrderNumber'),
            work_order_url=self.vor_url.work_order(data.get('id'))
        )

        # Extract line fields (flattening and mapping)
        flattened_lines = []
        for line in data.get('WorkOrderLines') or []:
            field_mapping = dict(
                status='PackStatus',
                description='ItemDescription',
                pack='PackNumber',
                tare='TareNumber',
                # These dates are useful when movement request status messages are empty (e.g. after delivery)
                pack_date='PackCreateDate',
                scheduled_pickup_date='SchedulePickDate',
                promised_delivery_date='PromiseDeliveryDate',
                work_order_start_date='WorkOrderStartDate',
                last_update_date='LastReadFromSourceSystem',
                # Useful? 'OrderNumber', 'ItemNumber', 'RelatedPoSoNumber', 'RelatedOrderReceiptDate', 'BranchPlant'
            )
            flat_line = {k: line.get(v) for k, v in field_mapping.items()}
            flat_line['status'] = status_labels.get(flat_line['status'], flat_line['status'])  # i.e. keep if unknown

            if summary := line.get('MovementRequestSummary'):
                field_mapping = dict(
                    movement_request='MovementRequestNumber',
                    location='LastSeenLocation',
                    destination='FinalDestination',
                    mr_status='StatusDisplayName',
                    mr_status_message='MovementRequestEtaJustification'
                )
                flat_line.update({k: summary.get(v) for k, v in field_mapping.items()})
                flat_line['mr_status_message'] = ' '.join(flat_line['mr_status_message'] or [])
                flat_line['mr_mode'], flat_line['mr_stage'] = MovementRequestByID.status_to_mode_and_stage[flat_line['mr_status']]

                if latest_event := line.get('LatestEvent'):
                    field_mapping = dict(
                        project_code='ProjectCode',
                        container='CcuDisplayId',
                        timestamp='DateTime'
                    )
                    flat_line.update({k: latest_event.get(v) for k, v in field_mapping.items()})

                # Upgrade the status if the MR status is terminal or in progress and the JDE one is behind
                if flat_line['status'] not in ['Delivered', 'Closed', 'Cancelled']:
                    if flat_line['mr_stage'] == 'Delivered':
                        flat_line['status'] = 'Delivered'
                    elif flat_line['mr_stage'] == 'In Progress' and flat_line['mr_status'] != 'In Progress - Staged At Supply Base':
                        flat_line['status'] = 'Shipped'
                    # No upgrading for any other combination of status and mr_stage

            flattened_lines.append(flat_line)

        # Group lines by MR and aggregate their fields
        lines_by_mr_or_tare = defaultdict(list)
        if flattened_lines:
            # Extract shared dates
            for field in ['work_order_start_date', 'last_update_date']:
                mapped_data[field] = list(set(x[field] for x in flattened_lines).difference([None]))
                mapped_data[field] = mapped_data[field][0] if len(mapped_data[field]) == 1 else mapped_data[field]

            # Group by movement request or tare
            for line in flattened_lines:
                lines_by_mr_or_tare[line.get('movement_request') or line.get('tare')].append(line)  # No-MR-no-tare cases are safely under None

            # Aggregate fields within MRs or tares
            for mrt in lines_by_mr_or_tare:  # not .items() because modifying content
                field_vals = defaultdict(set)
                statuses = Counter()
                for line in lines_by_mr_or_tare[mrt]:
                    statuses.update([line['status']])
                    for field in line:
                        field_vals[field].add(line[field])
                field_vals['status'] = statuses

                # Drop fields, remove Nones, convert to lists, and extract singletons
                drop = ['status', 'work_order_start_date', 'last_update_date', 'movement_request']
                line_data = {k: list(v.difference([None])) for k, v in field_vals.items() if k not in drop}
                line_data = {k: v[0] if len(v) == 1 else v for k, v in line_data.items()}
                line_data['status_counts'] = dict(field_vals['status'])

                if mrt and re.match(r'[CL]MR', mrt):
                    line_data['movement_request_url'] = self.vor_url.movement_request(mrt)
                else:
                    line_data.pop('tare', None)  # safely remove the tare (as it is mrt or missing)

                line_data['description'] = '. '.join(line_data.get('description') or [])
                lines_by_mr_or_tare[mrt] = line_data

            # Clarify possible lack of movement requests for some lines to the LLM (instead of None)
            mapped_data['items_with_movement_request'] = {k: v for k, v in lines_by_mr_or_tare.items() if 'movement_request_url' in v}
            mapped_data['items_with_no_movement_request_by_tare'] = {
                (k if k else 'All items with no MR nor tare'): v for k, v in lines_by_mr_or_tare.items() if 'movement_request_url' not in v}

            # Tally up statuses across all lines
            total_status_counts = Counter()
            for fields in lines_by_mr_or_tare.values():
                total_status_counts.update(Counter(fields['status_counts']))
            mapped_data['total_status_counts'] = dict(total_status_counts)

        # Note: this endpoint does NOT respect the UseLocalTime header, however, all its datetime fields (except one)
        #   are dates with added midnights and UTC tz, so the localisation code performs the correct operations.
        if localised_datetimes:
            for item_list in ['items_with_movement_request', 'items_with_no_movement_request_by_tare']:
                if item_list in mapped_data:
                    for item in mapped_data[item_list].values():
                        for k in ['pack_date', 'scheduled_pickup_date', 'promised_delivery_date', 'work_order_start_date', 'last_update_date']:
                            if k in item:
                                item[k] = localise_dt(item[k], self.c['timezone'])

        return mapped_data

    async def query(self, _id: str, verbose=True, localised_datetimes=True, **kwargs) -> dict:
        """Send query to endpoint and fetch data."""
        if not _id.isnumeric() and (match := re.search(r'\d+', _id)):
            _id = match.group(0)

        data = await self._send_request(session=self.session, verbose=verbose, params=dict(id=_id, role=self.c['org']))

        if data:
            data["id"] = _id
            return self._data_mapping(data, localised_datetimes=localised_datetimes)
        else:
            return {"status": "no data available"}


class WorkOrderByIDDancer(DataEnhancerAPIBaseClass):
    def __init__(self, c: ConfigSchema, session=None):
        super().__init__(c, supported_orgs=['ExxonMobilGuyana'])
        self.url_endpoint = config.data_enhancer.url.work_orders_by_id
        self.session = session

    def _data_mapping(self, data, localised_datetimes=True) -> dict:
        """Method to reduce the Data Enhancer API data and extract useful fields."""
        bad_keys = [  # I.e. fields which are redundant, need special handling, or are not of interest
            'entityId',
            'sourceFileName',
            'sourceFileLineNumber',
            # Special handling
            'additionalData',
            'materials'
        ]
        keep_even_if_none = [  # since dropping null and "None" fields below
            'status',
            'title',
            'workOrderType'
        ]
        mapped_data = {k: v for k, v in data.items() if k not in bad_keys
                       if (v and v != 'None') or k in keep_even_if_none}

        # Convert key/value pairs to a standard dictionary
        mapped_data['additionalData'] = {pair['key']: pair['value'] for pair in data['additionalData']}

        ############ WILL WANT SPECIAL HANDLING IF/WHEN THIS DATA IS AVAILABLE
        mapped_data['materials'] = data['materials']

        mapped_data['url'] = self.vor_url.enhanced_work_order(data['entityId'])

        if localised_datetimes:
            for k in ['actualStartDateTime', 'actualCompletionDateTime', 'createdAtDateTime', 'lastUpdatedAtDateTime']:
                if k in mapped_data:
                    mapped_data[k] = localise_dt(mapped_data[k], self.c['timezone'])

        return mapped_data

    async def query(self, _id: str, verbose=True, localised_datetimes=True, **kwargs) -> dict:
        """Send query to endpoint and fetch data."""
        # Get only numbers and add the required prefix
        if not _id.isnumeric() and (match := re.search(r'\d+', _id)):
            _id = match.group(0)
        _id = 'ifs-' + _id

        data = await self._send_request(session=self.session, verbose=verbose,
                                        params=dict(organization=self.c['org']),
                                        path_variables=dict(id=_id))
        return self._data_mapping(data, localised_datetimes=localised_datetimes) if data else dict(status='no data available')


