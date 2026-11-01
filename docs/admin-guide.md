# Admin guide

This guide is for the Instant Mechanic team: support agents, content admins and super admins. It explains the admin
app in simple steps. You do not need to know anything technical.

The admin app is a website for staff only. The customer website is separate.

## Who can do what

You only see the menu items your role allows. If you open a page you cannot use, it says "No access".

| Role | What you can do |
| --- | --- |
| Support agent | Requests (handle customers who need a mechanic), Mechanics, Customers |
| Content admin | Knowledge, Vehicles, Parts & Prices, Datasets, Quality |
| Super admin | Everything, plus staff accounts, the audit log and mechanics' ID documents |
| Mechanic | Can read requests only |

Everything you change is saved in the audit log with your name and the time.

---

## 1. Daily startup

### Sign in

1. Open the admin app in your browser. Ask your team lead for the address.
2. Type your email and password, then press **Continue**.
3. Open the authenticator app on your phone (for example Google Authenticator). Type the 6-digit code for
   Instant Mechanic and press **Sign in**.
4. If the code is refused, wait for the next code and try again. Check that your phone's time is set
   automatically.

You are signed out after 8 hours, or after 30 minutes without using the app.

### Check the Overview page first

The **Overview** page is the first page you see. It shows **today** (from midnight, India time).

- **Red boxes come first.** A request in a red box is **safety-critical**: the customer was told to stop driving.
  Open it and call the customer straight away.
- **No agent after 10 minutes**: requests that nobody has taken yet. Take the oldest ones first (red ones before
  everything else).
- **Requests today**: how many came in today, and where they are now (New, Triaged, Mechanic on the way, ...).
- **Diagnoses today**: how many customers used the diagnosis today, and how many safety alerts were shown.
- **LLM spend today**: "LLM off" means we do not use any AI text service at the moment. This is normal.

Press **Refresh** to see the latest numbers.

### If the app does not open

Tell the person who looks after the system. (For them: the start commands are in the README, "Run".)

---

## 2. Handling a request

A request is a customer asking for a mechanic. Open **Requests** in the menu.

### The queue

- The list is already in the right order: **safety-critical** first (red label), then **urgent**, then the
  **oldest**.
- **Waiting** shows how long the customer has waited.
- Phone numbers show only the last 4 digits.
- Use the filters to narrow the list: Status, Safety, Category, "Only mine", or search by reference, name, area or
  pincode. **Closed** shows finished and cancelled requests.

### Take a request

1. Click the request's reference (for example IM-7K3Q9P).
2. Press **Take this request**. You are now the owner. Only the owner can see the customer's full phone number.
3. Press **Show number** and call the customer. (Every time you show a number, it is written in the audit log.)

### Triage

1. Talk to the customer. Check the car, the problem and the AI's likely causes on the page.
2. If it is safety-critical, tell the customer not to drive. Arrange help or a tow.
3. Press **Mark triaged**.

### Offer the job to a mechanic

1. Look at **Suggested mechanics**. They are on duty, work in that area, have the right skill and are not full
   today. The best match is first. Each one shows why it was suggested.
2. Call the mechanic. If they can do it, press **Offer job** next to their name.
3. When they answer, press **Mechanic accepted** or **Mechanic declined**.
   - If they decline, the request goes back to Triaged. Offer it to the next mechanic.
4. Need someone who is not suggested? Open **Left out**, press **Offer anyway** and write why.

The map shows roughly where the customer is (the centre of their pincode). If it says **rough location**, the
point can be several kilometres off.

### Keep the status up to date

Press the buttons as things happen:

- **Mechanic is on the way**
- **Mechanic arrived**
- **Repair started**

The customer sees these updates on their request page in simple words.

- **Escalate**: a senior person must look at it. Write why.
- **Cancel request**: the customer no longer needs help. Write why.

### Notes

Write anything useful under **Internal notes** (for example "Called twice, no answer"). Customers never see these
notes.

---

## 3. Completing a job

