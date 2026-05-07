# Client Auth Migration Guide

This document covers every change the Flutter client needs to make as a result of the authentication implementation. All changes are **breaking** — the app will not work against the new server without them.

---

## 1. Overview of What Changed

| Area | Before | After |
|---|---|---|
| Auth | No auth required on any endpoint | All endpoints require a Bearer JWT |
| User identity | `user_id=1` hardcoded | Derived from the JWT (server-side) |
| Household | No concept | All financial data belongs to a shared household |
| `subscriptions` responses | Had `user_id` field | Now has `household_id` field |
| `account_snapshots` responses | Had `user_id` field | Now has `household_id` field |
| Net-worth / snapshot endpoints | No auth | Require JWT |
| Admin endpoints | No auth | Require JWT |
| New endpoints | — | `/api/auth/*`, `/api/users/*` |

---

## 2. Token Storage

Store both tokens securely after login/register. On Flutter use `flutter_secure_storage`.

```dart
// Store after login or register
await storage.write(key: 'access_token', value: response.access_token);
await storage.write(key: 'refresh_token', value: response.refresh_token);
```

**Never** store tokens in `SharedPreferences` — it is not encrypted.

---

## 3. HTTP Client — Add Auth Header

Every API request (except register, login, and avatar serving) must include:

```
Authorization: Bearer <access_token>
```

The recommended pattern is an `http` interceptor / Dio interceptor that:
1. Reads the stored access token and injects the header.
2. On `401` response, calls `/api/auth/refresh` once.
3. If refresh succeeds, retries the original request with the new token.
4. If refresh fails (401), clears tokens and redirects to the login screen.

```dart
// Dio interceptor sketch
class AuthInterceptor extends Interceptor {
  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    final token = await storage.read(key: 'access_token');
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    super.onRequest(options, handler);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    if (err.response?.statusCode == 401) {
      final refreshed = await _tryRefresh();
      if (refreshed) {
        // Retry original request with new token
        return handler.resolve(await _retry(err.requestOptions));
      }
      // Refresh failed — force logout
      await _clearTokensAndNavigateToLogin();
    }
    super.onError(err, handler);
  }
}
```

---

## 4. New Auth Endpoints

Base path: `/api/auth`

---

### 4.1 `POST /api/auth/register` — First-run bootstrap

**Use only on first launch when no account exists.** The server returns `409 Conflict` after the first account is created — this endpoint is the setup wizard screen, not a sign-up flow.

**Request:**
```json
{
  "email": "jordan@example.com",
  "password": "supersecret",
  "full_name": "Jordan"        // optional
}
```

**Response `201`:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "2_cAUM...",
  "token_type": "bearer"
}
```

**Response `409`** — server already has users, show login screen instead:
```json
{ "error": "Registration is closed. Ask the household owner to create an account for you via POST /api/users." }
```

**Client flow suggestion:**
- On app launch, try `GET /api/users/me` with no token.
- If `401` and no stored token → check if any user exists by attempting register with empty fields (or just show a "First Setup" screen with register form).
- A cleaner approach: on first launch with no stored tokens, attempt `POST /api/auth/register`. If `409` → show login screen. If `201` → show main app.

---

### 4.2 `POST /api/auth/login`

**Request:**
```json
{
  "email": "jordan@example.com",
  "password": "supersecret"
}
```

**Response `200`:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "LFjz...",
  "token_type": "bearer"
}
```

**Response `401`:**
```json
{ "error": "Invalid email or password" }
```

**Response `403`:**
```json
{ "error": "Account is disabled" }
```

---

### 4.3 `POST /api/auth/refresh` — Rotate tokens

Call this when an access token expires (when you receive a `401` on any endpoint).

**Request:**
```json
{ "refresh_token": "LFjz..." }
```

**Response `200`:**
```json
{
  "access_token": "eyJ...",   // new
  "refresh_token": "xK9p...", // new — replace old one immediately
  "token_type": "bearer"
}
```

**Response `401`** — session expired, must re-login:
```json
{ "error": "Refresh token is invalid or expired" }
```

