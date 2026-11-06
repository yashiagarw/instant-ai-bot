# Notifications: accounts, registrations and templates to set up

What you must set up, outside this code, before each real channel works. Nothing here is needed for development:
with the defaults every channel has a console provider that prints to the API / worker log (numbers masked).

Until a channel is set up, its messages are **skipped with the reason** ("WHATSAPP_TPL_JOB_OFFER is not set",
"SMS_PROVIDER=msg91 needs MSG91_AUTH_KEY" …), logged, shown on the admin request page, and the **next channel** is
tried. In production the console providers count as "not set up" (they would reach nobody), except email's.

| Channel | Who gets it | Needed | Rough lead time |
|---|---|---|---|
| Email | Support inbox: new requests, escalations | An email provider and a verified sending domain | 1 day |
| Web push | Customers who tap "Turn on alerts" | VAPID keys (a command; no account) | minutes |
| SMS | Customers (status updates), mechanics (job offers) | DLT registration (India), then MSG91 | 1-2 weeks |
| WhatsApp | Opted-in customers and mechanics (offers with Accept / Reject) | Meta business verification, WhatsApp Business Account, approved templates | 1-3 weeks |
| Masked calls | Customer and mechanic during a job | Exotel account with KYC and an ExoPhone | 1-5 days |

Do them in this order: email and web push first (no waiting), then start DLT and Meta verification **in parallel**
(both wait on reviews).

Every setting below goes in `backend/.env.prod` (production) or `backend/.env` (development), never in git. After
changing any of them restart the API and the worker.

---

## 1. Email (support alerts)

Already used since Phase 1 (`EMAIL_PROVIDER`); Phase 5.2 only sends it through the worker, with retries.

1. Pick a provider. Simplest: **Resend** (resend.com) or your existing Google Workspace / Zoho mailbox over SMTP.
2. **Verify the sending domain** `instantmechanic.online` with the provider: add the SPF and DKIM DNS records it
   gives you (TXT / CNAME at your DNS host). Add a DMARC record (`_dmarc` TXT, start with `p=none`).
3. Create the sender `alerts@instantmechanic.online` (or the address you verified) and an API key (Resend) or an
   app password (SMTP).
4. Settings:
   `EMAIL_PROVIDER=resend` + `RESEND_API_KEY`, or `EMAIL_PROVIDER=smtp` + `SMTP_HOST`, `SMTP_PORT`,
   `SMTP_USERNAME`, `SMTP_PASSWORD`; `EMAIL_FROM="Instant Mechanic <alerts@instantmechanic.online>"`;
   `SUPPORT_EMAIL=` the team inbox.
5. Check: submit a request on the website; the admin request page shows "New request alert · Email · sent".

## 2. Web push (browser alerts)

No account. The browsers' own push services (Google FCM, Mozilla, Apple, Microsoft) deliver for free.

1. Generate a key pair once: `cd backend && uv run python -m app.notify.push keys`.
2. Settings: `PUSH_PROVIDER=webpush`, `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` (secret),
   `VAPID_SUBJECT=mailto:support@instantmechanic.online` (push services contact this address about problems).
3. Keep the pair: a new pair means every browser has to turn alerts on again.
4. HTTPS is required (Caddy provides it). Android Chrome, desktop Chrome / Edge / Firefox / Safari work directly.
   **iPhone / iPad (iOS 16.4+) only show web push for sites added to the Home Screen** (Share > Add to Home Screen;
   the site has a web app manifest since Phase 5.3). Mechanics get offer alerts the same way from the mechanic app
   (/m > Profile > Turn on alerts), on the same keys.
5. Check: on the request confirmation tap **Turn on alerts**, allow, then move the request to "accepted" in the
   admin app: the alert appears.

## 3. SMS (MSG91, with DLT registration)

Indian law (TRAI TCCCPR 2018) requires every business SMS to come from a registered sender with a registered
template. Order matters: DLT first, MSG91 second.

### 3.1 DLT registration (one-time, as the business)

1. Register as a **Principal Entity (PE)** on one operator's DLT portal (any one is enough for all operators), e.g.
   Jio TrueConnect (trueconnect.jio.com), Vi Vilpower (vilpower.in), Airtel DLT (dltconnect.airtel.in) or Smartping.
   Documents: PAN of the business, GST certificate (or other proof of business), an authorisation letter on
   letterhead for the person registering. Fee: about Rs 5,900 (incl. GST) on most portals. You get an
   **Entity ID (PE ID)**, usually in 2-7 working days.
2. Register a **Header (sender ID)**: 6 letters linked to the brand, type *Transactional / Service*, e.g. `IMECHN`.
   This is `MSG91_SENDER_ID` (the OTP login already uses it).
