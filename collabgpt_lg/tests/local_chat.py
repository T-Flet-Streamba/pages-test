"""Testing local back-and-forth chatting does not really fit with other tests (and pytest really does not like
capturing stdin unless all capturing is disabled: https://docs.pytest.org/en/6.2.x/capture.html)
"""
import json
import azure.functions as func
from collabgpt_lg import main


if __name__ == '__main__':
    # Set the organisation
    org = 'CHEVRON'
    # org = 'Shell UK'

    # Add previous interactions if tedious to input repeatedly
    # NOTE THAT CHAT INPUT IS IN REVERSE ORDER
    chat = []
    # chat = [
    #     'Mr User: @[vorai@vor.cloud] Tell me about WO1234567',
    #     'VOR AI: It looks like the reference number WO1234567 may contain a typo or could be incorrect. Could you please double-check the number and confirm the correct reference before I proceed with your request?'
    # ]
    chat = [
        'Mr User: @[vorai@vor.cloud] Escalate CMR123456 to Amanda',
        '''VOR AI: To proceed with the escalation of movement request CMR123456 to Amanda, I need to know the reason for the escalation.
            Could you please provide the reason for escalating this movement request?
        '''
    ]

    print('[Local chat with CollabGPT.]')
    for msg in chat:
        print(msg)
    print('[Send an empty message to end.]')

    while user := input('> '):                                  # vv note that message history is provided reversed
        request_data = dict(userQuery=dict(
            userId='test@user.edu',
            organization=org,
            existingMessages=chat[::-1],
            message=user
        ))
        req = func.HttpRequest(method='GET', body=None, url='/api/collabgpt_lg', params=request_data)

        resp = main(req)
        ai = json.loads(resp.get_body())

        print(ai_resp := f'VOR AI: {ai["message"]}')
        chat.extend([f'Mr User: {user}', ai_resp])


