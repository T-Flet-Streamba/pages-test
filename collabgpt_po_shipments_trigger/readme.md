# collabgpt_po_shipments_trigger

Microservice to trigger the overdue-for-booking PO shipment workflow for the highest-priority, earliest-allocated not booked PO.
Necessary conditions on POs for being triggers (some from https://streamba.slack.com/archives/C026XKWLH6X/p1731945939441029):
    - 'shipmentDetails' is absent or empty
    - 'endorsedCollectionStatus' is 'Unknown', 'Assigned' or 'Pending Booking'
    - 'poNumber' is present and correctly formatted, i.e. \d+ (sometimes users write sentences or MRs in them)
    - 'allocatedAtDateTime' is older than the warning threshold for each 'priority'
        - 7 days for Sea, 1 day for P1, 2 days for P2 and P3, and 3 days for Courier (None values are ignored)

Runs daily (at 02:00 UK time, i.e. 10:00 Perth time), so after an initial period of daily triggers to go over the backlog it will only spawn workflows when needed.