When the repair is done, the request page shows **Complete the job** (only while the status is "Repair in
progress").

1. **Confirmed fault**: choose what the mechanic actually found. The AI's top 3 guesses are at the top of the list.
   If it is something else, choose **Other** and describe it.
2. **Parts used**: press **Add a part** for each part. Give the name, the quantity and the price.
3. **Final cost**: what the customer paid, in rupees.
4. **Mechanic's notes**: anything the mechanic said.
5. Press **Complete job**.

Please be careful with the confirmed fault. It is used to check how good the AI is, and to make it better.

---

## 4. Editing knowledge

Knowledge is everything the diagnosis uses: faults, questions, answers, safety rules, parts and prices. Open
**Knowledge** in the menu (content admins and super admins).

You never change the live website directly. You change a **draft** (a copy). Customers see your changes only
after the draft is **published** (section 5).

1. Press **Start an edit draft**. It takes about a minute and a half to make the copy.
2. The bar at the top shows which draft you are editing.
3. Choose a tab:
   - **Faults**: details, symptoms, causes, repair steps, advice, safety, towing, customer phrases, pictures.
   - **Questions**: the question text, its answers and what each answer means for each fault.
   - **Tiles & categories**: the problem tiles customers pick from.
   - **Safety rules**: these decide when we tell a customer to stop driving. You must confirm every change.
     Rules are never deleted, only rejected.
4. Press **Save** on each item you change.
5. **Changes in this draft** lists everything you changed. You can undo (revert) any change there.

Parts and prices are edited the same way on the **Parts & Prices** page. Every price needs a source (the supplier
or a link) and the date it was checked. A price of 20,000 rupees or more needs a **Second look** by a different
person.

---

## 5. Publishing and rolling back

Open **Datasets** in the menu.

### Publish a draft

1. Open the draft.
2. Read the **validation report**. "Nothing lost" must be OK.
3. Press **Run the evaluation**. It tests the draft on thousands of example cases and compares it with the live
   version. It takes a few minutes; you can watch the progress.
4. Check the results:
   - **Top-3 accuracy** must not drop by more than 3 points.
   - **Danger cases missed** must not go up. (A danger case is one where we must tell the customer to stop
     driving.)
5. If both are fine, press **Publish**. The new version is live for new diagnoses within a minute. Customers who
   are halfway through a diagnosis keep the old version.

If publishing is blocked, fix the draft and run the evaluation again. Only a super admin can **override** the
block, and they must write a reason.

### Upload a new Excel file

1. Press **Upload a category file** and choose the category and the file.
2. Press **Upload and build draft**. The system builds a draft with that file. Then follow "Publish a draft".

### Roll back (undo a publish)

If something went wrong after publishing:

1. On the Datasets page, find the older version in the **History** table.
2. Press **Roll back**, choose the category, and confirm.
3. The system builds and publishes a new version with that category as it was. Other categories stay as they are.

### Throw away a draft

Press **Discard draft** if you do not want it any more.

---

## 6. Sign-off

Some items were checked automatically and still need a person (a mechanic or an expert) to agree. They show
"pending mechanic sign-off".

1. Open **Knowledge**, then the **Sign-off** tab.
2. Use the filter to show items that are still pending.
3. Check each item carefully. If it is right, press **Sign off as me**. Your name and today's date are saved. A
   safety rule becomes "approved".
4. To sign off many items at once, filter the list, check every item shown, then press **Sign off all N shown**.
   Only do this when you have really checked all of them.

Sign-offs are saved in the draft, so they go live when the draft is published.

---

## 7. Quality

Open **Quality** in the menu (content admins and super admins). It shows how well the diagnosis works. Choose
**Last 7 / 30 / 90 days** at the top.

- **Safety**
  - **Danger cases missed**: in the latest test, how many cases did not show a stop-driving warning when they
    should have. Red means at least one was missed: tell the content team.
  - **Safety alerts shown today**: how many warnings customers saw today.
- **Latest evaluation**: accuracy by category for the version customers use now.
  - **Top-1**: the right fault was the first answer.
  - **Top-3**: the right fault was in the first three.
  - **Real cases** are shown in their own table. They are never mixed with the example cases.
- **Confirmed by mechanics**: how often the AI was right, compared with the fault the mechanic confirmed when the
  job was completed. Shown by category and by dataset version. "Not enough data yet" means fewer than 30
  confirmed jobs: the number would not be reliable yet.
- **Diagnoses**: low confidence (the AI was not sure), no match (the AI found nothing), the average number of
  questions, and how many customers said the answer was helpful. "LLM off" means no AI text service is used.

### Sessions to review

At the bottom there are three lists: **Negative feedback** (the customer said "not helpful"), **Low confidence**
and **No match**.

1. Click a session to open its **replay**. You see every question and answer with the time. Answers the customer
   took back are crossed out. You cannot change anything here. Phone numbers are hidden.
2. Look for what went wrong: a missing question, a wrong answer, a phrase the system did not understand. Fix it
   in **Knowledge** (in a draft).

### Add to golden set

If you know the right answer for a session, add it to the **golden set**: real cases the app is tested against.

1. On the replay, press **Add to golden set**.
2. Choose the **right fault**. If a mechanic completed a job for this customer, their confirmed fault is already
   chosen.
3. Optional: the **safety alert** the case should show.
4. **Who confirmed it**: the mechanic (on the completed job) or you (from the replay).
5. Press **Add case**.

The case is saved without the customer's name, phone number or address (only the pincode is kept). A session can
be added only once.

---

## Need help?

- Locked out (5 wrong tries): wait 15 minutes, or ask a super admin to unlock you.
- Lost your phone: ask a super admin to **reset two-factor**. You set it up again at your next sign-in.
- Something looks wrong on a page: take a screenshot and tell the team. Do not try to fix live data another way.
