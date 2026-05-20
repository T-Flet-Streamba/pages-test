import time
from pprint import pp

from collabgpt_lg.bot import GraphLogisticsBot

prompt = '''
#### Main Goal ####
The data about some entity has changed (or you just got the data for the first time); you have the current data and the diff from the last time you checked it (if there was data at the time).
You also have a description of the conditions for when someone wishes to be notified about these changes (they "subscribed" to events of that kind for that entity).
Finally, you have all previous messages you sent the user about this subscription.

Your task is to determine whether the way the data has changed meets those conditions and whether you already told the user about the same implied event.
Based on that you then have to output a JSON object whose fields depend on the situation as described below; a notification will be sent to the user based on your output.


#### Guidelines
- If the notification conditions are for when the thing in question is delivered / arrives at its destination, the user only needs to be notified the user when that happens, and not when there are changes to the delivery estimate (or when the delivery location is added).
- Even if the user asks for notifications for all data changes, be smart about it: things like a change in the indexing date/timestamp are never worthy of notification. Even when you do write a notification for actually relevant changes, do not mention if indexing date/timestamp also changed.
- If you are writing a hyperlink in a field and the id in the url starts with "ignition-", make the visible part of the hyperlink be just the string after that prefix; e.g. if the url is "...ignition-sr12345...", the visible string should be just "SR12345", with SR capitalised (and it should link to the untouched url).


#### If the conditions are not met ####
If the change does not indicate that the subscription condition is satisfied, your full output should be ```{"conditions_are_met": false}```.


#### If the conditions are met BUT you have already told the user about the same event implied by this data change ####
Your full output should be ```{"conditions_are_met": true, "covered_before": true}```.


#### If the conditions are met AND you have not told the user about the same event implied by this data change ####
Your output should be ```{"conditions_are_met": true, "covered_before": false, "description_of_data_change": ..., "this_is_the_last_notification": ...}```, where the values of the "description_of_data_change" and "this_is_the_last_notification" fields should be as described below.

The value of "description_of_data_change" should be a string which:
- Starts with "Changes in ID_WITH_HYPERLINK:", where ID_WITH_HYPERLINK is a hyperlink where the text is the subscription entity's ID and the link is its url (which is somewhere in the full data).
- Briefly describes what changed in the data to make you determine that the subscription condition has been met (do not refer to specific data fields by name).
- If other relevant entities you mention in the data change have urls of their own, you should include them in the same way as the main entity one (i.e. as a hyperlink with the text is their ID).

The value of "this_is_the_last_notification" should be a simple bool reflecting whether you think the event which has occurred is the last event which would trigger those conditions.
To clarify: most subscriptions only have a single trigger (e.g. notify on arrival at final destination), but others will have multiple conditions (e.g. notify on departure, final arrival, and estimated time changes), so with this field you are noting whether no more notifications are expected after this.


#### User and Subscription Info ####
User: tfletcher@streamba.com
Entity ID: LMR131524
Entity Type: movement request
Notification conditions: when it is complete
  - (If the notification conditions are empty, treat that as meaning that any change is worth reporting)


#### Past notifications you have sent about this subscription ####
If any of the following messages you have already sent to the user already covers the gist of what you were going to tell the user about the the subscription condition being met, DO NOT send them a new message about it.
The point of "covering the gist of it" above is that there can be multiple data changes which all indicate the same thing, e.g. a delivery, but do not occur all together, which could make you think the condition you are looking for has happened again (while in fact it is just more data fields being updated to reflect the fact it has already occurred.
Here are the past messages you sent (there may be none):
```

```


#### New data (changes since the last time you checked it) ####
The following is how the full current data in the next section is different from your last snapshot of it; there may be no differences, in which case you should look in the full data for whether the notification conditions are fulfilled (or, if the notification conditions were empty, consider them not met).


#### Current Data ####
This is the current state of movement request LMR131524; if there are data changes above, then you should only consider those w.r.t. determining whether the subscription conditions are met, and only use the full data below as extra context when giving info to the user.
Only when there is no new data above should you actually base your decision as to whether the subscription conditions were met on this full data.

{'LMR131524': {'id': 'LMR131524', 'Status': 'Delivered - Marine', 'ModeOfTransport': 'Sea', 'Stage': 'Delivered', 'Parents': '', 'Flights': [], 'Projects': ['GOROPS'], 'RoadTransportJobs': ['ignition-sr69427'], 'Voyages': ['aurigaastrolabedsbbwi0605'], 'MaterialDescriptions': 'KIT: TYPE ON/OFF MULTI AND 2 WAY SPARES,APPLICATION VALVE, TOOL: TYPE COMBINATION RING/ OPEN END SPANNER,SIZE 22MM, FR869,ACAE-3P11340-SUPT011, FABRICATED - DO NOT ORDER GENERATOR: TYPE ZERO AIR, RATING 650CC/MIN, FR869,ABAE-2P11363-SUPT011, FABRICATED - DO NOT ORDER FR869,ABAE-2P11340-SUPT011, FABRICATED - DO NOT ORDER TONER: TYPE PRINTER, COLOR MAGENTA, TOOL: TYPE COMBINATION RING/ OPEN END SPANNER,SIZE 32MM, TOOL: TYPE COMBINATION RING/ OPEN END SPANNER,SIZE 27MM, ELEMENT: FILTER,SIZE 22.4MM ID X 45MM OD X 160MM LG, TAPE: TYPE THREAD SEAL (GAS), SIZE 12MM WD X 10 MT LG, GLASSES: SAFETY, TYPE INDUSTRIAL, CABLE: ELECTRICAL, TYPE LS, NUMBER OF CONDUCTORS 1, WASHER: TYPE SEAL, NOMINAL SIZE M12,MATERIAL CU DETECTOR: TYPE EXPLOSION PROOF OPEN PATH GAS, CRS 60 Emulsion FR869,ACAE-3P11363-SUPT011, FABRICATED - DO NOT ORDER LUBRICANT: TYPE PENETRATING OIL, FORM LIQUID, GASKET: RING JOINT, PIPE SIZE 2 IN (50MM), BOOTS: TYPE SAFETY GUMBOOT, SIZE 9 AUS, HEIGHT 400MM, Pallet containing ship spares WIPE: TYPE MERCURY,SIZE 200MM X 178MM,MATERIAL FIBRE COATED PROTECTOR: TYPE HARD HAT BRIM C/W FLAP, SIZE LARGE, ELBOW: TUBE ADAPTER REDUCER, SIZE 1/4 IN (8MM) X 1/2 IN, DRILL: TWIST,TYPE SPIRAL, SIZE 10MM,LENGTH 133MM, ELEMENT: FILTER,P/N R928006806 BOOTS: TYPE SAFETY GUMBOOT, SIZE 8 AUS, HEIGHT 400MM,', 'PONumbers': [], 'HCR': False, 'Hazmat': False, 'Events': [{'CcuDisplayId': 'ABQU2001423', 'DateTime': '2025-08-31T09:00:00', 'DetailedStatus': 'Lifted off of Auriga Astrolabe  at Barrow Island', 'LastSeenLocation': 'Barrow Island', 'Origin': 'Dampier', 'Destination': 'GORGON OPS', 'VoyageId': 'aurigaastrolabedsbbwi0605', 'Vessel': 'Auriga Astrolabe'}, {'CcuDisplayId': 'ABQU2001423', 'DateTime': '2025-08-31T06:56:40', 'DetailedStatus': 'Delivered to Dampier Supply Base - Area C', 'LastSeenLocation': 'Dampier Supply Base - Area C', 'Origin': 'Perth Supply Base', 'Destination': 'Dampier Supply Base - Area C', 'RoadTransportJobId': 'ignition-sr69427'}, {'CcuDisplayId': 'ABQU2001423', 'DateTime': '2025-08-30T15:00:00', 'DetailedStatus': 'Lifted on to Auriga Astrolabe  at Dampier Supply Base', 'LastSeenLocation': 'Dampier', 'Origin': 'Dampier', 'Destination': 'Barrow Island', 'VoyageId': 'aurigaastrolabedsbbwi0605', 'Vessel': 'Auriga Astrolabe'}, {'CcuDisplayId': 'ABQU2001423', 'DateTime': '2025-08-30T14:00:00', 'DetailedStatus': 'Delivered to Dampier Supply Base - Area C', 'LastSeenLocation': 'Dampier Supply Base - Area C', 'Destination': 'Dampier Supply Base - Area C'}, {'CcuDisplayId': 'ABQU2001423', 'DateTime': '2025-08-26T14:08:40', 'DetailedStatus': 'Collected from Perth Supply Base', 'LastSeenLocation': 'Perth Supply Base', 'Origin': 'Perth Supply Base', 'Destination': 'Dampier Supply Base - Area C', 'RoadTransportJobId': 'ignition-sr69427'}], 'SplitChildRequests': [], 'SplitParentRequests': [], 'ReverseParent': [], 'Packs': ['000119570008484821', '000119570008484654', '000119570008485125', '000119570008485057', '000119570008484517', '000119570008484845', '000119570008484890', '000119570008484562', '000119570008484876', '000119570008484968', '000119570008484920', '000119570008485002', '000119570008485040', '000119570008484937', '000119570008484746', '000119570008485163', '000119570008483602', '000119570008483626', '000119570008484739', '000119570008483749', '000119570008485231', '000119570008485064', '000119570008476727', '000119570008484951', '000119570008484135', '000119570008484579', '000119570008484586', '000119570008484944', '000119570008484999', '000119570008484524', '000119570008484975', '000119570008484234', '000119570008484388', '000119570008483701', '000119570008485019', '000119570008484722', '000119570008485224', '000119570008484852', '000119570008484357', '000119570008485026', '000119570008484883', '000119570008483787', '000119570008485101', '000119570008484869', '000119570008484623', '000119570008484531', '000119570008484982'], 'Tares': ['100119570008484033', '100119570008484637', '100119570008476748'], 'Organization': None, 'LastUpdated': '0001-01-01T00:00:00', 'MovementRequestEta': None, 'MovementRequestEtaText': None, 'MovementRequestEtaJustification': '', 'CcuId': 'ABQU2001423', 'LastUpdatedAtDateTime': '2025-08-31T09:00:00', 'LastSeenLocation': 'Barrow Island', 'FinalDestination': 'Barrow Island', 'IsPriority': False, 'PlannedEvents': [], 'TransportPlan': [], 'RequiredOnSiteDate': '2027-06-01T04:00:00', 'RequestDescription': 'GORGON ABQU2001423', 'KabalId': '', 'WasteMovementReturnCMR': None, 'WasteMovementForwardCMR': None, 'ChargeToDepartmentName': None, 'ChargeToDepartmentCode': None, 'Project': '', 'url': 'https://vor2dev.streamba.cloud/supplychain#/movementRequest/LMR131524', 'container_url': 'https://vor2dev.streamba.cloud/supplychain#/containerEvents/ABQU2001423', 'road_transport_jobs_urls': 'https://vor2dev.streamba.cloud/supplychain#/roadTransport/jobs/ignition-sr69427', 'voyages_urls': 'https://vor2dev.streamba.cloud/supplychain#/voyage/aurigaastrolabedsbbwi0605'}}
'''