3. Register the **content templates** below, category **Service Implicit** (messages about a service the person
   asked for: their request, or a job offer to a partner mechanic). Hindi ones as **Unicode** templates. Each value is
   `{#var#}` and may be at most 30 characters (the code cuts values to 30). Each approved template gets a
   **DLT Template ID**. Approval takes 1-3 days; templates must match word for word what is sent.

### 3.2 MSG91

1. Create an MSG91 account (msg91.com), finish KYC, and add your **DLT Entity ID** and the **header** under
   SMS > Sender ID.
2. For each DLT template: SMS > Templates > Add: paste the DLT Template ID and the exact text, with each `{#var#}`
   written as MSG91's variable (`##VAR1##`, `##VAR2##` … in the order shown). MSG91 gives each one its own
   **template id**: that goes in the `MSG91_TPL_*` setting.
3. Settings: `SMS_PROVIDER=msg91`, `MSG91_AUTH_KEY` (API > Auth key), `MSG91_SENDER_ID`, and the ten
   `MSG91_TPL_<MESSAGE>_<EN|HI>` ids. A missing Hindi id falls back to the English SMS; a missing English one skips
   SMS for that message (logged, next channel).
4. Recharge SMS credit. Check: offer a job to a mechanic without WhatsApp opt-in: the admin request page shows
   "Job offer · SMS · sent".

### 3.3 SMS templates (register exactly this text)