> **Important:** The old refresh token is invalidated immediately. Store the new one before making any other requests. If two requests try to refresh at the same time, one will fail — use a lock/mutex around the refresh call.

---

### 4.4 `POST /api/auth/logout`

Send the current refresh token so the server invalidates it. The client must also clear both stored tokens locally, regardless of the server response.

**Request:**
```json
{ "refresh_token": "LFjz..." }
```

**Response:** `204 No Content`

```dart
Future<void> logout() async {
  final refreshToken = await storage.read(key: 'refresh_token');
  if (refreshToken != null) {
    // Best-effort — don't block UI on network failure
    unawaited(apiClient.post('/api/auth/logout', data: {'refresh_token': refreshToken}));
  }
  await storage.delete(key: 'access_token');
  await storage.delete(key: 'refresh_token');
  // Navigate to login
}
```

---

## 5. New User Endpoints

Base path: `/api/users` — all require `Authorization` header.

---

### 5.1 `GET /api/users/me` — Current user profile

```json
{
  "id": 1,
  "household_id": 2,
  "email": "jordan@example.com",
  "full_name": "Jordan",
  "profile_picture_url": "/api/users/1/avatar",  // null if no avatar set
  "is_active": true,
  "created_at": "2026-05-07T17:19:24.106617Z"
}
```

`profile_picture_url` is a server-relative path. Prepend your base URL to load it:
```dart
final avatarUrl = '${baseUrl}${user.profile_picture_url}';
// e.g. http://192.168.1.100:8080/api/users/1/avatar
```

---

### 5.2 `PATCH /api/users/me` — Update profile

