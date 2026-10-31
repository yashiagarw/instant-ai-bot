# Staff permissions

Who may do what on `/api/admin`. The code is `backend/app/admin/permissions.py`; `tests/test_admin.py` checks this
table against it and calls every admin endpoint with every role.

## Rules

- **Deny by default.** Every `/api/admin` route declares one permission (`@requires(...)`) or is the public staff
  login (`@public`). A route that declares nothing is refused for everyone, and the app refuses to start if one exists
  or if any route sits under `/api/admin` outside the admin router.
- **Staff and customers are separate.** Staff sign in with email + password + authenticator code and get the
  `im_staff` cookie (HttpOnly, Secure, SameSite=Strict, path `/api/admin`). The customer cookie `im_session` is never
  read by `/api/admin`, and the staff cookie is not a customer login. Answers: 401 when not signed in as staff, 403
  when signed in without the permission.
- **Customer** is the role of every phone-login account. It has no admin permissions and is never stored in
  `user_roles` (a database check refuses it).
- A staff member's permissions are the union of their roles'. Role changes, deactivation, a two-factor reset and a
  password change end the person's other sessions.
- There is always at least one active super admin: the last one cannot be demoted or deactivated, and nobody can
  remove their own super admin role or deactivate themselves.

## Permission map

| Permission | super_admin | content_admin | support_agent | mechanic | customer |
| --- | --- | --- | --- | --- | --- |
| `self` | yes | yes | yes | yes | no |
| `staff.read` | yes | no | no | no | no |
| `staff.manage` | yes | no | no | no | no |
| `audit.read` | yes | no | no | no | no |
| `requests.read` | yes | no | yes | yes | no |
| `requests.contact` | yes | no | yes | no | no |
| `requests.update` | yes | no | yes | no | no |
| `content.read` | yes | yes | no | no | no |
| `content.review` | yes | yes | no | no | no |

What each permission covers:

| Permission | Endpoints |
| --- | --- |
| public | `POST /api/admin/auth/login` |
| `self` | `GET /api/admin/auth/me`, `POST /api/admin/auth/logout`, `POST /api/admin/auth/password` (own password: current password + a fresh code) |
| `staff.read` | `GET /api/admin/staff` |
| `staff.manage` | `POST /api/admin/staff` (two-factor setup returned once), `PUT /api/admin/staff/{id}/roles`, `POST /api/admin/staff/{id}/deactivate`, `.../activate`, `.../unlock`, `.../reset-two-factor` |
| `audit.read` | `GET /api/admin/audit` (filters: `action`, `entity_type`, `limit`) |
| `requests.read` | `GET /api/admin/requests`, `GET /api/admin/requests/{id}`: phone numbers show only the last 4 digits |
| `requests.contact` | the same, with the customer's full phone number (to call them) |
| `requests.update` | `PATCH /api/admin/requests/{id}` (status) |
| `content.read` | `GET /api/admin/content/generated-questions`, `GET /api/admin/content/image-labels` |
| `content.review` | `POST /api/admin/content/generated-questions/{id}/review` (approve / reject) |

## Staff sign-in

- Email + password (argon2id, at least 12 characters, not the email name) + a 6-digit TOTP code (RFC 6238, 30 s,
  one step of clock drift). A code that was used once is refused after that.
- One answer for any wrong part ("Email, password or code is wrong."). After `STAFF_MAX_FAILED_LOGINS` (5) failures
  in a row the account is locked for `STAFF_LOCKOUT_MINUTES` (15); a super admin can unlock it earlier. Sign-ins are
  also rate-limited per IP.
- Sessions: at most `STAFF_SESSION_HOURS` (8) after sign-in and `STAFF_IDLE_MINUTES` (30) without a request
  (customers: 30 days).
- TOTP secrets are stored encrypted with `STAFF_TOTP_KEY`; passwords as argon2id hashes; session cookies as SHA-256.

## Audit log

`audit_log`: time, actor (staff id and email, `cli` or the email tried), action, entity type and id, before and after
JSON, IP. Written by `app.admin.audit.record` for every admin write and for staff sign-in events. Before writing, it
replaces passwords, secrets, tokens, OTP and TOTP values with `***` and cuts phone numbers to their last 4 digits.
The table is append-only (a trigger refuses UPDATE and DELETE).

| Action | When |
| --- | --- |
| `staff.login`, `staff.login_failed`, `staff.locked`, `staff.login_locked`, `staff.logout` | sign-in events |
| `staff.create`, `staff.set_roles`, `staff.activate`, `staff.deactivate`, `staff.unlock`, `staff.reset_two_factor`, `staff.change_password` | staff accounts (API or CLI) |
| `request.set_status` | a mechanic request's status changed |
| `content.review_question` | a generated question approved or rejected |
