/**
 * Query-key roots that one entity's writes invalidate in another's cache.
 * They live here, below the entities, so a session or timer write can
 * refresh the billing figures without importing `entities/billing`, and a
 * billing write can refresh the clients (whose `currency_locked` it moves)
 * without importing `entities/client`. Each entity builds its own keys on
 * its root.
 */

/** Every billing read: project billing, entry marks and the month's figures. */
export const billingRootKey = ["billing"] as const;

/** Every client read. */
export const clientsRootKey = ["clients"] as const;

/**
 * Every organisation read. A write to the timeline invalidates it too: an
 * entry edited, deleted or logged, and a timer stopped, all move what the
 * organisation reads of its own projects — the record, "What Acme can see"
 * and the archive are assembled from the same beats (docs/organisations.md).
 */
export const organisationsRootKey = ["organisations"] as const;
