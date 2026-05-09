# Reimbursement Engine — Client API Reference

**Version:** 1.0  
**Base URL:** `https://<your-host>/api`  
**Auth:** All endpoints require a valid `Authorization: Bearer <access_token>` header.  
**Content-Type:** `application/json`

---

## Overview

The reimbursement engine lets you link an **income** transaction to an **expense** transaction to record that the expense was paid back (in full or in part). This is the correct way to handle scenarios such as:

- A colleague paid you back for a shared dinner expense
- An employer reimbursed a business travel charge
- A refund deposit arrived that offsets a purchase

### Key Design Decisions You Should Know

| Property | Detail |
|---|---|
| **Junction table architecture** | Reimbursements are stored in a separate table, not as flags on transactions. This allows multiple partial reimbursements against one expense. |
| **No negative amounts** | Transaction amounts are always positive. The `type` field (`"expense"` / `"income"`) determines direction. |
| **Amounts are decimals, not integer cents** | `amount` fields use the same `Decimal(19,4)` format as `transactions.amount`. Send e.g. `65.00` for $65.00 — **not** `6500`. |
| **Household-scoped** | Both transactions must belong to the authenticated user's household. Requests referencing another household's data receive `404`, not `403`, to prevent IDOR leakage. |
| **Idempotency** | Creating a link between the same `(expense_id, income_id)` pair twice returns `409`. Use PUT to update the existing link. |

---

## Data Model

### TransactionReimbursement Object

