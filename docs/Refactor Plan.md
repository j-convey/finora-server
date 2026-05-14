**Hey Jordan,**

**Phase 1 is now complete — excellent work from the backend dev.**  


---

# **Finora Backend – God-Tier Refactor Master Plan**  
**Version:** 1.1 (May 13, 2026)  
**Status:** Logging complete ✅ | Transactions Repository pilot complete ✅ | **Reimbursements Repository complete ✅**  
**Owner:** Jordan + Grok (Backend Architect)  
**Goal:** OCD-level separation of concerns using Clean Architecture + vertical feature slices while keeping the app always healthy and delivering value at every step.

### 1. Current State
- Structured logging (`core/logging.py` + middleware) is live and god-tier.
- `app/repositories/` folder exists with `BaseRepository` (async) and two fully wired repositories:
  - `TransactionRepository` (3 methods)
  - `ReimbursementRepository` (4 methods: `get_by_id`, `list_by_transaction`, `sum_allocated_to_income`, `sum_reimbursed_from_expense`)
- All raw reimbursement queries have been removed from `app/routers/transactions.py`.
- **Important clarification:** Reimbursement logic lives directly in the `transactions.py` router (no separate `reimbursement_service.py`).
- Tests and `.md` files remain at root (no moves yet).
- Everything is async-correct and container-healthy.

### 2. Guiding Principles (non-negotiable)
- **Incremental & always-green**: One small, working change per PR. Never commit dead code or stubs.
- **Deliver value immediately**: Every step must make services/routers thinner or improve testability.
- **Async-first**: Always use `AsyncSession`. No sync `Session` ever.
- **Respect existing structure**: No moving tests, docs, or `.md` files until Phase 5.
- **Repository owns data access**: Routers/services only do business logic + orchestration.
- **Dependency injection**: Use FastAPI `Depends()` for repositories.
- **Router stays thin**: HTTP exceptions and auth checks stay in routers.
- **One domain at a time**: Finish the slice (repo + router/service updates) before moving to the next domain.

### 3. High-Level Roadmap (5 Phases)

| Phase | Focus | Estimated Effort | Value Delivered | Status |
|-------|-------|------------------|-----------------|--------|
| **1** | Reimbursements (in transactions router) | 1 day | Core finance slice cleaned | **✅ Complete** |
| **2** | Budgets + Categories | 2–3 days | Major domain extracted | **Next** |
| **3** | Net-worth, Account Snapshot, User/Household | 3–4 days | 80% of business logic cleaned | Planned |
| **4** | Full Clean Architecture folder restructure | 2–3 days | Final OCD organization | After Phase 3 |
| **5** | Tests, docs, scripts, CI polish | 1–2 days | Production readiness | Final |

### 4. Detailed Next Steps (What to Implement Now)

#### **Phase 2 – Budgets + Categories (Immediate Next Step)**
**Goal:** Extract `BudgetRepository` and `CategoryRepository` and wire them into their respective routers/services (or wherever the logic currently lives).

**Step-by-step for backend dev:**
1. Create `app/repositories/budget_repository.py` (copy exact pattern from `transaction_repository.py` and `reimbursement_repository.py`).
2. Create `app/repositories/category_repository.py`.
3. Extract **all** remaining raw SQLAlchemy queries from the budget/category logic into the new repos (common methods: `get_by_id_for_household`, `list_by_household`, `create`, `update`, `delete`, any aggregate queries, etc.).
4. Update the relevant router files (`routers/budgets.py` and `routers/categories.py`) to inject the repositories via `Depends()` and replace all inline queries.
5. Run full test suite + manual smoke test of budget and category endpoints.
6. Verify: No raw DB queries remain in the budget/category routers/services.

**Success criteria:**
- All budget and category DB access goes through the new repositories.
- App remains healthy.
- Pattern is now battle-tested on three domains.

Once Phase 2 is complete, reply with a summary (like you did for Phase 1) and I’ll immediately provide the exact files/code for **Phase 3**.

#### **Phase 3 – Remaining Core Domains**
- Net-worth service + account snapshot
- User / Household
- Account
- SimpleFin integration (move into `infrastructure/integrations/simplefin/` as part of this phase)

#### **Phase 4 – Full Folder Restructure (Only After Phase 3)**
Only now do we perform the clean moves:
- `models/` → `infrastructure/models/`
- `services/` → `application/`
- `routers/` + `schemas/` → `api/v1/`
- Create `domain/` for pure Pydantic business entities
- Update imports in one controlled pass (tests will catch any breakage)

#### **Phase 5 – Final Polish**
- Move remaining docs to `docs/` (with any necessary redirects)
- Update any CI paths
- Add repository unit tests
- Optional: Add PII redaction processor to logging

### 5. General Rules for Every Step
- Always include the updated router/service + repo in the **same PR**.
- Use the exact same style and patterns established in the transaction and reimbursement repositories.
- Prefer `request.state` for user/household context (already in middleware).
- Update `get_logger(__name__)` calls as you touch files.
- After every change: `docker compose restart server` + run all tests + smoke test affected endpoints.
- If anything feels risky → pause and ask.

---
