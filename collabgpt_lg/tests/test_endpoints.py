import pytest
import asyncio

from collabgpt_lg.endpoints import (
    FlightRequestApproval,
    ContainerEventsByID,
    ContainerEventsByIDDancer,
    CCUHires,
    FlightRequests,
    FlightsByDescription,
    FlightsByDescriptionVorSearch,
    FlightsByID,
    GlobalDescriptionSearch,
    LogisticsSummaryReports,
    MovementRequestsByDescription,
    MovementRequestByID,
    PrioritiesByDescription,
    RoadTransportJobsByDescription,
    RoadTransportJobsByID,
    RoadTransportJobsVorSearch,
    ShipmentsByDescription,
    ShipmentsByID,
    ShipmentsVorSearch,
    TransferRequestsByID,
    VorGlobalSearch,
    VoyageCargoManifestsByDescription,
    VoyageCargoManifestsByID,
    VoyagesByDescriptionVorSearch,
    VoyagesByID,
    WorkOrderByID,
    WorkOrderByIDDancer
)
from collabgpt_lg.utils import org_state


class TestEndpoint:
    def test_container_events_by_id(self):
        """Test container events by ID API integration"""
        api = ContainerEventsByID(org_state('CHEVRON'))
        data = asyncio.run(api.query(_id='10262'))
        assert data.get('status') != 'no data available'

        # where id doesn't exist (other org)
        data = asyncio.run(api.query(_id='SAT602'))
        assert data.get('status') == 'no data available'

        api = ContainerEventsByID(org_state('Shell UK'))
        data = asyncio.run(api.query(_id='SAT602'))
        assert data.get('status') != 'no data available'

        # where id doesn't exist (other org)
        data = asyncio.run(api.query(_id='10262'))
        assert data.get('status') == 'no data available'

    def test_container_events_by_id_dancer(self):
        """Test container events by ID Dancer API integration"""
        api = ContainerEventsByIDDancer(org_state('ExxonMobilGuyana'))
        data = asyncio.run(api.query(_id='104101'))
        assert data.get('status') != 'no data available'

        # where id doesn't exist (other org)
        data = asyncio.run(api.query(_id='SAT602'))
        assert data.get('status') == 'no data available'

    def test_ccu_hires(self):
        """Test CCU Hires Dancer API integration"""
        api = CCUHires(org_state('ExxonMobilGuyana'))
        data = asyncio.run(api.query(id_or_other_ref='104101'))
        assert data.get('status') != 'no data available'

        # Only containers with $$ cost (neither $ nor $$$)
        data = asyncio.run(api.query(id_or_other_ref='$$'))
        assert data.get('status') != 'no data available'

        # where id doesn't exist (other org)
        data = asyncio.run(api.query(id_or_other_ref='SAT602'))
        assert data.get('status') == 'no data available'

    def test_flights_by_description(self):
        """Test flights by description API integration"""
        api = FlightsByDescription(org_state('CHEVRON'))
        data = api.query(query='*', estimated_departure_date='2026-01-01~2026-03-01')
        assert data.get('TopResults')

        # by flight number
        data = api.query(query='*', flight_number='NC3872')
        assert data.get('TopResults')

        data = api.query(query='Stickers')
        assert data.get('TopResults')

        # where further processing is required
        data = api.query(query='Stickers', further_processing='Something')
        assert data.get('AllResultsDataset') and not data.get('TopResultsDataset')  # datasets, not TopResults printout

        # where no results are found
        data = api.query(query='abc123')
        assert not data.get('TopResults')

        # Org not allowed
        with pytest.raises(ValueError):
            FlightsByDescription(org_state('Shell UK'))

    def test_flights_by_description_vor_search(self):
        """Test flights by description Vor Search API integration"""
        api = FlightsByDescriptionVorSearch(org_state('ExxonMobilGuyana'))
        data = api.query(search_term='OGLE')
        assert data.get('TopResults')

        data = api.query(date_ranges='[{"field":"estimatedDepartureDateTime","from":"2026-05-01","to":"2026-05-10"}]',
                         sort='[{"field":"estimatedDepartureDateTime"}]')
        assert data.get('TopResults')

        data = api.query(search_term='unlikely-token-xyz-no-results-abc')
        assert not data.get('TopResults')

        api = FlightsByDescriptionVorSearch(org_state('Shell UK'))
        data = api.query(search_term='SHC1-01')
        assert data.get('TopResults')

    def test_flight_requests(self):
        """Test flight requests list API integration"""
        api = FlightRequests(org_state('Shell UK'))
        data = asyncio.run(api.query())
        data = asyncio.run(api.query(status='PENDING|REJECTED'))
        # Nothing to assert, as there may be no requests; create some manually and uncomment to test
        # assert data.get('status') != 'no data available'

        # Org not allowed
        with pytest.raises(ValueError):
            FlightRequests(org_state('CHEVRON'))

    # @pytest.mark.skip(reason='Mutating endpoint; comment this out for integration testing and manually create other test requests if these do not work anymore.')
    def test_flight_request_approval(self):
        """Test flight request approval/rejection API integration"""
        api = FlightRequestApproval(org_state('Shell UK'))
        data = asyncio.run(api.query(
            approve=True,
            request_id='c0530208-1bde-4e30-ab9f-18cc07209253',  # replace with a new test request if necessary
            comments='Automated test approval',
            user_responsible='automated-tester@vor.cloud'
        ))
        assert data.get('State') == 'APPROVED'

        data = asyncio.run(api.query(
            approve=False,
            request_id='390472b7-6266-491e-b789-fd62d6e13bca',  # replace with a new test request if necessary
            comments='Automated test rejection',
            user_responsible='automated-tester@vor.cloud'
        ))
        assert data.get('State') == 'REJECTED'

        # Org not allowed
        with pytest.raises(ValueError):
            FlightRequestApproval(org_state('CHEVRON'))

    def test_flights_by_id(self):
        """Test flights by ID API integration"""
        api = FlightsByID(org_state('CHEVRON'))
        data = asyncio.run(api.query(_id='DaWinci-5675-1-2025-04-28'))
        assert data.get('status') != 'no data available'

        # where id doesn't exist
        data = asyncio.run(api.query(_id='random'))
        assert data.get('status') == 'no data available'

        api = FlightsByID(org_state('Shell UK'))
        data = asyncio.run(api.query(_id='Vantage-20250421_vantage_2372425-2025-04-21'))
        assert data.get('status') != 'no data available'

        # where id doesn't exist
        data = asyncio.run(api.query(_id='random'))
        assert data.get('status') == 'no data available'

    def test_global_description_search(self):
        """Test movement requests by description API integration"""
        api = GlobalDescriptionSearch(org_state('CHEVRON'))
        data = api.query(query='pump')
        assert data.get('TopResults')

        # where further processing is required
        data = api.query(query='documents', further_processing='Something')
        assert data.get('AllResultsDataset') and not data.get('TopResultsDataset')  # datasets, not TopResults printout

        # where no results are found
        data = api.query(query='abc123')
        assert not data.get('TopResults')

        # Org not allowed
        with pytest.raises(ValueError):
            GlobalDescriptionSearch(org_state('Shell UK'))

    def test_ls_reports(self):
        """Test retrieval and processing of LS warnings"""
        api = LogisticsSummaryReports(org_state('CHEVRON'))
        data = asyncio.run(api.query())
        assert data, 'No warnings at the moment; try later or mock them.'

        # Try and filter by anything for known types which are present; results unknown, so just checking there are no errors
        for t, conf in api._LS_REPORT_CONFIG.items():
            if t in data and (threshold_field := conf.get('threshold_field')):  # some do not have a threshold value
                for cond in [('>=', 2), ('<', 2)]:
                    filtered = asyncio.run(api.query(_id=t, filters=dict(threshold=cond), report_type_is_simplified=False))
                    print(f'\n{len(filtered[t])} {t} entries have {threshold_field} {cond[0]} {cond[1]}')

        # Org not allowed
        with pytest.raises(ValueError):
            LogisticsSummaryReports(org_state('Shell UK'))

    def test_mrs_by_description(self):
        """Test movement requests by description API integration"""
        api = MovementRequestsByDescription(org_state('CHEVRON'))
        data = api.query(query='oil')
        assert data.get('TopResults')

        # with filters
        data = api.query(query='*', status='Delivered|Unknown', hazmat=True, project_code='GOROPS')
        assert data.get('TopResults')

        # by location
        data = api.query(query='*', destination='BWI|Barrow', ros_date='2026-01-01~2026-03-01')
        assert data.get('TopResults')

        # where further processing is required
        data = api.query(query='oil', further_processing='Something')
        assert data.get('AllResultsDataset') and not data.get('TopResultsDataset')  # datasets, not TopResults printout

        # where no results are found
        data = api.query(query='abc123')
        assert not data.get('TopResults')

        # Org not allowed
        with pytest.raises(ValueError):
            MovementRequestsByDescription(org_state('Shell UK'))

    @pytest.mark.parametrize('mr_pack_or_tare', [
        # LMR         CMR          Pack                  Tare                  Kabal ID          PO Number
        'LMR110655', 'CMR124423', '000119570007349114', '100119570007355006', 'CHEVRONAU26005', '61222785'
    ])
    def test_mr_by_id(self, mr_pack_or_tare):
        """Test movement requests by ID API integration"""
        api = MovementRequestByID(org_state('CHEVRON'))
        data = asyncio.run(api.query(_id=mr_pack_or_tare))  # leaving unnest_singletons False for testing
        assert not data.get('status', '').startswith('no data available')

        # Org not allowed
        with pytest.raises(ValueError):
            MovementRequestByID(org_state('Shell UK'))

    def test_priorities_by_description(self):
        """Test priorities by description API integration"""
        api = PrioritiesByDescription(org_state('CHEVRON'))
        data = api.query(query='*', ros_date='2026-02-01~2026-03-01')
        assert data.get('TopResults')

        data = api.query(query='ST723869')
        assert data.get('TopResults')

        # where further processing is required
        data = api.query(query='*', ros_date='2026-01-01~2026-03-01', further_processing='Something')
        assert data.get('AllResultsDataset') and not data.get('TopResultsDataset')  # datasets, not TopResults printout

        # where no results are found
        data = api.query(query='abc123')
        assert not data.get('TopResults')

        # Org not allowed
        with pytest.raises(ValueError):
            PrioritiesByDescription(org_state('Shell UK'))

    def test_road_transport_jobs_by_description(self):
        """Test road transports jobs by description API integration"""
        api = RoadTransportJobsByDescription(org_state('CHEVRON'))
        data = api.query(query='*', requested_delivery_date='2026-01-01~2026-03-01')
        assert data.get('TopResults')

        data = api.query(query='ITEMS')
        assert data.get('TopResults')

        # where further processing is required
        data = api.query(query='ITEMS', further_processing='Something')
        assert data.get('AllResultsDataset') and not data.get('TopResultsDataset')  # datasets, not TopResults printout

        # where no results are found
        data = api.query(query='abc123')
        assert not data.get('TopResults')

        # Org not allowed
        with pytest.raises(ValueError):
            RoadTransportJobsByDescription(org_state('Shell UK'))

    def test_road_transport_jobs_by_id(self):
        """Test road transports jobs by ID API integration"""
        api = RoadTransportJobsByID(org_state('CHEVRON'))
        data = asyncio.run(api.query(_id='SR09835'))
        assert data.get('status') != 'no data available'

        # where id doesn't exist
        data = asyncio.run(api.query(_id='abc123'))
        assert data.get('status') == 'no data available'

        # Org not allowed
        with pytest.raises(ValueError):
            RoadTransportJobsByID(org_state('Shell UK'))

    def test_road_transport_jobs_vor_search(self):
        """Test road transport jobs Vor Search API integration."""
        api = RoadTransportJobsVorSearch(org_state('CHEVRON'))
        data = api.query(search_term='GOROPS')
        assert data.get('TopResults')

        data = api.query(date_ranges='[{"field":"requestedPickupDateTime","from":"2026-05-01","to":"2026-05-10"}]',
                         sort='[{"field":"requestedPickupDateTime"}]')
        assert data.get('TopResults')

        data = api.query(search_term='unlikely-token-xyz-no-results-abc')
        assert not data.get('TopResults')

        with pytest.raises(ValueError):
            RoadTransportJobsVorSearch(org_state('ExxonMobilGuyana'))

    def test_shipments_vor_search(self):
        """Test shipments Vor Search API integration."""
        api = ShipmentsVorSearch(org_state('ExxonMobilGuyana'))
        data = api.query(search_term='GYSBI')
        assert data.get('TopResults')

        data = api.query(sort='[{"field":"modeOfTransport"}]')
        assert data.get('TopResults')

        data = api.query(search_term='unlikely-token-xyz-no-results-abc')
        assert not data.get('TopResults')

        with pytest.raises(ValueError):
            ShipmentsVorSearch(org_state('Shell UK'))

    def test_shipments_by_description_or_project(self):
        """Test shipments by description or project API integration"""
        api = ShipmentsByDescription(org_state('CHEVRON'))
        data = api.query(query='delo silver')
        assert data.get('TopResults')

        data = api.query(query='*', project_code='GOROPS')
        assert data.get('TopResults')

        # where further processing is required
        data = api.query(query='delo silver', further_processing='Something')
        assert data.get('AllResultsDataset') and not data.get('TopResultsDataset')  # datasets, not TopResults printout

        # where no results are found
        data = api.query(query='abc123')
        assert not data.get('TopResults')

        # Org not allowed
        with pytest.raises(ValueError):
            ShipmentsByDescription(org_state('Shell UK'))

    def test_shipments_by_id(self):
        """Test shipments by ID API integration"""
        api = ShipmentsByID(org_state('CHEVRON'))

        # A DSV shipment, for which the AI is warned that all datetimes have no tz and are local to their event
        data = asyncio.run(api.query(_id='SSIN0424029'))
        assert data.get('status') != 'no data available'

        # A DB Schenker shipment, where all the datetimes have explicit timezones
        data = asyncio.run(api.query(_id='38090013916538'))
        assert data.get('status') != 'no data available'

        # where id doesn't exist
        data = asyncio.run(api.query(_id='abc123'))
        assert data.get('status') == 'no data available'

        # ExxonMobilGuyana
        api = ShipmentsByID(org_state('ExxonMobilGuyana'))

        # This is also a DSV shipment
        data = asyncio.run(api.query(_id='SEDC1387185'))
        assert data.get('status') != 'no data available'

        # Org not allowed
        with pytest.raises(ValueError):
            ShipmentsByID(org_state('Shell UK'))

    def test_transfer_requests_by_id(self):
        """Test transfer requests by ID API integration"""
        api = TransferRequestsByID(org_state('ExxonMobilGuyana'))
        data = asyncio.run(api.query(_id='3b2e5b5b-8974-49af-a129-5be4ae885ae4'))
        assert data.get('status') != 'no data available'

        # With friendly ID
        data = asyncio.run(api.query(_id='TR2602252209'))
        assert data.get('status') != 'no data available'

        # where id doesn't exist
        data = asyncio.run(api.query(_id='abc123'))
        assert data.get('status') == 'no data available'

        # Org not allowed
        with pytest.raises(ValueError):
            TransferRequestsByID(org_state('Shell UK'))

    def test_vor_search(self):
        """Test VOR Search API integration"""
        api = VorGlobalSearch(org_state('ExxonMobilGuyana'))
        data = api.query(query='oil')
        assert data.get('TopResults')

        # compound query with type filter
        data = api.query(query='Prosperity¦battery', result_type='Flight')
        assert data.get('TopResults')

        # where no results are found
        data = api.query(query='abc123')
        assert not data.get('TopResults')

        api = VorGlobalSearch(org_state('Shell UK'))
        data = api.query(query='Valaris¦oil', result_type='Voyage')
        assert data.get('TopResults')

        api = VorGlobalSearch(org_state('CHEVRON'))
        data = api.query(query='pump')
        assert data.get('TopResults')

        # where further processing is required
        data = api.query(query='Barrow Island', further_processing='Something')
        assert data.get('AllResultsDataset') and not data.get('TopResultsDataset')  # datasets, not TopResults printout

    def test_voyages_by_description_vor_search(self):
        """Test voyages by description Vor Search API integration."""
        api = VoyagesByDescriptionVorSearch(org_state('ExxonMobilGuyana'))
        data = api.query(search_term='oil')
        assert data.get('TopResults')

        data = api.query(date_ranges='[{"field":"plannedDepartureDateTime","from":"2026-04-20"}]',
                         sort='[{"field":"plannedDepartureDateTime"}]')
        assert data.get('TopResults')

        data = api.query(search_term='unlikely-token-xyz-no-results-abc')
        assert not data.get('TopResults')

        api = VoyagesByDescriptionVorSearch(org_state('Shell UK'))
        data = api.query(search_term='oil')
        assert data.get('TopResults')

        with pytest.raises(ValueError):
            VoyagesByDescriptionVorSearch(org_state('CHEVRON'))

    def test_voyage_cargo_manifests_by_description(self):
        """Test voyage cargo manifests by description API integration"""
        api = VoyageCargoManifestsByDescription(org_state('CHEVRON'))
        data = api.query(query='freezer')
        assert data.get('TopResults')

        # filtering
        data = api.query(
            query='*',
            status='Provisional',  # None by default if not provided
            project_code='GOROPS'  # None by default if not provided
        )
        assert data.get('TopResults')

        # where further processing is required
        data = api.query(query='freezer', further_processing='Something')
        assert data.get('AllResultsDataset') and not data.get('TopResultsDataset')  # datasets, not TopResults printout

        # no results
        data = api.query(query='*', project_code='MAYHEM')
        assert not data.get('TopResults')

        # Org not allowed
        with pytest.raises(ValueError):
            VoyageCargoManifestsByDescription(org_state('Shell UK'))

    def test_voyage_cargo_manifest_by_id(self):
        """Test voyage cargo manifests by ID API integration"""
        api = VoyageCargoManifestsByID(org_state('CHEVRON'))
        data = asyncio.run(api.query(_id='aurigainvestigator9999'))
        assert data.get('status') != 'no data available'

        data = asyncio.run(api.query(_id='9999'))
        assert data.get('status') != 'no data available'

        # no results
        data = asyncio.run(api.query(_id='random'))
        assert data.get('status') == 'no data available'

        # Org not allowed
        with pytest.raises(ValueError):
            VoyageCargoManifestsByID(org_state('Shell UK'))

    def test_voyage_by_id(self):
        """Test voyage by ID API integration (Data Enhancer)"""
        api = VoyagesByID(org_state('CHEVRON'))
        data = asyncio.run(api.query(_id='aurigaastrolabe9813'))
        assert data.get('status') != 'no data available'

        # no results
        data = asyncio.run(api.query(_id='random'))
        assert data.get('status') == 'no data available'

        api = VoyagesByID(org_state('Shell UK'))
        data = asyncio.run(api.query(_id='abz08225outbound'))
        assert data.get('status') != 'no data available'

        # (very) partial id for Shell UK voyages
        data = asyncio.run(api.query(_id='82'))
        assert data.get('status') != 'no data available'

    def test_wo_by_id(self):
        """Test work orders by ID API integration"""
        api = WorkOrderByID(org_state('CHEVRON'))
        data = asyncio.run(api.query(_id='850188'))
        assert len(data.get('items_with_movement_request')) > 0 and len(data.get('items_with_no_movement_request_by_tare')) > 0

        # Technically the AI is told to not pass in the prefix, but we tolerate it
        data = asyncio.run(api.query(_id='WO751845'))
        assert data.get('status') != 'no data available'

        # Org not allowed
        with pytest.raises(ValueError):
            WorkOrderByID(org_state('Shell UK'))

    def test_wo_by_id_dancer(self):
        """Test work orders by ID Dancer API integration"""
        api = WorkOrderByIDDancer(org_state('ExxonMobilGuyana'))
        data = asyncio.run(api.query(_id='120013750'))
        assert data.get('status') != 'no data available'

        # Technically the AI is told to not pass in the prefix, but we tolerate it
        data = asyncio.run(api.query(_id='WO120013750'))
        assert data.get('status') != 'no data available'

        # Org not allowed
        with pytest.raises(ValueError):
            WorkOrderByIDDancer(org_state('CHEVRON'))


