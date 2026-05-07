# Backend Implementation Summary: Net Worth History Feature

## Overview
All backend changes required for the net worth history feature have been successfully implemented. The implementation follows the existing project patterns and integrates seamlessly with the current codebase.

## Files Created

### 1. **app/models/account_snapshot.py**
New database model for storing daily net worth snapshots.

**Schema:**
- `id` (Integer, Primary Key)
- `user_id` (Integer) - Links to user
- `snapshot_date` (Date) - The date of the snapshot
- `net_worth` (Numeric) - Net worth value (assets - liabilities)
- `total_assets` (Numeric) - Sum of all positive balances
- `total_liabilities` (Numeric) - Sum of all negative balances
- `created_at` (DateTime) - Record creation timestamp
- `updated_at` (DateTime) - Record update timestamp
- **Unique Constraint:** `(user_id, snapshot_date)` - Ensures one snapshot per user per day

### 2. **app/schemas/account_snapshot.py**
Pydantic schemas for API request/response serialization.

**Classes:**
- `NetWorthHistoryEntry` - Single history point (date + net_worth)
- `NetWorthHistory` - Collection of history entries
- `AccountSnapshotBase` - Base snapshot data
- `AccountSnapshot` - Full snapshot with metadata

### 3. **app/services/net_worth.py**
Business logic for net worth calculations and snapshot management.

**Functions:**
- `calculate_net_worth(db, user_id)` - Calculates current net worth from all accounts
  - Returns: (net_worth, total_assets, total_liabilities)
  - Properly handles credit cards as liabilities
  - Supports mixed positive/negative balances
  
- `create_snapshot(db, user_id, snapshot_date)` - Creates or updates daily snapshot
  - Upserts logic: creates if new, updates if exists for that date
  - Calls `calculate_net_worth()` internally
  
- `get_net_worth_history(db, user_id, period)` - Retrieves historical net worth
  - Supports periods: `1week`, `1month`, `3months`, `6months`, `1year`
  - Returns sorted list of `NetWorthHistoryEntry` objects
  - Defaults to 1 month if invalid period provided

## Files Modified

### 1. **app/routers/accounts.py**
Added two new API endpoints to the accounts router.

**New Endpoints:**

#### `GET /api/accounts/net-worth-history`
- **Query Parameters:**
  - `period` (string, default: "1month") - Time period filter
- **Response:** List of `NetWorthHistoryEntry` objects
  ```json
  [
    {"date": "2026-11-07", "net_worth": 663401.45},
    {"date": "2026-11-08", "net_worth": 665234.20},
    ...
  ]
  ```
- **Implementation:** Uses `get_net_worth_history()` service
- **Note:** Currently uses hardcoded `user_id = 1` (to be replaced with auth context)

#### `POST /api/accounts/snapshots/create`
- **Purpose:** Trigger snapshot creation for the current day
- **Response:** Created/updated snapshot details
  ```json
  {
    "id": 42,
    "user_id": 1,
    "snapshot_date": "2026-11-08",
    "net_worth": 665234.20,
    "total_assets": 666481.70,
    "total_liabilities": 1247.50
  }
  ```
- **Implementation:** Calls `create_snapshot()` service
- **Use Case:** Called by scheduled tasks (cron, Lambda, Cloud Scheduler, etc.)

### 2. **app/main.py**
Updated to import and seed account snapshots on startup.

**Changes:**
- Imported `seed_account_snapshots` from seeder
- Added `await seed_account_snapshots()` to lifespan startup

### 3. **app/services/seeder.py**
Added snapshot seeding for demo/testing purposes.

**New Function:**
- `seed_account_snapshots()` - Creates 31 days of sample snapshots
  - Generates data from 30 days ago to today
  - Base net worth: $45,671.17 with gradual growth
  - Adds daily fluctuations for realistic chart visualization
  - Only runs if no snapshots exist (idempotent)

### 4. **app/models/__init__.py**
Updated to export `AccountSnapshot` model.

## Database Migration

The `AccountSnapshot` table is automatically created on first startup via SQLAlchemy's `Base.metadata.create_all()` in the lifespan context manager.

