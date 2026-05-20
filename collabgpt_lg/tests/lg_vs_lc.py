import pickle
import re
import pytest
import pandas as pd
from pydantic import BaseModel, Field
from collections import Counter
from itertools import groupby

from langchain_core.prompts import PromptTemplate

from collabgpt_lg.bot import GraphLogisticsBot
from collabgpt_lg.utils import sort_test_responses, batch_test_responses


class Assessment(BaseModel):
    """Assessment of the quality of a batch of query answers: a list of scores and a summary of their reasons."""
    a_score: int = Field(description='Score from 1 to 5 for system_type A')
    b_score: int = Field(description='Score from 1 to 5 for system_type B')
    summary: str = Field(description='A paragraph summarising the difference between answers from the two systems.')


structured_llm = GraphLogisticsBot().llms['reasoning'].with_structured_output(Assessment)


assessments_prompt = PromptTemplate.from_template('''
Your task is to assess the quality of the answers to queries in the list of {n_entries} responses below.
Return your assessments of the set of answers in the form of three values:
    - An integer score from 1 to 5 for answers by system_type A, with 1 being very poor and 5 being very good.
    - An integer score from 1 to 5 for answers by system_type B, with 1 being very poor and 5 being very good.
    - A paragraph explaining the scores and differences between answers by the two systems.

If there are no answers by one of the systems, its score is an automatic 1.

The following is a list of criteria you should take into account when coming up with your scores:
    - Your most important concern is whether the requested information is present in the answer.
      Some queries will be just alphanumeric strings representing some entities;
      in those cases you may consider the answer satisfactory in this aspect unless no data is found.
    - Your second concern is whether the tool used to answer the query is within the expected ones;
      the 'behaved_as_expected' field tells you whether this was the case.
      Ignore the number of tools in 'expected_tools', as these are just acceptable choices, not requirements.
      Similarly, do not detract points for a high number of tools in 'tools_used'.
      Do, however, detract points (and mention) if there are negative comments in the 'comments' field.
    - Your third concern is inconsistencies in answering the same query.
      However, the inconsistencies you care about are NOT in the actual state of things being returned;
      this is because it is entirely possible for the underlying situation to have changed between each time an answer was generated.
      The inconsistencies you DO care about are whether the same system uses different tools or produces different levels of detail. 
      So if the answer given is satisfactory in all cases for one system but the underlying data situation has changed, they should not be marked down.
      If there is no overlap in the tools used in one query with those used by its other instances, detract one point.
      If an answer promises to give some information and then does not give it, give a score of 1 and mention the query_id explicitly. 
    - Your fourth concern is whether the answer is clear and concise:
      a lot of data may be generated when producing these answers, and users may very well appreciate it,
      but answer length is important too.
      So first decide whether you think all the information in the answer is likely to be of interest given
      the query, and then decide whether it could have been reported more clearly or concisely
      (e.g. as dotted lists instead of long sentences).
    - Finally, if the answer is formatted as JSON (instead of standard text or markdown), give a score of 1.

Query and answer data:
{queries_and_answers}
''')


summary_prompt = PromptTemplate.from_template('''
Your task is to summarise a list of repetitive paragraphs.
The paragraphs are assessments of the quality of answers to batches of queries,
and will be very repetitive except when mentioning specific answers directly.

Your summary should capture the essence of the set but should also
report anything which was specifically highlighted as a negative;
it is very important that this negative feedback is not lost, especially if a query_id is mentioned negatively
(query_ids look like 'float@int', e.g. '12.1@20').

Assessments: {assessments}
''')


def assess_answer_batch(batch: list[dict]) -> Assessment:
    chain = assessments_prompt | structured_llm
    return chain.invoke(dict(n_entries=len(batch), queries_and_answers=batch))


def summarise_summaries(assessments: list[Assessment]) -> str:
    chain = summary_prompt | GraphLogisticsBot().llms['reasoning']
    return chain.invoke(dict(assessments='\n\n'.join(a.summary for a in assessments))).content