old_prompt = '''
#### Main Goal ####
The data about some entity has changed (or you just got the data for the first time); you have the current data and the diff from the last time you checked it (if there was data at the time).
You also have a description of the conditions for when someone wishes to be notified about these changes (they "subscribed" to events of that kind for that entity).
Finally, you have all previous messages you sent the user about this subscription.

Your task is to determine whether the way the data has changed meets those conditions and whether you already told the user about the same implied event; you have instructions on what to do in each case below.


#### User and Subscription Info ####
User: tfletcher@streamba.com
Entity ID: LMR131524
Entity Type: movement request
Notification conditions: when it is complete
  - (If the notification conditions are empty, treat that as meaning that any change is worth reporting)


#### Guidelines
- If the notification conditions are for when the thing in question is delivered / arrives at its destination, you only have to notify the user when that happens, and not when there are changes to the delivery estimate (or when the delivery location is added).
- Even if the user asks for notifications for any data change, be smart about it: things like a change in the indexing date/timestamp are never worthy of notification. Even when you do send a notification for actually relevant changes, do not mention if indexing date/timestamp also changed.


#### If the conditions are not met ####
If the change does not indicate that the subscription condition is satisfied, do not use any tool; instead, just have your output text be "The data change does not match the subscription condition".


#### If the conditions are met BUT you have already told the user about the same event implied by this data change ####
Do not use any tool; instead, just have your output text be "The data change is already covered by a previous notification about the subscription condition.".


#### If the conditions are met AND you have not told the user about the same event implied by this data change ####
Use the Teams messaging tool to send them A SINGLE message following the instructions below, informing them that an event they had subscribed to has occurred.
Use Markdown in the message, with the header "# VOR Subscription Notification", and follow the instructions below.
NEVER SEND MORE THAN ONE MESSAGE.

Make sure to mention all of the following:
- Entity ID
- Entity type
- What the notification condition was
- All the details it is relevant to include about what changed (do not refer to specific data fields by name, just communicate the essence of what made you deem the notification condition fulfilled).
- Any urls present in the data
    - Try to include them contextually as hyperlinks from their IDs (e.g. ideally you should make the first mention of the entity ID a hyperlink to its url).
        - If the id in the url starts with "ignition-", make the visible part of the hyperlink be just the string after that prefix; i.e. if the url is about "ignition-sr12345", the visible string should be "SR12345", with SR capitalised (and it should link to the untouched url).

One final thing you have to consider before sending the message is whether you think the event which has occurred is the last event which would trigger those conditions; most subscriptions only have a single trigger (e.g. notify on arrival at final destination), but others will have multiple conditions (e.g. notify on departure, final arrival, and estimated time changes).

If this IS indeed the final event of the ones of interest, then end the Teams message with a couple of empty lines and then, in bold "I am scheduling this subscription to be closed; would you like me to close it now instead?".
If it is NOT the final event you should instead end the Teams message with a couple of empty lines and then, in bold "Should I close this subscription?".

After you have sent the Teams message, your final text output should start with "SENT THIS NOTIFICATION" and include an exact copy enclosed in triple quotes """ after it.
Then, if this was the final event (and you said so in the Teams message), make sure your text output ends with "SCHEDULE SUBSCRIPTION CLOSURE".



#### Past notifications you have sent about this subscription ####
If any of the following messages you have already sent to the user already covers the gist of what you were going to tell the user about the the subscription condition being met, DO NOT send them a new message about it.
The point of "covering the gist of it" above is that there can be multiple data changes which all indicate the same thing, e.g. a delivery, but do not occur all together, which could make you think the condition you are looking for has happened again (while in fact it is just more data fields being updated to reflect the fact it has already occurred.
Here are the past messages you sent (there may be none):
```


```

#### New data (changes since the last time you checked it) ####
The following is how the full current data in the next section is different from your last snapshot of it; there may be no differences, in which case you should look in the full data for whether the notification conditions are fulfilled (or, if the notification conditions were empty, consider them not met).



#### Current Data ####
This is the current state of movement request LMR131524; if there are data changes above, then you should only consider those w.r.t. determining whether the subscription conditions are met, and only use the full data below as extra context when giving info to the user.
Only when there is no new data above should you actually base your decision as to whether the subscription conditions were met on this full data.

{'LMR131524': {'id': 'LMR131524', 'Status': 'Delivered - Marine', 'ModeOfTransport': 'Sea', 'Stage': 'Delivered', 'Parents': '', 'Flights': [], 'Projects': ['GOROPS'], 'RoadTransportJobs': ['ignition-sr69427'], 'Voyages': ['aurigaastrolabedsbbwi0605'], 'MaterialDescriptions': 'KIT: TYPE ON/OFF MULTI AND 2 WAY SPARES,APPLICATION VALVE, TOOL: TYPE COMBINATION RING/ OPEN END SPANNER,SIZE 22MM, FR869,ACAE-3P11340-SUPT011, FABRICATED - DO NOT ORDER GENERATOR: TYPE ZERO AIR, RATING 650CC/MIN, FR869,ABAE-2P11363-SUPT011, FABRICATED - DO NOT ORDER FR869,ABAE-2P11340-SUPT011, FABRICATED - DO NOT ORDER TONER: TYPE PRINTER, COLOR MAGENTA, TOOL: TYPE COMBINATION RING/ OPEN END SPANNER,SIZE 32MM, TOOL: TYPE COMBINATION RING/ OPEN END SPANNER,SIZE 27MM, ELEMENT: FILTER,SIZE 22.4MM ID X 45MM OD X 160MM LG, TAPE: TYPE THREAD SEAL (GAS), SIZE 12MM WD X 10 MT LG, GLASSES: SAFETY, TYPE INDUSTRIAL, CABLE: ELECTRICAL, TYPE LS, NUMBER OF CONDUCTORS 1, WASHER: TYPE SEAL, NOMINAL SIZE M12,MATERIAL CU DETECTOR: TYPE EXPLOSION PROOF OPEN PATH GAS, CRS 60 Emulsion FR869,ACAE-3P11363-SUPT011, FABRICATED - DO NOT ORDER LUBRICANT: TYPE PENETRATING OIL, FORM LIQUID, GASKET: RING JOINT, PIPE SIZE 2 IN (50MM), BOOTS: TYPE SAFETY GUMBOOT, SIZE 9 AUS, HEIGHT 400MM, Pallet containing ship spares WIPE: TYPE MERCURY,SIZE 200MM X 178MM,MATERIAL FIBRE COATED PROTECTOR: TYPE HARD HAT BRIM C/W FLAP, SIZE LARGE, ELBOW: TUBE ADAPTER REDUCER, SIZE 1/4 IN (8MM) X 1/2 IN, DRILL: TWIST,TYPE SPIRAL, SIZE 10MM,LENGTH 133MM, ELEMENT: FILTER,P/N R928006806 BOOTS: TYPE SAFETY GUMBOOT, SIZE 8 AUS, HEIGHT 400MM,', 'PONumbers': [], 'HCR': False, 'Hazmat': False, 'Events': [{'CcuDisplayId': 'ABQU2001423', 'DateTime': '2025-08-31T09:00:00', 'DetailedStatus': 'Lifted off of Auriga Astrolabe  at Barrow Island', 'LastSeenLocation': 'Barrow Island', 'Origin': 'Dampier', 'Destination': 'GORGON OPS', 'VoyageId': 'aurigaastrolabedsbbwi0605', 'Vessel': 'Auriga Astrolabe'}, {'CcuDisplayId': 'ABQU2001423', 'DateTime': '2025-08-31T06:56:40', 'DetailedStatus': 'Delivered to Dampier Supply Base - Area C', 'LastSeenLocation': 'Dampier Supply Base - Area C', 'Origin': 'Perth Supply Base', 'Destination': 'Dampier Supply Base - Area C', 'RoadTransportJobId': 'ignition-sr69427'}, {'CcuDisplayId': 'ABQU2001423', 'DateTime': '2025-08-30T15:00:00', 'DetailedStatus': 'Lifted on to Auriga Astrolabe  at Dampier Supply Base', 'LastSeenLocation': 'Dampier', 'Origin': 'Dampier', 'Destination': 'Barrow Island', 'VoyageId': 'aurigaastrolabedsbbwi0605', 'Vessel': 'Auriga Astrolabe'}, {'CcuDisplayId': 'ABQU2001423', 'DateTime': '2025-08-30T14:00:00', 'DetailedStatus': 'Delivered to Dampier Supply Base - Area C', 'LastSeenLocation': 'Dampier Supply Base - Area C', 'Destination': 'Dampier Supply Base - Area C'}, {'CcuDisplayId': 'ABQU2001423', 'DateTime': '2025-08-26T14:08:40', 'DetailedStatus': 'Collected from Perth Supply Base', 'LastSeenLocation': 'Perth Supply Base', 'Origin': 'Perth Supply Base', 'Destination': 'Dampier Supply Base - Area C', 'RoadTransportJobId': 'ignition-sr69427'}], 'SplitChildRequests': [], 'SplitParentRequests': [], 'ReverseParent': [], 'Packs': ['000119570008484821', '000119570008484654', '000119570008485125', '000119570008485057', '000119570008484517', '000119570008484845', '000119570008484890', '000119570008484562', '000119570008484876', '000119570008484968', '000119570008484920', '000119570008485002', '000119570008485040', '000119570008484937', '000119570008484746', '000119570008485163', '000119570008483602', '000119570008483626', '000119570008484739', '000119570008483749', '000119570008485231', '000119570008485064', '000119570008476727', '000119570008484951', '000119570008484135', '000119570008484579', '000119570008484586', '000119570008484944', '000119570008484999', '000119570008484524', '000119570008484975', '000119570008484234', '000119570008484388', '000119570008483701', '000119570008485019', '000119570008484722', '000119570008485224', '000119570008484852', '000119570008484357', '000119570008485026', '000119570008484883', '000119570008483787', '000119570008485101', '000119570008484869', '000119570008484623', '000119570008484531', '000119570008484982'], 'Tares': ['100119570008484033', '100119570008484637', '100119570008476748'], 'Organization': None, 'LastUpdated': '0001-01-01T00:00:00', 'MovementRequestEta': None, 'MovementRequestEtaText': None, 'MovementRequestEtaJustification': '', 'CcuId': 'ABQU2001423', 'LastUpdatedAtDateTime': '2025-08-31T09:00:00', 'LastSeenLocation': 'Barrow Island', 'FinalDestination': 'Barrow Island', 'IsPriority': False, 'PlannedEvents': [], 'TransportPlan': [], 'RequiredOnSiteDate': '2027-06-01T04:00:00', 'RequestDescription': 'GORGON ABQU2001423', 'KabalId': '', 'WasteMovementReturnCMR': None, 'WasteMovementForwardCMR': None, 'ChargeToDepartmentName': None, 'ChargeToDepartmentCode': None, 'Project': '', 'url': 'https://vor2dev.streamba.cloud/supplychain#/movementRequest/LMR131524', 'container_url': 'https://vor2dev.streamba.cloud/supplychain#/containerEvents/ABQU2001423', 'road_transport_jobs_urls': 'https://vor2dev.streamba.cloud/supplychain#/roadTransport/jobs/ignition-sr69427', 'voyages_urls': 'https://vor2dev.streamba.cloud/supplychain#/voyage/aurigaastrolabedsbbwi0605'}}
'''

bot = GraphLogisticsBot('CHEVRON')

start = time.perf_counter()
res = bot.llms['fast'].invoke(
    prompt
    # old_prompt
)
took = time.perf_counter() - start

print(res.content)
print(res.usage_metadata)
# pp(res.model_dump())
print(took)