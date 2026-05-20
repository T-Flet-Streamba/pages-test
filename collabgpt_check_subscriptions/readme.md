# collabgpt_check_subscriptions

Microservice to check whether the underlying data for all active subscriptions has changed.
If it has changed, it produces a diff between the old data snapshot (stored in a Redis cache) and the current data;
it then sends both to the Subscription Agent (along with the relevant user, entity info, and what the subscription conditions are).

Runs every 15 minutes.