**Request** (all fields optional — only include what's changing):
```json
{
  "full_name": "Jordan Convey",
  "email": "new@example.com"
}
```

**Response `200`:** Same shape as `/users/me`.

**Response `409`:** Email already taken by another account.

---

### 5.3 `POST /api/users/me/avatar` — Upload profile picture

Send as `multipart/form-data`. Accepted formats: JPEG, PNG, WebP.

```dart
final formData = FormData.fromMap({
  'file': await MultipartFile.fromFile(
    imagePath,
    contentType: DioMediaType('image', 'jpeg'),
  ),
});
await dio.post('/api/users/me/avatar', data: formData);
```

**Response `200`:** Updated user object — `profile_picture_url` will now be set.

**Response `400`:** Wrong content type.

---

### 5.4 `GET /api/users/{id}/avatar` — Serve avatar

No auth required. Use `profile_picture_url` from the user object directly as an image URL.

```dart
Image.network('${baseUrl}/api/users/${user.id}/avatar')
```

Returns `404` if no avatar is set or the file is missing.

---

### 5.5 `GET /api/users` — List household members

Returns all users sharing the same household (i.e., both you and your spouse).

```json
[
  { "id": 1, "household_id": 2, "email": "jordan@example.com", "full_name": "Jordan", ... },
  { "id": 2, "household_id": 2, "email": "spouse@example.com", "full_name": "Spouse", ... }
]
```

---

### 5.6 `POST /api/users` — Add household member

The logged-in user creates an account for their spouse. The new user is placed in the same household.

**Request:**
```json
{
  "email": "spouse@example.com",
  "password": "theirpassword",
  "full_name": "Spouse Name"    // optional
}
```

**Response `201`:** User object.
**Response `409`:** Email already registered.

---

### 5.7 `DELETE /api/users/{id}` — Remove a household member

Cannot delete yourself (`400`). Cannot delete users from other households (`404`).

**Response:** `204 No Content`

---

## 6. Breaking Changes to Existing Endpoints

### All existing endpoints now require `Authorization: Bearer <token>`

Previously unauthenticated endpoints that now return `401` without a token:

- `GET /api/accounts`
- `GET /api/accounts/net-worth-history`
- `POST /api/accounts/snapshots/create`
- `GET /api/transactions`
- `PATCH /api/transactions/{id}`
- `GET /api/budgets`
- `POST /api/budgets`
- `PATCH /api/budgets/{id}`
- `DELETE /api/budgets/{id}`
- `GET /api/categories`
- `GET /api/subscriptions`
- `POST /api/subscriptions`
- `GET /api/subscriptions/{id}`
- `PATCH /api/subscriptions/{id}`
- `DELETE /api/subscriptions/{id}`
- `POST /api/subscriptions/{id}/link/{tx_id}`
- `DELETE /api/subscriptions/{id}/link/{tx_id}`
- `POST /api/admin/reset-database`
- `GET /api/admin/export-database`
- `POST /api/admin/import-database`
- `GET /api/admin/subscriptions/suggestions`
- `POST /api/admin/subscriptions/backfill`
- `GET /api/simplefin/...` (all SimpleFIN endpoints)

> **Exception:** `GET /api/users/{id}/avatar` does NOT require auth (for `Image.network` use).
> `GET /api/v1/health` does NOT require auth.

---

### `user_id` query parameter removed from subscriptions

Previously the client could pass `?user_id=1` on subscription endpoints. That parameter is gone — the user is identified from the JWT.

Remove any `user_id` query params from:
- `GET /api/subscriptions`
- `POST /api/subscriptions`
- `GET /api/subscriptions/{id}`
- `PATCH /api/subscriptions/{id}`
- `DELETE /api/subscriptions/{id}`
- `POST/DELETE /api/subscriptions/{id}/link/{tx_id}`
- `GET /api/admin/subscriptions/suggestions`
- `POST /api/admin/subscriptions/backfill`

---

### `SubscriptionResponse` field rename: `user_id` → `household_id`

Update any Dart model / `fromJson` that reads `user_id` on a subscription:

```dart
// Before
class Subscription {
  final int userId;
  Subscription.fromJson(Map json) : userId = json['user_id'];
}

// After
class Subscription {
  final int householdId;
  Subscription.fromJson(Map json) : householdId = json['household_id'];
}
```

---

### `AccountSnapshot` field rename: `user_id` → `household_id`

Same as above — update any snapshot Dart model that reads `user_id`.

---

### `POST /api/accounts/snapshots/create` response change

The response now contains `household_id` instead of `user_id`:

```json
// Before
{ "id": 5, "user_id": 1, "snapshot_date": "2026-05-07", ... }

// After
{ "id": 5, "household_id": 2, "snapshot_date": "2026-05-07", ... }
```

---

## 7. App Launch Flow

```
App Launch
    │
    ├─ Has stored access_token?
    │       │
    │       ├─ YES → Try GET /api/users/me
    │       │           ├─ 200 → proceed to main app
    │       │           └─ 401 → try refresh (§4.3)
    │       │                       ├─ success → proceed to main app
    │       │                       └─ 401    → clear tokens → Login screen
    │       │
    │       └─ NO → Is this the first launch?
    │                   ├─ YES / unknown → show "First Setup" screen (register)
    │                   └─ NO           → show Login screen
    │
```

---

## 8. Token Lifecycle Reference

| Token | Lifetime | Storage | When to refresh |
|---|---|---|---|
| `access_token` | 15 minutes | `flutter_secure_storage` | On `401` from any endpoint |
| `refresh_token` | 7 days | `flutter_secure_storage` | Used once to get new access token |

- Access token is a JWT — you can decode it client-side to read `household_id` and `exp` without a network call.
- Refresh token is opaque — treat it as a secret string.
- Both tokens are **rotated** on every refresh call. Store the new pair atomically.
- Refresh tokens expire after 7 days of inactivity. After expiry the user must log in again.

---

## 9. OIDC (Coming Later)

The Pocket ID SSO flow is not yet implemented on the server. When it is, the client will need:

- A "Login with Pocket ID" button that opens a browser/WebView to `GET /api/auth/oidc/login`
- A custom URL scheme registered in the app (e.g. `finora://auth/callback`) to receive the redirect
- A handler that POSTs the authorization code to `POST /api/auth/oidc/mobile-redirect` and receives the same `{ access_token, refresh_token }` response as normal login

No changes to token storage or the auth interceptor will be needed — OIDC login produces the same token pair.