```json
{
  "id": "3f1e2d4c-...",
  "expense_transaction_id": "txn_abc123",
  "income_transaction_id": "txn_def456",
  "amount": 65.00,
  "notes": "Partial reimbursement for dinner",
  "created_by_user_id": 7,
  "created_at": "2026-05-09T14:22:00Z",
  "updated_at": "2026-05-09T14:22:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | string (UUID) | Unique identifier of the reimbursement link |
| `expense_transaction_id` | string | ID of the expense transaction being reimbursed |
| `income_transaction_id` | string | ID of the income transaction doing the reimbursing |
| `amount` | number (decimal) | Reimbursement amount — must be > 0 |
| `notes` | string \| null | Optional human-readable note |
| `created_by_user_id` | integer \| null | User who created this link |
| `created_at` | ISO 8601 datetime | Creation timestamp |
| `updated_at` | ISO 8601 datetime | Last update timestamp |

---

## Endpoints

### 1. Create Reimbursement Link

```
POST /transactions/reimbursements
```

Links an income transaction as a (partial) reimbursement of an expense transaction.

#### Request Body

```json
{
  "expense_transaction_id": "txn_abc123",
  "income_transaction_id": "txn_def456",
  "amount": 65.00,
  "notes": "Partial reimbursement for dinner"
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `expense_transaction_id` | string | ✅ | Must be a transaction with `type="expense"` in your household. Cannot be a split-parent row. |
| `income_transaction_id` | string | ✅ | Must be a transaction with `type="income"` in your household. |
| `amount` | number | ✅ | Must be `> 0`. Cannot exceed the expense amount. Cannot exceed the income transaction's remaining unallocated capacity. |
| `notes` | string | ❌ | Free text, max database TEXT length. |

#### Success Response — `201 Created`

Returns the created `TransactionReimbursement` object.

```json
{
  "id": "3f1e2d4c-8b5a-4f2e-9c3d-1a2b3c4d5e6f",
  "expense_transaction_id": "txn_abc123",
  "income_transaction_id": "txn_def456",
  "amount": 65.00,
  "notes": "Partial reimbursement for dinner",
  "created_by_user_id": 7,
  "created_at": "2026-05-09T14:22:00Z",
  "updated_at": "2026-05-09T14:22:00Z"
}
```

#### Error Responses

| Status | `error` field | Meaning |
|---|---|---|
| `400` | — | Malformed request body / missing required field |
| `404` | — | One or both transaction IDs not found, or they belong to a different household |
| `409` | `duplicate_link` | A reimbursement link already exists between this exact `(expense_id, income_id)` pair. Update the existing link with PUT instead. |
| `422` | `invalid_directionality` | `expense_transaction_id` is not type `"expense"`, or `income_transaction_id` is not type `"income"` (transfers are not allowed on either side) |
| `422` | `split_parent_not_allowed` | The expense transaction is a split-parent ghost row. Link individual split children instead. |
| `422` | `over_reimbursement` | The requested amount would exceed either the income transaction's capacity or the expense transaction's total amount. See body for details. |

##### `over_reimbursement` Error Body

```json
{
  "error": "over_reimbursement",
  "message": "This would over-reimburse the expense by $12.50",
  "current_net": 87.50,
  "max_allowed": 87.50
}
```

| Field | Meaning |
|---|---|
| `message` | Human-readable description |
| `current_net` | How much of the expense is currently un-reimbursed |
| `max_allowed` | Maximum amount you may submit in a new request |
| `allocated_amount` | (income capacity errors only) — how much of the income is already allocated |

---

### 2. Update Reimbursement Link

```
PUT /transactions/reimbursements/{reimbursement_id}
```

Update the `amount` and/or `notes` on an existing reimbursement link. Only these two fields can be modified. To change which transactions are linked, delete and recreate.

#### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `reimbursement_id` | string (UUID) | The `id` of the reimbursement to update |

#### Request Body

All fields are optional — send only what you want to change.

```json
{
  "amount": 80.00,
  "notes": "Updated — paid in full"
}
```

| Field | Type | Constraints |
|---|---|---|
| `amount` | number | Must be `> 0`. Re-validated against capacity rules. |
| `notes` | string \| null | Free text |

#### Success Response — `200 OK`

Returns the updated `TransactionReimbursement` object.

#### Error Responses

| Status | Meaning |
|---|---|
| `404` | Reimbursement not found, or the linked transactions no longer belong to your household |
| `422` | New amount would violate capacity rules — same `over_reimbursement` body as create |

---

### 3. Delete Reimbursement Link

```
DELETE /transactions/reimbursements/{reimbursement_id}
```

Permanently removes a reimbursement link. Budget and report queries are dynamic, so they automatically reflect the removal with no additional action required.

#### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `reimbursement_id` | string (UUID) | The `id` of the reimbursement to delete |

#### Success Response — `204 No Content`

Empty body.

#### Error Responses

| Status | Meaning |
|---|---|
| `404` | Reimbursement not found or belongs to a different household |

---

### 4. List Reimbursements for a Transaction

```
GET /transactions/{transaction_id}/reimbursements
```

Returns all reimbursement links where the given transaction appears on either side (as the expense **or** as the income). Also returns allocation totals so you can render a capacity indicator without a second request.

#### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `transaction_id` | string | The transaction to query. Works for both expense and income transactions. |

#### Success Response — `200 OK`

```json
{
  "transaction_id": "txn_abc123",
  "transaction_amount": 100.00,
  "allocated_amount": 65.00,
  "remaining_amount": 35.00,
  "reimbursements": [
    {
      "id": "3f1e2d4c-...",
      "expense_transaction_id": "txn_abc123",
      "income_transaction_id": "txn_def456",
      "amount": 65.00,
      "notes": "Partial reimbursement for dinner",
      "created_by_user_id": 7,
      "created_at": "2026-05-09T14:22:00Z",
      "updated_at": "2026-05-09T14:22:00Z"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `transaction_id` | string | The queried transaction's ID |
| `transaction_amount` | number | The transaction's full amount (always positive) |
| `allocated_amount` | number | Sum of all linked reimbursement amounts |
| `remaining_amount` | number | `transaction_amount - allocated_amount` (≥ 0) |
| `reimbursements` | array | All reimbursement link objects, ordered by `created_at` ascending |

#### Error Responses

| Status | Meaning |
|---|---|
| `404` | Transaction not found or belongs to a different household |

---

## Validation Rules Summary

The server enforces all five rules **atomically** with row-level locks. If any rule fails, the entire operation is rolled back.

| Rule | Check | Error |
|---|---|---|
| **1 – Directionality** | `expense_transaction.type == "expense"` AND `income_transaction.type == "income"` | `422 invalid_directionality` |
| **2 – Ghost parent** | `expense_transaction.is_split_parent == false` | `422 split_parent_not_allowed` |
| **3 – Tenant isolation** | Both transactions must have `household_id == current_user.household_id` | `404` |
| **4 – Income capacity** | `(existing allocations on this income txn) + new_amount ≤ income_transaction.amount` | `422 over_reimbursement` |
| **5 – Expense over-reimbursement** | `(existing reimbursements on this expense txn) + new_amount ≤ expense_transaction.amount` | `422 over_reimbursement` |

---

## Typical UI Flows

### Flow A — Link a Full Reimbursement

1. User opens an expense transaction and taps "Mark as Reimbursed".
2. User selects (or the app auto-detects) an income transaction to use as the source.
3. Client calls `GET /transactions/{income_id}/reimbursements` to determine the income transaction's `remaining_amount`.
4. Client pre-fills `amount` with `min(expense.amount, income.remaining_amount)`.
5. Client calls `POST /transactions/reimbursements`.
6. On success, show the updated net amount on the expense card.

### Flow B — Partial Reimbursement

Same as Flow A but the user edits the `amount` to a value less than the expense total. The expense card should show:

```
Expense:      $100.00
Reimbursed:   $65.00
Net cost:     $35.00
```

### Flow C — Multiple Partial Reimbursements

An expense can have multiple reimbursement links (e.g. two colleagues each paying back part of a shared bill):

1. Call `POST /transactions/reimbursements` once for each income transaction.
2. Query `GET /transactions/{expense_id}/reimbursements` to get the running totals.

### Flow D — Edit Reimbursement Amount

1. User opens the reimbursement detail screen.
2. User changes the amount.
3. Client calls `PUT /transactions/reimbursements/{reimbursement_id}` with the new `amount`.
4. Handle `422 over_reimbursement` if the new amount exceeds capacity — display `max_allowed` to the user.

### Flow E — Unlink a Reimbursement

1. Client calls `DELETE /transactions/reimbursements/{reimbursement_id}`.
2. On `204`, update the local state to remove the link and recalculate the expense net amount from `allocated_amount` returned by the list endpoint.

---

## Budget & Reporting Behavior

You do **not** need to call any extra endpoint after linking or unlinking. Budget and spending report queries are fully dynamic:

- **Net spend per category** = gross expense − total reimbursements linked to expenses in that category
- **Net income** = gross income − reimbursements allocated to income transactions in the period
- Changing the `category_id` of an expense automatically moves its reimbursement offset to the new category in reports — no extra action needed
- Deleting a transaction cascades to its reimbursement links automatically

### Amount Convention in Reports

All financial figures in reports use the same `Decimal` format as the `amount` fields above. The client should display:

```
Net spend = gross_expense - total_reimbursed
```

Both values are positive numbers. The UI should subtract, not add.

---

## Common Mistakes to Avoid

| Mistake | Correct Approach |
|---|---|
| Sending `amount` in integer cents (e.g. `6500`) | Send decimal dollars (e.g. `65.00`) to match `transactions.amount` |
| Using a `type="transfer"` transaction as either side | Only `type="expense"` (payer) and `type="income"` (receiver) are valid |
| Trying to reimburse a split-parent row | Link the individual child splits (the real line items), not the parent ghost row |
| Creating a second link between the same pair | Use `PUT` to update the existing link; creating a duplicate returns `409` |
| Assuming the full expense amount is always available | Call `GET /transactions/{expense_id}/reimbursements` first to check `remaining_amount` |

---

## Authentication

All four endpoints use the existing JWT Bearer authentication middleware. Include the access token on every request:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Access tokens expire after 15 minutes. Use the refresh token endpoint (`POST /auth/refresh`) to obtain a new one without re-login.

---

## cURL Examples

### Create a full reimbursement
```bash
curl -X POST https://<host>/api/transactions/reimbursements \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "expense_transaction_id": "txn_abc123",
    "income_transaction_id": "txn_def456",
    "amount": 100.00,
    "notes": "Full reimbursement"
  }'
```

### List reimbursements for an expense
```bash
curl https://<host>/api/transactions/txn_abc123/reimbursements \
  -H "Authorization: Bearer <token>"
```

### Update the amount
```bash
curl -X PUT https://<host>/api/transactions/reimbursements/3f1e2d4c-... \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"amount": 75.00}'
```

### Delete a link
```bash
curl -X DELETE https://<host>/api/transactions/reimbursements/3f1e2d4c-... \
  -H "Authorization: Bearer <token>"
```
