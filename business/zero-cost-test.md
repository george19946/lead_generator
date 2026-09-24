# The £0 interest test (do this first)

**Goal:** find out, for £0, whether CQC consultancies want this, before spending anything.
**Cost:** £0. **Time:** about 8 hours over 4 weeks, most of it in the first two days.
**When to spend money:** only once the test passes (section 6). Then follow `8-week-trial-plan.md`.

---

## 1. What makes £0 possible

| Normally costs | Free replacement | What you give up |
|---|---|---|
| ICO data protection fee (£47) | **Companies-only mode** (on by default): sole traders and partnerships are never stored or sent, so the leads hold no personal data. The prospects you email are handled for your own marketing, which is exempt from the fee. | About 1–2% of leads (in the test boroughs, 2 of 133 providers). |
| Domain and business email (£20+) | A **new, free Gmail** address used only for this, signed with your own full name | A little credibility. "I've built a tool and want feedback" suits a Gmail address. |
| Website hosting | **Netlify**, free, at `yourname.netlify.app` | Your own domain name |
| Mailing software | **Claude drafts each email in Gmail** (Gmail connector); you press send | 15 minutes a day |
| A prospect list | `uv run signals prospects`: **594 consultancies from Companies House, 144 of them in London**. It uses 11 free API requests. | You find the email addresses, with Claude's help |
| Payments | Nothing until someone wants to pay. Then a Stripe Payment Link, which is free until used. | |

**Check the fee point yourself for free.** Take the ICO's 5-minute "Do I need to pay a data protection fee?"
self-assessment at ico.org.uk, answering for companies-only mode. This is my reading, not legal advice.

**Two small legal points:**
- **Sign emails with your own full name.** If you trade under a brand name, the business-names rules require your
  name and an address on business letters; signing as yourself, with the brand only as your project's name, avoids
  that. Add an address before you send an invoice.
- **Email only companies and LLPs.** `signals prospects` lists nothing else. Every email says who you are and has a
  one-line opt-out.

---

## 2. Why this isn't "a cold email with nothing behind it"

Every email carries **real results for the reader's own area**, and the tool delivers more the same day:

1. **In the email itself:** live numbers and three real examples from their area. For example: "Green Arrow Care
   (Hackney): last rated Good on 2018-12-15". `uv run signals sample` writes these into `email-teaser.txt` for
   you, with a ready-made sentence to paste. It only ever names organisations.
2. **One link:** your free sample page, with live numbers and anonymised examples.
3. **If they reply "yes":** the full "due for inspection" list for their area, the same day, as a spreadsheet and a
   PDF digest. Then 4 weekly digests.
4. **The ask is small and honest:** "I've built this; try it free and tell me if it's useful." People answer
   requests for feedback far more often than sales pitches.

---

## 3. Set-up (2 days, about 4 hours)

**Day 1 (about 2 hours)**
1. **Update the code.** Drag the code folder to the Bin, unzip the new version into your home folder, open
   Terminal in it, and run `uv sync`. Companies-only mode is on automatically; the next command you run removes
   any sole traders already in your database.
2. **Create a free Gmail**, for example `caresignals.yourname@gmail.com`. Keep it separate from your personal email.
3. **Business details.** Run `open -e ~/Signals/business.yaml` and fill in:
   - `legal_name`: your full name;
   - `email`: the new Gmail address;
   - `website`: leave empty for now.

   Leave the ICO number, address and company number empty. Save the file.
4. **Website.** Run `uv run signals site`. Go to app.netlify.com, sign up free, and drag the `~/Signals/site`
   folder onto "Deploy manually". Rename the site (Site settings, then Change site name) to get
   `something.netlify.app`. Put that address in `website:` in `business.yaml`, run `uv run signals site` again, and
   drag the folder again.
5. **Numbers for your emails.** Run `uv run signals run`, then:
   ```
   uv run signals sample --region london
   ```
   It prints a folder; open `email-teaser.txt` in it.

**Day 2 (about 2 hours)**

6. **The prospect list.** Run:
   ```
   uv run signals prospects --region london
   ```
   It writes `~/Signals/prospects/prospects-<date>.csv`.
7. **Find their email addresses with Claude.** In the Claude app, with web search on, attach the CSV and paste:
   > For each company in this file, find its website and the business email address published on that website
   > (a contact, info or hello address, or a named person's address at the company's own domain). Only use
   > addresses the company publishes itself; never guess one. Fill in the website, email and first_name columns
   > (first_name only if a person is named) and put the page where you found the email in notes. Leave email
   > blank if there isn't one. Return the CSV.
8. **Approve the list.** Open the result. Delete any company that clearly isn't a CQC consultancy, and type `yes`
   in `approved` for the rest that have an email. **Aim for 60–80.** If London gives fewer than 60, add a second
   region: see "Your customer regions" in the README. The backfill is free and runs on its own.
9. **Connect Gmail to Claude.** In the Claude app, go to Settings, then Connectors, and connect Gmail, signed in
   to the new account.

---

## 4. The 4 weeks

| Week | What you do | Time |
|---|---|---|
| 1 | Each weekday, ask Claude to draft **15 emails** from the approved list (prompt below). Check them in Gmail Drafts and send. Reply to anyone who answers the same day. | 15–20 min a day |
| 2 | Finish the list. Send **one** follow-up to anyone who hasn't replied after 5 days. Monday: send each trial user their digest. | 15–20 min a day |
| 3 | Monday digests. The **check-in email** after their second digest. | 30 min |
| 4 | Monday digests. Final digest with the **"would you pay?"** question. Count the results (section 6). | 30 min |

