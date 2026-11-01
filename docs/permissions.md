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
| `datasets.manage` | yes | yes | no | no | no |
| `datasets.override` | yes | no | no | no | no |
| `knowledge.edit` | yes | yes | no | no | no |
| `vehicles.manage` | yes | yes | no | no | no |
| `mechanics.read` | yes | no | yes | no | no |
| `mechanics.manage` | yes | no | yes | no | no |
| `mechanics.documents` | yes | no | no | no | no |
| `quality.read` | yes | yes | no | no | no |
| `quality.golden` | yes | yes | no | no | no |

What each permission covers:

| Permission | Endpoints |
| --- | --- |
| public | `POST /api/admin/auth/login`, `POST /api/admin/auth/two-factor/confirm` (needs the setup cookie from the login) |
| `self` | `GET /api/admin/auth/me`, `POST /api/admin/auth/logout`, `POST /api/admin/auth/password` (own password: current password + a fresh code) |
| `staff.read` | `GET /api/admin/staff` |
| `staff.manage` | `POST /api/admin/staff` (invite: a temporary password returned once), `PUT /api/admin/staff/{id}/roles`, `POST /api/admin/staff/{id}/deactivate`, `.../activate`, `.../unlock`, `.../reset-two-factor` (removes two-factor: set up again at the next sign-in) |
| `audit.read` | `GET /api/admin/audit` (filters: `action`, `entity_type`, `entity_id`, `actor`, `since`, `until`, `limit`) |
| `requests.read` | `GET /api/admin/requests` (the queue: safety-critical first, then urgent, then oldest; filters `view`, `status`, `safety`, `category`, `mine`, `q`), `GET /api/admin/requests/{id}` (detail, timeline, notes, outcome), `GET .../{id}/suggestions` (matching mechanics with reasons), `GET .../{id}/faults` (what the confirmed fault can be: the diagnosis's top 3, then the category's faults): customer phone numbers always show only the last 4 digits |
| `requests.contact` | `POST /api/admin/requests/{id}/reveal-phone`: the customer's full number, **only for the agent assigned to the request**; each reveal written to the audit log |
| `requests.update` | `PATCH /api/admin/requests/{id}` (an allowed status change; cancel / escalate need a note), `PUT .../{id}/agent` (take it; giving it to someone else needs `staff.manage`), `POST .../{id}/offer` (to a mechanic), `.../response` (the mechanic accepted / declined), `.../notes` (internal), `.../outcome` (confirmed fault: completes the job) |
| `mechanics.read` | `GET /api/admin/mechanics`, `GET /api/admin/mechanics/{id}` (with the mechanic's phone number; jobs today, acceptance rate) |
| `mechanics.manage` | `POST /api/admin/mechanics`, `PUT .../{id}`, `PUT .../{id}/skills`, `.../zones`, `.../availability` (weekly shifts, India time), `.../duty` (on / off duty); live, audited |
| `mechanics.documents` | `GET/POST /api/admin/mechanics/{id}/documents`, `GET/DELETE .../documents/{doc}`: ID documents, encrypted with `MECHANIC_DOCS_KEY`; every view written to the audit log |
| `self` (overview) | `GET /api/admin/overview`: today (India time). Its parts depend on the caller: requests today by status and the unassigned ones (`requests.read`), diagnoses, safety alerts and LLM spend today (`quality.read`); the rest is null |
| `quality.read` | `GET /api/admin/quality` (metrics; `days`), `GET /api/admin/quality/review` (`kind`: negative_feedback, low_confidence, no_match; `days`), `GET /api/admin/quality/sessions/{id}` (read-only replay; phone numbers, emails and number plates masked), `GET /api/admin/quality/faults` |
| `quality.golden` | `POST /api/admin/quality/sessions/{id}/golden`: writes the session as a real case to `data/eval/golden/real_cases/` (no personal data) and records it |
| `content.read` | `GET /api/admin/content/generated-questions`, `GET /api/admin/content/image-labels` |
| `content.review` | `POST /api/admin/content/generated-questions/{id}/review` (approve / reject) |
| `content.read` (datasets) | `GET /api/admin/datasets` (versions, categories, active job), `GET /api/admin/datasets/versions/{id}` (validation report, diff, eval), `GET /api/admin/datasets/jobs/{id}` (progress) |
| `datasets.manage` | `POST /api/admin/datasets/uploads` (a category file: a draft built in the background), `POST .../versions/{id}/rebuild`, `.../eval`, `.../publish`, `.../rollback`, `DELETE .../versions/{id}` (discard a draft), `POST .../jobs/{id}/cancel` (a job not started yet) |
| `content.read` (knowledge) | `GET /api/admin/knowledge/drafts`, `.../versions/{id}/taxonomy`, `.../faults`, `.../faults/{key}`, `.../questions`, `.../safety`, `.../signoff`, `.../edits`, `GET /api/admin/knowledge/images`, `GET /api/admin/vehicles/unlisted`, `GET /api/admin/vehicles/makes` |
| `knowledge.edit` | `POST /api/admin/knowledge/drafts` (start an edit draft), `POST .../versions/{id}/edits` (save an item: always into a draft, published through the pipeline), `DELETE .../versions/{id}/edits/{edit}` (revert), `POST .../versions/{id}/signoff` (mark reviewed under your own name), `POST /api/admin/knowledge/generated-questions/{id}/approve` |
| `vehicles.manage` | `POST /api/admin/vehicles/unlisted/{id}/add` (to the car catalogue, live), `POST .../unlisted/{id}/dismiss`; the catalogue: `POST/PUT/DELETE /api/admin/vehicles/makes`, `.../models`, `.../generations`, `.../variants` (live, audited; a variant in use is not deleted) |
| `content.read` (parts) | `GET /api/admin/vehicles/catalogue`, `GET /api/admin/parts/versions/{id}/parts`, `.../parts/{key}`, `.../prices`, `.../labour`, `.../zone-rates.yaml`, `GET /api/admin/parts/csv-template` |
| `knowledge.edit` (parts, pictures) | part, price, fit, labour and zone-rate edits through `POST /api/admin/knowledge/versions/{id}/edits`; `POST /api/admin/parts/versions/{id}/prices/second-look` (not the person who entered the price); `POST /api/admin/parts/versions/{id}/import` (CSV, `commit=true` to import); `POST /api/admin/media/pictures` (upload through the photo storage); `POST /api/admin/knowledge/versions/{id}/signoff/bulk` |
| `datasets.override` | publish although the eval gate blocks it (top-3 down more than 3 points, or safety recall down): `override_reason` of at least 15 characters, written to the audit log |
| `customers.read` | `GET /api/admin/customers` (search by name or the last digits of the phone): phone numbers always masked |
| `customers.contact` | `POST /api/admin/customers/{id}/reveal-phone`: one customer's full number, each time written to the audit log |

## Admin app menu (apps/admin)

Menu items are hidden without their permission, and their pages say "no access" when opened directly. Hiding is
only for convenience: the API checks every call.

| Menu item | Shown with |
| --- | --- |
| Overview | `self` (every staff member) |
| Requests | `requests.read` (actions: `requests.update`; the customer's number: `requests.contact` and owning the request) |
| Mechanics | `mechanics.read` (editing: `mechanics.manage`; the Documents section: `mechanics.documents`) |
| Knowledge, Vehicles, Parts & Prices, Datasets | `content.read` (editing: `knowledge.edit`; the unlisted-vehicles queue: `vehicles.manage`) |
| Quality | `quality.read` ("Add to golden set": `quality.golden`) |
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
| `request.set_status` | a mechanic request's status changed (also an offer, the mechanic's answer and completion; the note or confirmed fault in `after`) |
| `request.set_agent` | who owns a request changed |
| `request.reveal_phone` | the assigned agent revealed the customer's full number (masked in the log) |
| `mechanic.create`, `mechanic.update` | a mechanic added or changed (phone masked) |
| `mechanic.skills`, `mechanic.zones`, `mechanic.availability`, `mechanic.duty` | their skills, zones, weekly shifts, on / off duty |
| `mechanic.document_upload`, `mechanic.document_view`, `mechanic.document_delete` | an ID document stored (encrypted), opened, deleted |
| `quality.golden_add` | a real session was added to the evaluation's golden set (case id, expected fault, file in `after`) |
| `content.review_question` | a generated question approved or rejected |
| `dataset.upload`, `dataset.rebuild`, `dataset.eval`, `dataset.publish_requested`, `dataset.rollback_requested`, `dataset.discard`, `dataset.job_cancel` | Datasets page actions (the job id in `after`) |
| `dataset.publish`, `dataset.rollback` | the worker switched the published version (`before`: the version archived) |
| `knowledge.edit`, `knowledge.signoff`, `knowledge.edit_revert` | an editor save, sign-off or revert (`before` / `after`: the changed fields) |
| `knowledge.safety_edit`, `knowledge.safety_edit_revert` | a safety rule or trigger change, with its old and new values |
| `dataset.edit_draft` | an edit draft started |
| `vehicle.add_from_unlisted`, `vehicle.dismiss_unlisted` | the unlisted-vehicles queue |
| `vehicle.make_create`, `vehicle.make_update`, `vehicle.make_delete`, and the same for `model`, `generation`, `variant` | the car catalogue (before / after) |
| `knowledge.signoff_bulk` | a bulk sign-off: the filter used and the count (one entry for all items) |
| `parts.csv_import` | a CSV price import: rows, valid, errors, flagged |
| `media.upload` | a picture uploaded in the admin app |
| `dataset.publish_override` | published although the eval gate blocked it: the gate's reasons in `before`, the written reason in `after` |
