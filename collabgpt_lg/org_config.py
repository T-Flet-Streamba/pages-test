from urllib.parse import urljoin

import config


vor_search_result_filters = {
    'CHEVRON': '"Flight", "MovementRequest", "RoadTransportJob", "Shipment", "Voyage", "WorkOrder"',
    'ExxonMobilGuyana': '"Flight", "Material", "Shipment", "TransferRequest", "Voyage", "WorkOrder"',
    'Shell UK': '"AirFreightRequest", "Container", "Flight", "Voyage"'
    # Entities across all orgs (from VOR Search itself):
    #   RoadTransportJob, Flight, Voyage, Container, Shipment, MovementRequest, WorkOrder, TransferRequest, AirFreightRequest, Material
}


def vor_url_list(org: str):
    """Links to various VOR pages, for use in LLM prompts; limited to the basic common pages, other pages commented out."""
    suffixes = {
        'CHEVRON': dict(
            ccuHires="ccuHires",
            roadTransport="roadTransport",
            airTransport="airTransport",
            activeVoyages="activeVoyages",
            vesselSchedule="vesselSchedule",
            internationalShipments="shipments",
            downstreamShipments="downstreamShipments",
            logisticsSummary="logistics-summary",
            # priorityReportItems="priorityReport",
            # workOrders="workOrders",
            # musterReport="muster-report",
            # nonInventoryStaging="nonInventoryStaging",
            # equipmentMasterRegister="equipmentMasterRegister",
            # gateMovements="gateMovements",
            # downstreamOrders="downstreamOrders",
        ),
        'Shell UK': dict(
            ccuHires="ccuHires",
            activeVoyages="activeVoyages",
            realtimePlan="realtimePlan",
        ),
        'ExxonMobilGuyana': dict(
            # activeVoyages="activeVoyages",
            airTransport="airTransport",
            airportLog="groundTransport",
            ccuHires="ccuHires",
            crudeLifting="crudeLifting",
            equipmentRentals="rentalItems",
            materials="materials",
            oilfieldChemicals="oilfieldChemicals",
            operationalImpact="operationalImpact",
            requests="requests",
            rigView="rigView",
            shipments="shipments",
            supplyChainHealth="supplyChainHealth",
            vesselAvailability="vesselAvailability",
            workOrders="enhancedWorkOrders",
        )
    }
    return {n: urljoin(config.customer_api.url.base, 'supplychain#/' + suffix) for n, suffix in suffixes[org].items()}


