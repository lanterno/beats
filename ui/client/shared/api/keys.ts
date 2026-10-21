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
 * Every report link read: the lists and the share dialog's preview. A
 * billing write and a client delete refresh it, since a project moved to
 * another client or no longer billed leaves its old client's links, and a
 * deleted client's links go with it (docs/billing.md, phase 1c).
 */
export const reportLinksRootKey = ["report-links"] as const;
