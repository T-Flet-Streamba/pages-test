import json
import re

with open(r'C:\Users\T-Fle\Projects\Misc\Collate Message History\query_data_merged_messages.json', 'r', encoding='utf-8') as fh:
    data = json.load(fh)

sub_notifications = [re.search('(?<=changes in )[\s\S]+', d).group() for d in data if 'Subscription Notification' in d]


print()