# Finora Client: Demo Mode Integration Guide

This document provides exhaustive instructions for updating the client application (e.g., Flutter, React, Vue) to support the new "Demo Mode" feature backed by the Finora Server.

## 1. Concept Overview

The backend has implemented a highly scalable **schema-isolated Demo Mode**. This means:
*   There is no separate URL or separate user account required for Demo Mode.
*   The backend contains a complete parallel database schema (`demo`) populated with rich seed data.
*   **The single mechanism to access this data is the `X-Demo-Mode` HTTP Header.**
*   When a client sends `X-Demo-Mode: true` with *any* API request, the backend seamlessly routes that request to the demo database instead of the user's real database.
*   When the client omits the header or sends `X-Demo-Mode: false`, requests route normally to the user's main database.

## 2. API Endpoints for Toggling State

The backend provides three new, rate-limited endpoints for managing demo mode state:

*   `POST /api/demo/enable`: A symbolic endpoint that the client can call when the user clicks "Enter Demo Mode". It returns a success message.
*   `POST /api/demo/disable`: A symbolic endpoint that the client can call when the user clicks "Exit Demo Mode".
*   `GET /api/demo/status`: A health-check endpoint to verify if demo mode is ready and seeded on the server.

**Important Note:** Calling `/api/demo/enable` *does not* magically put the user's session into demo mode on the server. The server is completely stateless regarding demo mode. The endpoint exists primarily for analytics, rate limiting, and future backend hooks. **The client is 100% responsible for attaching the header to subsequent requests.**

## 3. Client Implementation Requirements

To correctly implement Demo Mode, the client must fulfill the following requirements:

### 3.1. State Management (Global Context)

The client must maintain a global state variable (e.g., `isDemoModeActive`).
*   This state should ideally be persisted locally (e.g., `localStorage`, `SharedPreferences`, `SecureStorage`) so that if the user refreshes the page or restarts the app, they remain in their selected mode.

### 3.2. HTTP Interceptor / HTTP Client Modification

You must update the global HTTP client or add an Interceptor that inspects `isDemoModeActive` before sending *every* request to the Finora API.

**Example Interceptor Logic:**
```javascript
// Pseudo-code for an Axios or Fetch interceptor
httpClient.interceptors.request.use((config) => {
  const isDemoMode = appState.get('isDemoModeActive');

  if (isDemoMode) {
    config.headers['X-Demo-Mode'] = 'true';
  } else {
    // Explicitly remove it just in case it was cached/attached elsewhere
    delete config.headers['X-Demo-Mode'];
  }

  return config;
});
```

### 3.3. Complete Data Refetching (Cache Invalidation)

This is the most critical requirement for a smooth user experience.

When the user toggles Demo Mode (either entering or exiting), the underlying data context changes completely. The client must *immediately*:

1.  **Clear all local application caches:** Purge any cached API responses for accounts, transactions, budgets, subscriptions, and net worth history. (e.g., `queryClient.clear()` in React Query, or clearing your Redux store).
2.  **Refetch core data:** Trigger a re-fetch of the primary data needed for the current screen. Because the HTTP interceptor (from 3.2) is now active, these refetch requests will automatically hit the correct database schema and populate the UI with the appropriate data (either the Demo seed data or the user's real data).

### 3.4. Unauthenticated Access (Pre-Login Demo)

Demo Mode is specifically designed to allow users to test the application *before* registering an account.

*   The `X-Demo-Mode: true` header works even on endpoints that do not require a JWT Authorization header.
*   The client UI should provide a "Try Demo" button on the Login/Registration screen.
*   Clicking this button should set `isDemoModeActive = true`, and navigate the user into the main application dashboard, bypassing the login requirement.
*   **Security check:** The client must ensure that when `isDemoModeActive` is true, any attempts to access user profile settings or change passwords gracefully degrade or are hidden, as there is no real user account backing the session.

### 3.5. UI Indication

When `isDemoModeActive` is true, the client UI *must* prominently display a warning or banner.

*   **Requirement:** A persistent banner at the top or bottom of the screen stating: "Demo Mode. Changes are not saved to your account."
*   **Actionable Exit:** The banner should include a clear "Exit Demo" button. Clicking this button should:
    1. Set `isDemoModeActive = false`.
    2. Call `POST /api/demo/disable` (optional but recommended).
    3. Clear caches and refetch data (see 3.3).
    4. If the user was unauthenticated, redirect them back to the Login screen.

## 4. Summary of Developer Workflow (Client)

1.  User clicks "Try Demo" on login screen.
2.  Client sets `localStorage.setItem('demo_mode', 'true')`.
3.  Client calls `POST /api/demo/enable`.
4.  Client navigates to Dashboard.
5.  Dashboard component mounts, fetches `/api/accounts`.
6.  Interceptor sees local storage flag, injects `X-Demo-Mode: true` header.
7.  Server receives header, routes DB query to `demo` schema.
8.  Server returns seeded demo accounts.
9.  Dashboard renders seeded demo accounts.
10. User clicks "Exit Demo" on the persistent banner.
11. Client sets `localStorage.removeItem('demo_mode')`.
12. Client clears all frontend cache state.
13. Client redirects to Login screen (since they have no JWT).
