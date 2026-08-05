# Identity evidence policy

1. Mark an order `verified` only when its confirmed quantity is fully represented by passed print-job serials and ready shipping labels with the same order ID and serial. Model and color must also match the order.
2. A note may establish that one explicitly identified serial supersedes another only when it names the order, old serial and replacement serial.
3. Mark a confirmed order `insufficient_evidence` when required serials or labels are missing. Do not infer missing identifiers.
4. Mark an order `conflict` when two records claim different serials, models, colors or order IDs for the same physical item.
5. Mark canceled orders `canceled`; never place them in the verified identity chain.
6. Only `verified` orders may be considered ready for a later shipping decision. This task does not authorize shipment.
7. Exception owners: missing production evidence → `Production Lead`; label or serial conflict → `Fulfillment Lead`; canceled-order cleanup → `Order Operations`.