def test_compare_two_systems(request):
    """Function based on test_assess_response_quality but tweaked to compare multiple answers by two systems to the same questions."""
    # Import the responses from the cache or a file
    response_cache = request.config.cache.get('responses', [])
    # import pickle
    # with open('response_cache_ALL_24-06-2025.pkl', 'rb') as file:
    #     response_cache0 = pickle.load(file)
    # with open('response_cache_last_2.pkl', 'rb') as file:
    #     response_cache2 = pickle.load(file)
    # response_cache = response_cache2


    ####################################
    #### vv STATIC CONFIGURATION vv ####

    # Uncomment and edit as required to assess/save only a portion of the cache
    # (e.g. to only focus on queries with message history after an initial batch without them)
    # response_cache = response_cache[180:]

    only_these_systems = [
        'LangGraph',
        'LangChain'
    ]

    only_these_orgs = [
        'CHEVRON',
        'Shell UK'
    ]
    # only_these_orgs = []  # uncomment for no filtering

    #### ^^ STATIC CONFIGURATION ^^ ####
    ####################################

    if only_these_systems:
        response_cache = [r for r in response_cache if r['system_type'] in only_these_systems]

    if only_these_orgs:
        response_cache = [r for r in response_cache if r['organisation'] in only_these_orgs]

    # # Save the Python object for easy re-import
    # import pickle
    # with open('response_cache.pkl', 'wb') as file:
    #     pickle.dump(response_cache, file)

    # Sort by query and offset replicates if from later batches
    response_cache = sort_test_responses(response_cache)

    # Remade after the next loop
    df = pd.DataFrame(response_cache)

    assert response_cache, 'The cache is empty; run test_invoked_tool with at least one test case to fill it.'
    unique_queries = {query: i+1 for i, query in enumerate(df['query'].unique())}
    for i, r in enumerate(response_cache):
        # The id is: {unique query int}.{adjusted replicate number (+=100 for later batches)}@{index in the reordered response_cache}
        r['query_id'] = f"{unique_queries[r['query']]}.{r['replicate']}@{i}"
        r['query_index'] = i
        r['unique_query'] = unique_queries[r['query']]  # storing it to batch intelligently later
        indented_msg = re.sub('\n', '\n\t', r['message'])
        r['printout'] = f"{r['system_type']} Query {r['query_id']}: {r['query']}"
        if comments := '\n\t'.join(r.get('comments', [])):
            r['printout'] += f"\nComments {r['query_id']}:\n\t{comments}"
        r['printout'] += f"\nAnswer {r['query_id']} - {'GOOD' if r['behaved_as_expected'] else 'BAD'}:\n\t{indented_msg}"

    # Save to a human-friendly csv
    df = pd.DataFrame(response_cache)
    df['expected_tools'] = df['expected_tools'].apply(lambda xs: ', '.join([str(x) for x in xs]))
    df['used_tool_names'] = df['used_tool_names'].combine_first(df['tools_used'])
    df['tools_params'] = [dict(tool=tool, args=args) for tool, args in zip(df['tools_used'], df['tools_params'])]
    df['used_tools'] = df['used_tools'].combine_first(df['tools_params'])
    del df['tools_used']
    del df['tools_params']
    df['used_tool_names'] = df['used_tool_names'].apply(lambda xs: ', '.join([str(x) for x in xs]))
    df['comments'] = df['comments'].apply(lambda xs: '\n'.join([str(x) for x in xs]))
    first_few_columns = ['behaved_as_expected', 'organisation', 'query', 'query_index', 'query_id', 'replicate', 'message', 'expected_tools', 'used_tool_names', 'used_tools', 'comments', 'existing_messages']
    df = df[first_few_columns + [col for col in df.columns if col not in first_few_columns]]
    df.to_csv('response_cache.csv', index=False)

    # Print out queries and answers before beginning the assessment; uncomment sets of interest
    all_printouts = [r['printout'] for r in response_cache]
    unexpected_printouts = [r['printout'] for r in response_cache if not r['behaved_as_expected']]
    commented_printouts = [r['printout'] for r in response_cache if r['comments']]
    sql_commented_printouts = [r['printout'] for r in response_cache if 'SQL' in '\n\n'.join(r.get('comments', []))]

    report = []

    report.append('\n\n## Query ID schema ##\n\t{unique query int} . {adjusted replicate number (+=100 for later batches)} @ {index in the reordered response_cache}')
    # report.extend([f'\n\n## All responses ({len(all_printouts)}) ##\n\n', '\n\n'.join(all_printouts)])
    report.extend([f'\n\n## Unexpected responses ({len(unexpected_printouts)}) ##\n\n', '\n\n'.join(unexpected_printouts)])
    # report.extend([f'\n\n## Responses with comments ({len(commented_printouts)}) ##\n\n', '\n\n'.join(commented_printouts)])
    report.extend([f'\n\n## Responses with unnecessary SQL ({len(sql_commented_printouts)}) ##\n\n', '\n\n'.join(sql_commented_printouts)])

    # Anonymise the system_type
    for r in response_cache:
        r['system_type'] = dict(LangGraph='A', LangChain='B')[r['system_type']]

    # Generate assessments
    batch_len = 4  ### Set a breakpoint here to manually sift through the now-sorted response_cache ###
    report.append('\n\n\n## Response quality assessment ##\n\n')
    report.append(f'Assessing {len(response_cache)} queries in batches of {batch_len} (exceedable to avoid splitting same queries over batches).')
    uqs, assessments = [], []
    for _, group in groupby(response_cache, key=lambda d: d['unique_query']):
        batch = list(group)
        report.append(f"\nQueries {batch[0]['query_id']} to {batch[-1]['query_id']}:")
        assessment = assess_answer_batch(batch)
        uqs.append(batch[0]['query'])
        assessments.append(assessment)
        report.append(str(assessment))

    # Save/import the Python object for easy re-import
    with open('uqs_and_assessments.pkl', 'wb') as file:
        pickle.dump((uqs, assessments), file)
    # with open('uqs_and_assessments.pkl', 'rb') as file:
    #     uqs, assessments = pickle.load(file)

    # Report scores info
    a_scores = [a.a_score for a in assessments]
    b_scores = [a.b_score for a in assessments]
    a_mean_score = sum(a_scores) / len(a_scores)
    b_mean_score = sum(b_scores) / len(b_scores)
    a_counts = Counter(a_scores)
    b_counts = Counter(b_scores)

    report.append(f'\n\n\n## REPORT ##')
    report.append(f'Mean A score: {a_mean_score:.3f}\nMean B score: {b_mean_score:.3f}')
    report.append(f'A Score counts: {a_counts}\nB Score counts: {b_counts}')

    # Summarise all assessments
    summary = summarise_summaries(assessments)
    report.extend([summary, '\n\n'])

    # Report other metrics (times and tokens)
    for system_type in 'AB':
        other_trackables = pd.DataFrame()
        for k in ['response_time', 'tokens_count', 'tokens_cost']:
            other_trackables[k] = [r.get(k) for r in response_cache if r['system_type'] == system_type]
        pd.set_option('display.max_columns', None, 'display.width', 200)
        report.append(f'System {system_type} summary statistics:')
        report.append(str(summ_stats := other_trackables.describe().T.drop('count', axis=1)))
        upper_outliers = {c: {r+1: x for r in range(len(other_trackables)) if (x := round(other_trackables.at[r, c], 6))
                          if x > summ_stats.at[c, '50%'] + 1.5 * (summ_stats.at[c, '75%'] - summ_stats.at[c, '25%'])}
                          for c in other_trackables}  # ^^ standard outlier definition as "> median + 1.5xIQR"
        report.append(f'\nSystem {system_type} outliers (query_id: value):')
        report.extend([f'\t{k}: {v}' for k, v in upper_outliers.items()])
        report.append('\n')

    # Compile and report the report
    report = '\n'.join(report)
    print(report)
    with open('comparison_report.md', 'w', encoding='utf-8') as file:
        file.write(report)


