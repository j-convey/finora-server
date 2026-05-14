# Database Reset Endpoint — Client Implementation Guide

## Endpoint Details

**Method:** `POST`  
**Path:** `/api/admin/reset-database`  
**Auth:** None (currently unprotected — **requires auth in production**)  
**Body:** None — this is a POST with no request payload

## Response

**Status:** `200 OK`

**Body:**
```json
{
  "ok": true,
  "message": "Database reset complete. All data deleted.",
  "deleted_records": {
    "account_snapshots": 0,
    "transactions": 0,
    "accounts": 0,
    "budgets": 0,
    "categories": 13,
    "simplefin_config": 0
  }
}
```

The `deleted_records` object shows how many rows were deleted from each table.

## Purpose

Clears all data from the database for a fresh start:
- Account snapshots
- Transactions
- Accounts
- Budgets
- Categories (will be re-seeded on next server restart)
- SimpleFIN config

This is useful during development/testing. Use with caution — **this is an intentionally destructive operation with no undo.**

## Usage Example

**cURL:**
```bash
curl -X POST http://localhost:8000/api/admin/reset-database
```

**Dart/Flutter:**
```dart
final response = await http.post(
  Uri.parse('http://localhost:8000/api/admin/reset-database'),
);

if (response.statusCode == 200) {
  final data = jsonDecode(response.body);
  print('Database reset: ${data["message"]}');
  print('Deleted: ${data["deleted_records"]}');
} else {
  print('Error: ${response.statusCode}');
}
```

**JavaScript/TypeScript:**
```javascript
const response = await fetch('http://localhost:8000/api/admin/reset-database', {
  method: 'POST',
});

const data = await response.json();
console.log('Database reset:', data.message);
console.log('Deleted records:', data.deleted_records);
```

## Notes

- **No confirmation required** — the endpoint will delete immediately. Consider adding a confirmation dialog in the UI before calling.
- **Idempotent** — calling it multiple times is safe; subsequent calls will delete 0 records if the database is already empty.
- **Re-seeding** — categories will be automatically re-seeded on the next server restart (or can be manually seeded via `seed_categories()`).
- **Production** — this endpoint should be protected behind authentication/authorization in production. The current implementation has no protection.

## Optional Future Enhancement

Add a query parameter for confirmation:
```
POST /api/admin/reset-database?confirm=true
```
This would require the client to explicitly opt-in, reducing accidental resets.