**Claude prompt for drafting** (attach the prospects CSV and `email-teaser.txt`):
> Using the Gmail connector, create a draft (don't send) for each of the next 15 rows in this CSV where approved is
> "yes" and the notes don't say "emailed". Use the email template below, and the numbers and examples from
> email-teaser.txt. Personalise the first line using the company's website if you can. Then give me the CSV back
> with "emailed <date>" in notes for those rows.

**When someone says yes:**
1. Reply the same day. Attach `due_for_inspection_all.csv` from the sample folder, plus the digest saved as a PDF
   (open `digest.html`, then File, Print, Save as PDF).
2. Note their name and area in a simple list: a note on your phone is enough.
3. **Mondays** (your scheduled job has already run): open `~/Signals/outputs/care/<latest date>/london/`, save
   `digest.html` as a PDF, and reply in each trial user's email thread with it attached. That's about 2 minutes
   each.
4. **If someone covers only some London boroughs,** add a region for them with their councils (`local_authorities`)
   in `signals.yaml`. It's inside London, so there's nothing new to fetch.

---

## 5. The emails

**Email 1.** Subject: `{n_due} care services in {area} CQC hasn't inspected in years`

> Hi {first_name, or "there"},
>
> I've built a tool that reads the CQC and Companies House registers every week and picks out the care services
> most likely to need a compliance consultant. I'm looking for a handful of consultancies to try it free and tell
> me honestly whether it's useful.
>
> Right now in {area}, {n_due} care services have a CQC rating that's 4 or more years old, or have waited over a
> year for their first inspection, and CQC is working through the oldest first. For example:
> - {example 1}
> - {example 2}
> - {example 3}
>
> In the last 4 weeks {area} also had {n_poor} new poor ratings and {n_new} newly registered services.
>
> If you'd like the full list for your area (every service, with phone, website and how long it's waited), reply
> "yes" and tell me which boroughs you cover. I'll send it today, free, with the next 4 Monday updates. All I ask
> in return is a few words on whether it helped.
>
> What it looks like: {website}/sample.html
>
> {your full name}
>
> *I found {company}'s address on your website. If you'd rather not hear from me, reply "no thanks" and I won't
> contact you again. How I use data: {website}/privacy.html*

**Follow-up** (once, 5 days later, in the same thread)

> Hi {first_name, or "there"}, just checking this reached you. Happy to send the {area} list if it's useful: just
> reply "yes". If not, no problem at all, and I won't email again.

**Check-in** (after their second digest)

> Quick question: reply with a number.
> 1 = I've contacted some of these services
> 2 = useful, but I haven't used it yet
> 3 = not useful for me
>
> And one thing you'd change?

**The money question** (with their last free digest)

> That's your last free digest; thank you for trying it. One honest question before I decide whether to carry on:
> if this were £149 a month for your area, with no more than 2 consultancies per area, would you:
> A) pay for it now,
> B) reserve a founding place at that price (nothing to pay yet), or
> C) not pay for it? If C, what would change your mind: price, area, the leads themselves?

---

## 6. The result: when to spend money

Count after week 4, from about 70 emails:

| Signal | Invest (go to the 8-week plan) | Rethink | Stop |
|---|---|---|---|
| Said "yes" to the free list | 6 or more (about 8%+) | 3–5 | 2 or fewer |
| Check-in answer "1" (used it) | 3 or more | 1–2 | none |
| Money question answer A or B | **2 or more** | 1 | none |

- **Invest** when the money row says so. Then spend on the things that save you time: your own domain and email,
  and the automation (Milestone 6). If you stay companies-only, you may never need the ICO fee.
- **Rethink:** change **one** thing and email 30 more consultancies. Options:
  - a different subject line;
  - a narrower offer (one borough);
  - a different buyer (care software, training or recruitment firms, using the side-test email in
    `8-week-trial-plan.md`).
- **Stop:** you've spent £0 and about 8 hours, and you know.

---

## 7. Every free option considered

| Option | Cost | Verdict |
|---|---|---|
| Personal emails from free Gmail, drafted by Claude | £0 | **Yes: the main channel.** Keep it under 20 new emails a day and never use bulk-mailing add-ons; that keeps Gmail happy. |
| Real numbers and examples in every email, plus a free list on reply | £0 | **Yes.** This is what makes it more than a cold email. |
| Free Netlify website with a live sample page and privacy notice | £0 | **Yes.** It's also where the privacy notice for the people you email lives. |
| Companies-only mode instead of the ICO fee | £0 | **Yes**, for about 1–2% fewer leads. |
| LinkedIn post: "83.5% of homecare services have no current CQC rating; I built a list for London. Comment 'list' for your borough." | £0 | **Optional, and worth one post.** Anyone who contacts you first can have the list, including sole-trader consultants, whom you mustn't cold-email. |
| Posting in Facebook or LinkedIn groups for CQC consultants and care managers | £0 | Optional. Check each group's rules on promotion first. |
| A free weekly newsletter (Substack) of CQC rating trends | £0 | Later. It builds an audience but takes months. |
| Phone calls | £0, but you must check every number against TPS/CTPS | No: more work, and you asked for email. |
| Your own domain and Google Workspace | about £15 for 2 months | After the test passes. |
| Bought email lists or data | £100s | No: cost, and a GDPR risk. |
| Paid ads, cold-email software, LinkedIn Sales Navigator | £30–£100+ a month | No. |
| Letters by post | about £1 each | No. |
