import logging
import uuid
from datetime import datetime, timezone
from collections import defaultdict

from azure.functions import TimerRequest
from shared.slack import slack_logging

from collabgpt_po_shipments_trigger.classes import FlowiseWrapper, PoShipmentsTrigger
import config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logger.addHandler(ch)


@slack_logging
def main(poShipmentsTrigger: TimerRequest) -> None:
    """
    Trigger the overdue-for-booking PO shipment workflow for the oldest allocated-but-not-booked PO of the past n days.
    """
    utc_timestamp = datetime.now(tz=timezone.utc)
    logger.info('PO shipments workflow trigger function triggered at %s', utc_timestamp.isoformat())

    p = PoShipmentsTrigger(logger)
    p.get_data()
    overdue_pos = p.get_overdue_items()  # 'poNumber' guaranteed present and \d+ in these pos
    pon_to_po = {po['poNumber']: po for po in overdue_pos}

    w = FlowiseWrapper(logger, config.flowise.po_warnings_chatflow_id, 'PO Warnings')
    sessions = w.get_workflow_sessions()

    overdue_pos_by_ff = defaultdict(list)
    for po in overdue_pos:
        overdue_pos_by_ff[po['allocatedFreightForwarder']].append(po)

    supported_ffs = ['DBSchenker', 'DSV']
    if unrecognised_ffs := [ff for ff in overdue_pos_by_ff if ff not in supported_ffs]:
        logger.warning('Unrecognised freight forwarders found among overdue POs: %s', unrecognised_ffs)

    # Separating by freight forwarders so that each Chevron person responsible for each ff is contacted
    #   (i.e. the workflow will be triggered once per ff present in the list of currently overdue POs)
    for ff in supported_ffs:
        trigger_po_workflow(sessions=sessions, overdue_pos=overdue_pos_by_ff[ff], pon_to_po=pon_to_po, wrapper=w)


def trigger_po_workflow(sessions: list, overdue_pos: list[str], pon_to_po: dict[str, dict], wrapper: FlowiseWrapper):
    """
    Trigger the overdue POs workflow for the given arguments, in particular for the given overdue_pos, which may be
    restricted (e.g. to a specific freight forwarder).
    """
    all_pos_with_sessions = [po_str[2:] for s in sessions if (po_str := s['sessionId'].split('-')[0]).startswith('po')]
    pos_with_sessions = [pon for po in overdue_pos if (pon := po['poNumber']) in all_pos_with_sessions]
    if pos_without_sessions := [pon for po in overdue_pos if (pon := po['poNumber']) not in pos_with_sessions]:
        new_session_args = [dict(
            session_id=session_id[:-1] if session_id[-1] == '-' else session_id,
            _vars=dict(  # 'vars' would shadow the built-in Python function in FlowiseWrapper.start_workflow
                # Values specific to this po
                po=pon,
                threshold=pon_to_po[pon]['threshold'],
                allocated_date=pon_to_po[pon]['allocated_dt'].strftime('%d-%m-%Y'),
                freight_forwarder=pon_to_po[pon]['allocatedFreightForwarder'],
                # Values about all/other overdue POs
                n_overdue_pos=str(len(overdue_pos)),
                overdue_pos=pretty_po_list_str(overdue_pos),
                n_overdue_pos_with_sessions=str(len(pos_with_sessions) + i),
                n_overdue_pos_without_sessions=str(len(remaining_pos := pos_without_sessions[i:])),
                overdue_pos_without_sessions=pretty_po_list_str([pon_to_po[pon] for pon in remaining_pos]))
        ) for i, pon in enumerate(pos_without_sessions) if (session_id := f'po{pon}-{uuid.uuid4()}'[:36])]

        # Use only the 1st entry, i.e. start the workflow for the highest-priority earliest-allocated overdue PO
        r = wrapper.start_workflow(**new_session_args[0])
        logger.info('Workflow response: %s', r)


def pretty_po_list_str(pos: list[dict]) -> str:
    """
    Given a list of PO numbers, return a comma-separated list of "POxxxx [priority]" with the final one having an "and".
    E.g. "PO61071591 [P3 Air], PO61098062 [P3 Air], PO61073715 [P3 Air], PO61014710 [Courier], and PO61073714 [Sea]"
    """
    if pos:
        po_strs = [f"PO{po['poNumber']} [{po['priority']}]" for po in pos]
        return po_strs[0] if len(po_strs) == 1 else ', '.join(po_strs[:-1]) + f', and {po_strs[-1]}'
    else:
        return ''


# if __name__ == '__main__':
#     main(TimerRequest)