**Table Creation SQL (automatically generated):**
```sql
CREATE TABLE account_snapshots (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    snapshot_date DATE NOT NULL,
    net_worth NUMERIC(19, 4) NOT NULL,
    total_assets NUMERIC(19, 4) NOT NULL,
    total_liabilities NUMERIC(19, 4) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(user_id, snapshot_date)
);

CREATE INDEX idx_account_snapshots_user_id ON account_snapshots(user_id);
CREATE INDEX idx_account_snapshots_snapshot_date ON account_snapshots(snapshot_date);
```

## Integration Points

### Data Flow
1. **Current Accounts** - Existing `/api/accounts` endpoint (no changes)
2. **Snapshot Calculation** - New service logic in `net_worth.py`
3. **Historical Data** - Retrieved via new `/api/accounts/net-worth-history` endpoint
4. **Frontend Display** - Charts and summaries use the returned data

### Account Type Handling
The net worth calculation properly categorizes accounts:
- **Assets:** checking, savings, investment, cash accounts with positive balance
- **Liabilities:** credit_card accounts (negative balance = money owed)
- **Formula:** `net_worth = total_assets - total_liabilities`

## Future Enhancements

### 1. **Authentication Integration**
Replace hardcoded `user_id = 1` with actual auth context:
```python
# In routes
from app.core.auth import get_current_user
async def endpoint(current_user = Depends(get_current_user)):
    user_id = current_user.id
```

### 2. **Scheduled Daily Snapshots**
Add APScheduler or implement external scheduling:
```python
# Option A: APScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
scheduler = AsyncIOScheduler()
scheduler.add_job(create_daily_snapshots_for_all_users, 'cron', hour=23, minute=59)

# Option B: External (cron, Lambda, Cloud Scheduler)
# Call POST /api/accounts/snapshots/create daily
```

### 3. **Batch Operations**
Add endpoint to create snapshots for all users:
```python
@router.post("/admin/snapshots/create-all")
async def create_snapshots_for_all_users(db: AsyncSession):
    # Find all users and create snapshots
    pass
```

### 4. **Snapshot Retention Policy**
Consider adding cleanup for old snapshots or archival:
```python
# Delete snapshots older than 1 year
async def cleanup_old_snapshots(db: AsyncSession):
    pass
```

## Testing

### Manual Testing
```bash
# Create today's snapshot
curl -X POST http://localhost:8000/api/accounts/snapshots/create

# Get 1-month history
curl http://localhost:8000/api/accounts/net-worth-history?period=1month

# Get 1-year history
curl http://localhost:8000/api/accounts/net-worth-history?period=1year
```

### Expected Response (1 month, 31 seed snapshots)
```json
[
  {"date": "2026-10-08", "net_worth": 45671.17},
  {"date": "2026-10-09", "net_worth": 46338.84},
  ...
  {"date": "2026-11-07", "net_worth": 65671.17}
]
```

## Error Handling

- **Invalid Period:** Defaults to "1month" without error
- **No Snapshots:** Returns empty list
- **Missing User:** Returns empty list (future: 404 with proper auth)
- **Database Errors:** Handled by existing exception handlers in `main.py`

## Performance Considerations

1. **Database Indexes:** Added on `user_id` and `snapshot_date` for fast queries
2. **Unique Constraint:** Prevents duplicate daily snapshots
3. **Query Optimization:** Single query with date range filtering
4. **Response Size:** Typical 30-day history ~3KB JSON

## Compliance with Requirements

✅ **New API Endpoint:** `GET /api/accounts/net-worth-history` with period filtering
✅ **New Database Table:** `account_snapshots` with all specified fields
✅ **Unique Constraint:** `(user_id, snapshot_date)` implemented
✅ **Daily Snapshot Job:** `POST /api/accounts/snapshots/create` for scheduled tasks
✅ **Response Format:** `[{date: "2026-11-07", net_worth: 663401.45}, ...]`
✅ **Period Support:** 1week, 1month, 3months, 6months, 1year
✅ **Asset/Liability Calculation:** Properly categorizes account types
✅ **Seed Data:** 31 days of demo snapshots for testing

## No Breaking Changes

- Existing `/api/accounts` endpoint unchanged
- All new code is isolated to new files/endpoints
- Database table creation is automatic and non-destructive
- Fully backward compatible with frontend (except for the new chart component usage)