| Setting | Language | Text |
|---|---|---|
| `MSG91_TPL_JOB_OFFER_EN` | English | New job {#var#}: {#var#}. Area: {#var#}. Car: {#var#}. Call Instant Mechanic support to accept. -Instant Mechanic |
| `MSG91_TPL_JOB_OFFER_HI` | Hindi (Unicode) | नया काम {#var#}: {#var#}. जगह: {#var#}. गाड़ी: {#var#}. काम लेने के लिए Instant Mechanic सपोर्ट को कॉल करें। -Instant Mechanic |
| `MSG91_TPL_MECHANIC_ASSIGNED_EN` | English | Instant Mechanic: {#var#} will fix your car ({#var#}). We will tell you when they are on the way. |
| `MSG91_TPL_MECHANIC_ASSIGNED_HI` | Hindi (Unicode) | Instant Mechanic: {#var#} आपकी गाड़ी ठीक करेंगे ({#var#})। रास्ते में होने पर हम आपको बताएँगे। |
| `MSG91_TPL_MECHANIC_EN_ROUTE_EN` | English | Instant Mechanic: {#var#} is on the way to you ({#var#}). |
| `MSG91_TPL_MECHANIC_EN_ROUTE_HI` | Hindi (Unicode) | Instant Mechanic: {#var#} आपके पास आ रहे हैं ({#var#})। |
| `MSG91_TPL_MECHANIC_ARRIVED_EN` | English | Instant Mechanic: {#var#} has arrived ({#var#}). |
| `MSG91_TPL_MECHANIC_ARRIVED_HI` | Hindi (Unicode) | Instant Mechanic: {#var#} पहुँच गए हैं ({#var#})। |
| `MSG91_TPL_JOB_COMPLETED_EN` | English | Instant Mechanic: your job {#var#} is done. Thank you for choosing us. |
| `MSG91_TPL_JOB_COMPLETED_HI` | Hindi (Unicode) | Instant Mechanic: आपका काम {#var#} पूरा हो गया। हमें चुनने के लिए धन्यवाद। |

Values, in order: job offer = reference, problem, area, car; mechanic assigned / on the way / arrived = mechanic's
first name, reference; job done = reference. Values never contain a phone number (removed before sending).
The OTP login template (`MSG91_TEMPLATE_ID`, Phase 4.0) is separate and unchanged.

## 4. WhatsApp (Meta WhatsApp Cloud API)

### 4.1 Business and number

1. **Meta Business Portfolio** at business.facebook.com, with the legal business name exactly as on your GST / PAN
   documents.
2. **Business verification** (Business settings > Security Center > Start verification): legal name, address,
   phone, website; documents such as the GST certificate or certificate of incorporation, and a utility bill or bank
   statement in the business name. Verify the domain `instantmechanic.online` (Business settings > Brand safety >
   Domains: a DNS TXT record or a meta tag). Takes 2-14 days. Until verified, the number has low sending limits and
   the display name may not show.
3. **Developer app**: developers.facebook.com > My apps > Create app > type *Business*, linked to the portfolio; add
   the **WhatsApp** product. This creates a WhatsApp Business Account (WABA).
4. **Phone number**: a number that is **not** on the WhatsApp or WhatsApp Business app (delete that account first if
   it is), able to receive an SMS or call for the code. WhatsApp Manager > Phone numbers > Add. Set the **display
   name** "Instant Mechanic" (reviewed by Meta: it must match the business / website) and a two-step PIN.
5. **Payment method** in WhatsApp Manager > Billing (utility template messages are charged per message in India;
   replies inside 24 hours of a person's message are free).

### 4.2 Credentials

1. **Permanent token**: Business settings > Users > System users > Add (role Admin) > Assign assets: the app and the
   WhatsApp account (full control) > Generate token with `whatsapp_business_messaging` and
   `whatsapp_business_management`, no expiry. This is `WHATSAPP_TOKEN` (secret). Do not use the 24-hour test token.
2. **Phone number ID** (WhatsApp > API setup, under the number; not the phone number): `WHATSAPP_PHONE_NUMBER_ID`.
3. **App secret** (App settings > Basic > App secret): `WHATSAPP_APP_SECRET` (secret). It checks every webhook call.
4. **Verify token**: any long random string you choose, e.g. `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`:
   `WHATSAPP_VERIFY_TOKEN`.
5. `WHATSAPP_API_VERSION` (default `v23.0`): keep it at a Graph API version that is still supported.

### 4.3 Message templates (WhatsApp Manager > Message templates > Create)

Category **Utility** for all. Create each name once and add **two languages: English (`en`) and Hindi (`hi`)**. Pick
"English" (code `en`), not "English (US)" (`en_US`): the code sends `en` and `hi`. Use these exact bodies; give
sample values when asked (e.g. IM-7K3Q9P, Battery, Malviya Nagar 110017, Maruti Swift Petrol, Ravi). Put the
approved names in the settings. Suggested names:

| Setting | Suggested name | Body (en) | Body (hi) | Buttons |
|---|---|---|---|---|
| `WHATSAPP_TPL_JOB_OFFER` | `im_job_offer` | New job {{1}}: {{2}}. Area: {{3}}. Car: {{4}}. Tap Accept or Reject. | नया काम {{1}}: {{2}}. जगह: {{3}}. गाड़ी: {{4}}. Accept या Reject दबाएँ। | Quick reply: `Accept`, `Reject` (in this order) |
| `WHATSAPP_TPL_MECHANIC_ASSIGNED` | `im_mechanic_assigned` | Instant Mechanic: {{1}} will fix your car ({{2}}). We will tell you when they are on the way. | Instant Mechanic: {{1}} आपकी गाड़ी ठीक करेंगे ({{2}})। रास्ते में होने पर हम आपको बताएँगे। | none |
| `WHATSAPP_TPL_MECHANIC_EN_ROUTE` | `im_mechanic_en_route` | Instant Mechanic: {{1}} is on the way to you ({{2}}). | Instant Mechanic: {{1}} आपके पास आ रहे हैं ({{2}})। | none |
| `WHATSAPP_TPL_MECHANIC_ARRIVED` | `im_mechanic_arrived` | Instant Mechanic: {{1}} has arrived ({{2}}). | Instant Mechanic: {{1}} पहुँच गए हैं ({{2}})। | none |
| `WHATSAPP_TPL_JOB_COMPLETED` | `im_job_completed` | Instant Mechanic: your job {{1}} is done. Thank you for choosing us. | Instant Mechanic: आपका काम {{1}} पूरा हो गया। हमें चुनने के लिए धन्यवाद। | none |

The button payloads are set per message by the code (`offer:<offer id>:accept` / `reject`): nothing to enter for
them. If Meta rejects a short template for "too many variables for its length", add a few plain words and change
the same text in `backend/app/notify/templates.py` (and the SMS template, if you keep them identical).

Replies (job confirmed, decline noted, offer closed, STOP / START confirmations) are sent as plain text right after
the person writes to us, which WhatsApp allows without a template.

### 4.4 Webhook (button presses, STOP / START, delivery status)

1. Deploy the API with `WHATSAPP_VERIFY_TOKEN` and `WHATSAPP_APP_SECRET` set (the URL must answer before Meta saves
   it). Caddy already serves it; nothing to add there.
2. App dashboard > WhatsApp > Configuration > Webhook: **Callback URL**
   `https://api.instantmechanic.online/api/webhooks/whatsapp`, **Verify token** = `WHATSAPP_VERIFY_TOKEN` > Verify
   and save. Then **subscribe to the `messages` field** (it carries button presses, texts and delivery statuses).
3. Settings: `WHATSAPP_PROVIDER=cloud` and the five `WHATSAPP_TPL_*` names. Restart the API and the worker; the
   worker prints any channel it cannot use at start-up.
4. Check: record your own opt-in as a mechanic (below), offer yourself a job in the admin app, press **Accept** in
   WhatsApp: the request becomes "accepted", the timeline and audit log say "<name> (mechanic, WhatsApp)", and you
   get "Thanks! Job … is yours".

### 4.5 Opt-in (required by WhatsApp's policy, and by our rules)

- **Customers** tick the optional WhatsApp box on the request form or switch it on in My account. The wording,
  its version (`whatsapp-customer-v1`), the time and the source are stored (`notification_optins`).
- **Mechanics**: the agent reads them the mechanic wording on a call and records it
  (`PUT /api/admin/mechanics/{id}/whatsapp-optin`, audited), or the mechanic sends **START** to the WhatsApp number.
- Anyone can send **STOP** to stop WhatsApp messages (their opt-ins are withdrawn and kept with the time); START
  turns them on again.
- No opt-in, no WhatsApp: the message goes by the next channel (push or SMS).

## 5. Masked calls (Exotel)

The customer's "Call <mechanic>" button on the tracking page and the mechanic's "Call customer" button in the app
never show either number: Exotel rings the person who pressed first, then connects the other, and both see only the
company's virtual number (ExoPhone). Calls are possible only while a mechanic is on the job (accepted … in progress),
at most `CALL_RATE_LIMIT` per request per window, and each is recorded (`masked_calls`, masked numbers only).

1. **Exotel account** at exotel.com (business plan with outbound calls). Complete **KYC** for the business: PAN,
   GST certificate (or certificate of incorporation), address proof, authorised signatory ID, and the signed
   customer agreement / telemarketer declaration Exotel asks for. Takes 1-5 working days.
2. **ExoPhone**: buy a virtual number (a landline-style 0xx number in Delhi, or a mobile number) in Exotel's
   dashboard > ExoPhones. Indian rules require it to be used for **transactional** calls only (no marketing): that is
   all this does. Ask Exotel to enable "connect two numbers" (Calls / connect API) on the account if it is not on.
3. **API credentials**: Exotel dashboard > Settings > API: the **API key**, **API token**, **Account SID** and the
   **subdomain** (`api.exotel.com` for the Singapore cluster, `api.in.exotel.com` for Mumbai).
4. Settings: `CALL_PROVIDER=exotel`, `EXOTEL_SID`, `EXOTEL_API_KEY`, `EXOTEL_API_TOKEN` (secret), `EXOTEL_SUBDOMAIN`,
   `EXOTEL_CALLER_ID` (the ExoPhone), optionally `CALL_TIME_LIMIT_SECONDS` (900). Restart the API.
5. **Recharge** call credit. Each connected call is charged for both legs.
6. Check: on a job you accepted in the mechanic app, press "Call customer" with your own number as the customer:
   your phone rings first, then the other phone, and both show the ExoPhone.

Without these settings the call buttons answer "Calls are not set up yet: call support" (development: the console
provider prints the call with masked numbers).

---

## Settings summary

| Setting | Channel | Example / note |
|---|---|---|
| `NOTIFY_CUSTOMER_CHANNELS` | all | `whatsapp,push,sms` (order tried) |
| `NOTIFY_MECHANIC_CHANNELS` | all | `whatsapp,sms` |
| `NOTIFY_SUPPORT_CHANNELS` | all | `email` |
| `NOTIFY_MECHANIC_LANGUAGE` | all | `en` or `hi` (customers: from their diagnosis, else `en`) |
| `NOTIFY_MAX_ATTEMPTS`, `NOTIFY_RETRY_BASE_SECONDS` | all | `4`, `30` (30 s, 2 min, 8 min) |
| `EMAIL_PROVIDER`, `EMAIL_FROM`, `SUPPORT_EMAIL`, `RESEND_API_KEY` / `SMTP_*` | email | see 1 |
| `PUSH_PROVIDER`, `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | push | see 2 |
| `SMS_PROVIDER`, `MSG91_AUTH_KEY`, `MSG91_SENDER_ID`, `MSG91_TPL_*` (10) | SMS | see 3 |
| `WHATSAPP_PROVIDER`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_API_VERSION`, `WHATSAPP_TPL_*` (5) | WhatsApp | see 4 |
| `CALL_PROVIDER`, `EXOTEL_SID`, `EXOTEL_API_KEY`, `EXOTEL_API_TOKEN`, `EXOTEL_SUBDOMAIN`, `EXOTEL_CALLER_ID`, `CALL_TIME_LIMIT_SECONDS`, `CALL_RATE_LIMIT`, `CALL_RATE_WINDOW_SECONDS` | Masked calls | see 5 |
