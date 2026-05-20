import azure.functions as func
import json
import logging
import asyncio

# Set up the logger before importing anything else from this package
logging.getLogger().setLevel(logging.INFO)
if not logging.getLogger().hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)

import collabgpt_lg.bot as bot  # best to import the full module in __init__ scripts

from shared.mixpanel import track_event
from shared.slack import slack_logging


@slack_logging
def main(req: func.HttpRequest) -> func.HttpResponse:
    """Microservice interface with LangGraph based agents"""
    logging.info('CollabGPT LG function processed a request.')

    query = req.params.get('userQuery')

    if not query:
        try:
            req_body = req.get_json()
        except (ValueError, AttributeError) as err:
            logging.exception('Issue with query: %s', err)
        else:
            query = req_body.get('userQuery')

    response = bot.GraphLogisticsBot().run(query)

    if query and response:
        # Tracking is only really useful when have the response, so not tracking before running the bot
        if response['user_display_name'] != 'Automated Tester':  # not by user_id since it varies in tests
            properties = {k: v for k, v in response.items() if k in
                          ['source', 'organisation', 'user_display_name', 'user_teams_id', 'response_time', 'tokens_cost']}
            properties['distinct_id'] = response['user_id']
            properties['tools_used'] = [call['tool'] for call in response['used_tools']],
            track_event('collabgpt_lg_response', properties)
        return func.HttpResponse(json.dumps(response), status_code=200)
    else:
        return func.HttpResponse(json.dumps(dict(message='Error')), status_code=500)


