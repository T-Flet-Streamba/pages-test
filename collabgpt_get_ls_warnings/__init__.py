import azure.functions as func
import logging
import json
import pandas as pd
from shared.utils import filter_dataframe, truncate_json
from shared.redis_cache import SpecificRedisCache

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    ch = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    ch.setFormatter(formatter)
    logger.addHandler(ch)


class SummaryWarningsCache(SpecificRedisCache):
    def __init__(self, org: str):
        super().__init__(org=org, cache_path=f'VOR::LOGISTICSSUMMARY::{org}')

    def get_summary_warnings(self, filter_type=None):
        """Get data for logistics summary warnings, with optional filter
        """
        data = self._get_data(self.cache_path)
        if data:
            summary_items = data.get("items")
            if filter_type:
                summary_items = [item for item in summary_items if item["type"] == filter_type]
            return summary_items


def main(req: func.HttpRequest) -> func.HttpResponse:
    """Microservice to return a list of logistics summary warnings for a given
    org and filter_type [optional]
    """
    logger.info('Get LS warnings function triggered')

    org = req.params.get("organization")
    if not org:
        try:
            req_body = req.get_json()
        except (ValueError, AttributeError) as err:
            pass
        else:
            org = req_body.get("organization")

    # optional param filter type
    filter_type = req.params.get("filter_type")
    if not filter_type:
        try:
            req_body = req.get_json()
        except (ValueError, AttributeError) as err:
            pass
        else:
            filter_type = req_body.get("filter_type")

    # optional param location
    location = req.params.get("location")
    if not location:
        try:
            req_body = req.get_json()
        except (ValueError, AttributeError) as err:
            pass
        else:
            location = req_body.get("location")

    # optional param project code
    project_code = req.params.get("project_code")
    if not project_code:
        try:
            req_body = req.get_json()
        except (ValueError, AttributeError) as err:
            pass
        else:
            project_code = req_body.get("project_code")

    # optional param threshold
    threshold = req.params.get("threshold")
    if not threshold:
        try:
            req_body = req.get_json()
        except (ValueError, AttributeError) as err:
            pass
        else:
            threshold = req_body.get("threshold")

    try:
        threshold = int(threshold) if threshold is not None else None
    except (ValueError, TypeError):
        logging.info("Threshold value not valid: %s", str(threshold))
        threshold = None

    # get the data from redis cache
    r = SummaryWarningsCache(org)
    data = r.get_summary_warnings(filter_type=filter_type)

    filters = {
        "threshold": (">=", threshold),
        "projectCode": project_code,
        "location": location
    }
    data_filtered = []
    if data:
        data_filtered = filter_items(data, filters)
        data_str = json.dumps(truncate_json(data_filtered, max_list_length=10, max_depth=4))
        logger.info(f'Items found: {len(data_filtered)}')
        logger.info(f'Data (truncated, max len 10, depth 4): {data_str}')
    return func.HttpResponse(json.dumps({'data': data_filtered}), status_code=200)


def filter_items(items: list, filters: {}) -> list:
    """
    Filtering LS warning items, using a dictionary of filters (any fields that could be found
    within the LS warning), e.g.
    filters = {
        "location": "barrowislandrevlog",
        "projectCode": "JIC"
    }
    Exception is location where this is normalised by config below
    """
    config = {
        "RoadTransportJobHCRTransitTimeExceededWarning": {
            "item_columns": [
                "displayId",
                "accountCode",
                "clientRequestReference",
                "assetIds",
                "itemDescriptions",
                "actualPickupDateTime",
                "serviceType",
                "transitTime",
                "location"
            ],
            "item_reference": "freights",
            "location": "locationName",
            "threshold_value": "hcrWarningTimeInHours",
            "threshold_unit": "hours",
        },
        "HcrDwellTimeExceededAtLocation": {
            "item_columns": [
                'unit',
                'materialDescription',
                'origin',
                'destination',
                'projectCode',
                'unitStatus',
                'totalDaysDwellTime',
                'locationName',
                "plannedDepartureDate",
                "plannedVoyage",
                "plannedVoyageUrl"
            ],
            "item_reference": "units",
            "location": "locationId",
            "threshold_value": "totalDaysDwellTime",
            "threshold_unit": "days",
        },
        "DangerousGoodsWarning": {
            "item_columns": [
                "movementRequestNumber",
                "location",
                "requestDescription",
                "statusDisplayName",
                "ccuId",
                "finalDestination",
                "severity",
                "dgNames"
            ],
            "item_reference": "items",
            "location": "lastSeenLocation",
        }
    }
    output = []
    for ls_warning in items:
        warning_type = ls_warning.get("type")
        c = config.get(warning_type)
        if c is None:
            logging.info("Warning type not supported: %s", warning_type)
            continue

        # flatten out the data to item level
        items = ls_warning.pop(c.get("item_reference"))
        df_units = pd.DataFrame(items)
        df_warnings = pd.DataFrame([ls_warning], index=df_units.index)
        df_all = pd.concat([df_units, df_warnings], axis=1)

        # normalise the location column
        df_all.rename(columns={c.get("location"): "location"}, inplace=True)

        # set the threshold value to be filtered by
        if c.get("threshold_value"):
            df_all[c.get("threshold_value")] = df_all[c.get("threshold_value")].astype(int)  # rounding
            df_all["threshold"] = df_all[c.get("threshold_value")]

        # filter out the relevant items
        df_filtered = filter_dataframe(df_all, filters=filters)[df_all.columns.intersection(c.get("item_columns"))]
        if not df_filtered.empty:
            output.append(df_filtered.to_dict(orient="records"))

    # the above generates nested lists, flatten this out
    flattened_output = [item for sublist in output for item in sublist]
    return flattened_output
