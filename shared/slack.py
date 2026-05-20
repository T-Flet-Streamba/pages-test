import functools
import json
import logging
import requests
import sys
import traceback

import config


def slack_logging(func):
    """
    Decorator to send error messages to the Slack python functions channel
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        """
        Wrapper to catch all exceptions
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            data = {
                "text": f"{sys.modules[func.__module__].__file__} has failed: \n\n"
                        f"{traceback.format_exc()}"
            }
            logging.info(data)

            # only log live errors
            if config.ai_behaviour.environment == "live":
                requests.post(
                    config.slack.logging_webhook_url,
                    headers={"Content-type": "application/json"},
                    data=json.dumps(data)
                )
            raise e
    return wrapper


def log_on_slack(text: str) -> None:
    """Send an informational message to the Slack python functions channel (live only)."""
    if config.ai_behaviour.environment != 'live':
        return
    if not config.slack.logging_webhook_url:
        return
    requests.post(
        config.slack.logging_webhook_url,
        headers={'Content-type': 'application/json'},
        data=json.dumps(dict(text=text)),
    )
