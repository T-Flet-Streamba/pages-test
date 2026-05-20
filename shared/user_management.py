import logging
import requests

import config


class UserManagement:
    def __init__(self):
        self.UA_TENANT_ID = None
        self.UA_CLIENT_ID = None
        self.UA_CLIENT_SECRET = None
        self.use_live_env = config.ai_behaviour.environment == 'live'
        self.base_url = f'https://vor-user-management-api-{'live' if self.use_live_env else 'dev'}.azurewebsites.net/api/'

    def _gen_ua_bearer_token(self):
        """Function to generate the bearer token required for auth with the user actions endpoints."""
        r = requests.post(
            url=f'https://login.microsoftonline.com/{self.UA_TENANT_ID}/oauth2/v2.0/token',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'grant_type': 'client_credentials',
                'client_id': self.UA_CLIENT_ID,
                'client_secret': self.UA_CLIENT_SECRET,
                'scope': 'https://graph.microsoft.com/.default'
            }
        )
        r.raise_for_status()

        if r.status_code == 200:
            self.bearer_token = r.json()['access_token']
            logging.info('Created a new customer API bearer token')
        else:
            raise ValueError(f'Failed to generate access token. Status code {r.status_code}')

    def get_teams_email_by_id(self, teams_id: str):
        """Check Teams user account by Teams ID."""
        response = requests.get(
            url=f'{self.base_url}/TeamsUser/GetTeamsMappingByTeamsId',
            headers={
                'Content-Type': 'application/json',
                'accept': 'application/json'
                # 'Authorization' : f'Bearer {self.bearer_token}'
            },
            params={'teamsId': teams_id}
        ).json()

        user_id, user_email = None, None
        if isinstance(response, dict):
            # check if email is mapped
            user_email = response.get('document').get('userEmail')
        elif isinstance(response, str) and 'No Teams mapping found' in response:
            # issue, user should have a mapping, route back and get them to contact support
            raise KeyError('No Teams mapping found')
        return user_email

    def get_teams_id_by_email(self, email):
        """Check Teams user account by Teams Email."""
        response = requests.get(
            url=f'{self.base_url}/TeamsUser/GetTeamsMappingByEmail',
            headers={
                'Content-Type': 'application/json',
                'accept': 'application/json'
                # 'Authorization' : f'Bearer {self.bearer_token}'
            },
            params={'email': email}
        ).json()

        user_id, user_email = None, None
        if isinstance(response, dict):
            # check if email is mapped
            user_id = response.get('document').get('userId')
        elif isinstance(response, str) and 'No Teams mapping found' in response:
            # issue, user should have a mapping, route back and get them to contact support
            raise KeyError('No Teams mapping found')
        return user_id

    def update_user_account(self, teams_id, email):
        """Update a specific user account with new data."""
        r = requests.post(
            url=f'{self.base_url}/TeamsUser/CreateUserEmailMapping',
            headers={'Content-Type': 'application/json'},
            json={
                'teamsId': teams_id,
                'userEmail': email
            }
        )
        return r.text

    def remove_user_mapping(self, teams_id):
        """Remove the email mapping for the given Teams ID."""
        r = requests.post(
            url=f'{self.base_url}/TeamsUser/ClearUserEmailMapping',
            headers={'Content-Type': 'application/json'},
            json={'teamsId': teams_id}
        )
        return r.text


