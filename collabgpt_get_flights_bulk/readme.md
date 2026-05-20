# collabgpt_get_flights_bulk

Microservice to ingest all Data Enhancer flight data in the given time frame and send it to the AI indexing service.

Runs when triggered by a get request here: https://vor-collabgpt-functions-dev.azurewebsites.net/api/collabgpt_get_flights_bulk
The request has to contain the "code" parameter, which has to be an Azure host key or function key allowed for this function.
The request also has to contain the "from" and "to" parameters, which should be yyyy-mm-dd strings.
The request may also contain the following OPTIONAL parameters:
- upload_batch_size - int: the number of retrieved entries to send in one index upload request; defaults to 200.

Note that the expected number of entries to upload is around 60 per week.

Also note that this function does not return until the processing is done, therefore requests will likely time out
for non-restricted invocations. Can inspect live and stored invocation logs in the function app UI.
