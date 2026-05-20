# Context:
#   Projects are few and their patterns are too general (they overlap with most other entities');
#   they are therefore treated differently from other reference numbers (almost hardcoding them):
#       letters are left untouched (digits are still collapsed to \d),
#       intermediate patterns are of no interest.


# #### EXPORTED VARIABLE ####
project_regex = '(?:BATT|D(?:CF|EPMP)|EXPL|G(?:OR(?:DOM|OPS|S(?:CM|SPL)|T(?:A\\d{3}|P)|\\d{3})|S\\d)|JIC(?:OFF)?|ONEISL|PMPDCF|T(?:A(?:R\\d{3}|\\d{3})|\\d{3})|W(?:AO(?:BWI|DEC|WELLS)|HS(?:DS(?:OPS|T(?:A\\d{3}|P))|S(?:CM|SPL)|TA\\d{3}(?:/\\d{3}|\\d{3})|US(?:OPS|SPL|T(?:A\\d{3}|P)))))'
# #### EXPORTED VARIABLE ####


# #### Source list ####
#   The project list the above pattern is generated from; reported here since very short.
#   Also includes at least one instance for each project alias (e.g. T107/TA107/TAR107).

source_list = [
    'GOROPS',
    'GORDOM',
    'GORSSPL',
    'WHSUSSPL',
    'GORTA102',
    'GORTA107',
    'GORTA112',
    'GORTA103',
    'GORTA108',
    'WAOBWI',
    'WAODEC',
    'WHSUSOPS',
    'WHSUSTA512',
    'WHSDSOPS',
    'WHSDSTA503',
    'WHSDSTA504',
    'BATT',
    'JIC',
    'JICOFF',
    'DEPMP',
    'GS2',
    'GS3',
    'EXPL',
    'DEPMP',
    'GOROPS',
    'GS2',
    'GORTA107',
    'GORTA112',
    'JIC',
    'GORSSPL',
    'WHSSSPL',
    'WAODEC',
    'WAOBWI',
    'WHSDSOPS',
    'WHSUSOPS',
    'GOROPS',
    'GORDOM',
    'GORSSPL',
    'WHSUSSPL',
    'GORTA102',
    'GORTA107',
    'GORTA112',
    'GORTA103',
    'GORTA108',
    'WAOBWI',
    'WAODEC',
    'WHSUSOPS',
    'WHSUSTA512',
    'WHSDSOPS',
    'WHSDSTA503',
    'WHSDSTA504',
    'BATT',
    'JIC',
    'JICOFF',
    'DEPMP',
    'GS2',
    'GS3',
    'GORSCM',
    'GORTP',
    'ONEISL',
    'WHSDSTP',
    'WHSSCM',
    'WHSUSTP',
    'GOR112',
    'JICOFF',
    'PMPDCF',
    'DCF',
    'WAOWELLS',
    'WHSTA503512',
    'WHSTA503/512',
    'TAR107',
    'TA107',
    'T107'
]


