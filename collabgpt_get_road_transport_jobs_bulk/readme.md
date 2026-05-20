# collabgpt_get_road_transport_jobs_bulk

Microservice to ingest all Data Enhancer road transport data contained in a summary and send it to the AI indexing service.

Runs when triggered by a get request here: https://vor-collabgpt-functions-dev.azurewebsites.net/api/collabgpt_get_road_transport_jobs_bulk
The request has to contain the "code" parameter, which has to be an Azure host key or function key allowed for this function. 
The request may also contain the following OPTIONAL parameters:
- concurrent_requests_limit - int [30]: the maximum concurrent number of requests sent to the Data Enhancer to retrieve entries.
- entries_limit - int [None]: the number of entries to send requests for (backwards from the most recent).
- upload_batch_size - int [100]: the number of retrieved entries to send in one index upload request.

Note that the expected number of entries to upload (i.e. those updated in the last 14 days) is around 1500.

Also note that this function does not return until the processing is done, therefore requests will likely time out
for non-restricted invocations. Can inspect live and stored invocation logs in the function app UI.
