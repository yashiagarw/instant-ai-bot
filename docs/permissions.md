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
| `customers.read` | yes | no | yes | no | no |
| `customers.contact` | yes | no | yes | no | no |
| `content.read` | yes | yes | no | no | no |
| `content.review` | yes | yes | no | no | no |

What each permission covers:

| Permission | Endpoints |
| --- | --- |
| public | `POST /api/admin/auth/login`, `POST /api/admin/auth/two-factor/confirm` (needs the setup cookie from the login) |
| `self` | `GET /api/admin/auth/me`, `POST /api/admin/auth/logout`, `POST /api/admin/auth/password` (own password: current password + a fresh code) |
| `staff.read` | `GET /api/admin/staff` |
| `staff.manage` | `POST /api/admin/staff` (invite: a temporary password returned once), `PUT /api/admin/staff/{id}/roles`, `POST /api/admin/staff/{id}/deactivate`, `.../activate`, `.../unlock`, `.../reset-two-factor` (removes two-factor: set up again at the next sign-in) |
| `audit.read` | `GET /api/admin/audit` (filters: `action`, `entity_type`, `entity_id`, `actor`, `since`, `until`, `limit`) |
| `requests.read` | `GET /api/admin/requests`, `GET /api/admin/requests/{id}`: phone numbers show only the last 4 digits |
| `requests.contact` | the same, with the customer's full phone number (to call them) |
| `requests.update` | `PATCH /api/admin/requests/{id}` (status) |
| `content.read` | `GET /api/admin/content/generated-questions`, `GET /api/admin/content/image-labels` |
| `content.review` | `POST /api/admin/content/generated-questions/{id}/review` (approve / reject) |
| `customers.read` | `GET /api/admin/customers` (search by name or the last digits of the phone): phone numbers always masked |
| `customers.contact` | `POST /api/admin/customers/{id}/reveal-phone`: one customer's full number, each time written to the audit log |

## Admin app menu (apps/admin)

Menu items are hidden without their permission, and their pages say "no access" when opened directly. Hiding is
only for convenience: the API checks every call.

| Menu item | Shown with |
| --- | --- |
| Overview | `self` (every staff member) |
| Requests, Mechanics | `requests.read` (Mechanics also with `staff.read`) |
| Knowledge, Vehicles, Parts & Prices, Datasets, Quality | `content.read` |
| Users | `staff.read` (Staff tab) or `customers.read` (Customers tab) |
| Audit log | `audit.read` |

## Staff sign-in

- Email + password (argon2id, at least 12 characters, not the email name), then a 6-digit TOTP code (RFC 6238,
  30 s, one step of clock drift). A code that was used once is refused after that.
- **No two-factor yet** (invited staff, or after a reset): a correct password leads to the setup step instead of a
  session. The response shows the QR code and setup key once and sets a 10-minute HttpOnly setup cookie; a code
  from the new secret (`POST /api/admin/auth/two-factor/confirm`) saves it and signs in. 5 wrong codes, or 10
  minutes, end the setup: sign in again for a new QR code.
- **Invited staff** get a temporary password (shown once to the inviter). After signing in and setting up
  two-factor they can only change their password (every other admin call answers 403 "Choose your own password
  first") until they choose their own.
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
| `staff.login`, `staff.login_failed`, `staff.locked`, `staff.login_locked`, `staff.logout`, `staff.two_factor_setup_started`, `staff.two_factor_enrolled` | sign-in events |
| `customer.reveal_phone` | a customer's full phone number was shown |
| `staff.create`, `staff.set_roles`, `staff.activate`, `staff.deactivate`, `staff.unlock`, `staff.reset_two_factor`, `staff.change_password` | staff accounts (API or CLI) |
| `request.set_status` | a mechanic request's status changed |
| `content.review_question` | a generated question approved or rejected |
