# collabgpt_check_subscription_queue

Microservice to process subscription assessment requests from the queue.
It passes them to the Subscription Agent (waiting a bit if necessary to stay well below the model requests-per-minute limit),
logs their outcome, and updates the redis cache with newly-sent notifications and closure requests.


