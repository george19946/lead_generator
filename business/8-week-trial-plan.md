# 8-week trial plan: does anyone pay for this?

> **Phase 2. Do `zero-cost-test.md` first.** This plan spends about £70, so use it only once the £0 test shows
> interest. If you stay in companies-only mode, you can probably drop the ICO fee from the budget below (check with
> the ICO's free self-assessment).

**Dates:** set up Thu 24 Sep – Sun 4 Oct 2026, then 8 weeks from Mon 5 Oct to Sun 29 Nov. Decide on Mon 30 Nov.
**Cash:** about £70. **Your time:** about 15 hours in total, most of it in the set-up week.
**Everything runs by email.** You don't need calls, meetings, ads or LinkedIn.

---

## 1. What we're testing, and how we'll decide

Four questions, each with a number that answers it:

| Question | Measured by | Good | Weak |
|---|---|---|---|
| **Want:** do consultancies want the leads? | Emailed prospects who reply "yes" to the free offer | 8% or more | under 4% |
| **Use:** do they act on them? | Trial users who say they contacted at least one lead (week-2 check-in) | half or more | under a quarter |
| **Pay:** will they pay full price? | Paying customers by Sun 29 Nov | 3 or more | none |
| **Who else?** Would bigger buyers pay? | Positive replies from 20 care suppliers (side test) | 2 or more | none |

**The decision on Mon 30 Nov:**
- **Go:** 3 or more paying. Keep going, raise the number of prospects, and move the job to a small server.
- **Fix and retest for 4 weeks:** people used it and liked it, but 0–2 paid. Read their answers to "what would make
  it worth paying?" and change one thing: price, area size, or which lists are included.
- **Change the buyer:** consultancies didn't reply, but the side test did. Rerun this plan for that buyer.
- **Stop:** weak on Want and Use. You'll have spent about £70 and 15 hours, and you'll know.

---

## 2. Budget

| Item | Cost | Why |
|---|---|---|
| Domain name (.co.uk) | about £5–£10 for the first year | A professional address. People trust it more and your email is less likely to land in spam. |
| Google Workspace Business Starter | £7 + VAT a month, with a 14-day free trial: **about £12** for the trial period | Your business email, which the automation sends from. Claude can also read it and draft your replies. |
| ICO data protection fee | **£47** a year by direct debit (£52 otherwise) | Required by law (see the note at the end) |
| Website hosting (Netlify) | free | |
| Payments (Stripe Payment Links) | free to set up; about 1.5% + 20p per card payment | Customers pay by card. You don't need a website shop. |
| Claude | your existing subscription | Drafts replies and finds prospects' email addresses |
| **Total** | **about £65–£75** | |

**Not needed for the trial:**
- a limited company: trade as a sole trader under your brand;
- a solicitor;
- ads;
- bought data;
- cold-email software;
- a server.

---

## 3. How it runs: the machine

```
Prospect list ──► 3 automatic emails ──► "Yes, send my list" ──► free trial starts
(Companies House       (max 25 a day,          (one command          │
 + Claude finds         stop on any reply)      from you)            ▼
 the emails)                                              Monday digest emailed automatically ×4
                                                          + check-in after week 2 ("did you use it?")
                                                          + "trial ends next week" with payment links
                                                          + one-question "why not?" if they don't pay
                                   ──► Every Monday you get a scoreboard email
```

**What's automated.** I build this next (Milestone 6); it's one build session:
- `signals prospects`: a list of CQC consultancy companies from Companies House. It shows only limited
  companies and LLPs, which you're allowed to email, and counts how many are in each region.
- `signals outreach`: sends the 3-email sequence to the prospects you've approved.
  - At most 25 new emails a day, and only on weekdays.
  - It checks your inbox and stops emailing anyone who replies.
  - It never emails anyone on the do-not-contact list.
- `signals customer add`: starts a free trial with one command. It sends a welcome email, the free
  "due for inspection" list for their area, and the terms.
- `signals send`: runs straight after the Monday job. It emails every trial or paying customer their
  digest, and sends the check-in, trial-ending and "why not?" emails on schedule.
- **Scoreboard email to you every Monday:**
  - prospects emailed, replies and trials;
  - check-in answers;
  - paying customers and monthly revenue.
- **Optional, and recommended:** a daily Claude routine that reads new replies at 8am and writes a draft
  answer for each in your Gmail Drafts. You open Gmail, check each draft and press send.

**What stays with you** (it keeps you legal and takes minutes):
- approving the prospect list once;
- pressing send on replies;
- typing one command when someone says yes;
- marking customers as paid.

---

## 4. Week 0: set-up (Thu 24 Sep – Sun 4 Oct, about 5 hours)

**A. Accounts (about 1½ hours)**
1. **Choose the name**, then check that the .co.uk domain is free.
2. **Google Workspace.** Sign up for Business Starter at workspace.google.com (14-day free trial) and buy the
   domain through it; that's the simplest route. Create `hello@yourdomain.co.uk`.
   - In the Admin console, turn on **DKIM**: Apps → Google Workspace → Gmail → Authenticate email. This stops
     your emails landing in spam.
   - Turn on 2-step verification, then create an **app password** for the automation.
3. **ICO fee.** Pay at ico.org.uk ("Pay the data protection fee"), by direct debit (£47). Note your ZA… number.
4. **Stripe.** Create an account. Make two **Payment Links**, each a monthly subscription: "Your area,
   £149/month" and "Your area, exclusive, £249/month".

**B. Paperwork and website (about 1 hour)**
5. Fill in `~/Signals/business.yaml`:
   - name, address, email, website and ICO number;
   - `places_per_area: 2`;
   - `exclusive_price: 249`.

   If you are **not** VAT-registered, change `price_note` to "per area, per month. No VAT. Cancel any time."
6. Sign and date the LIA (`business/legitimate-interests-assessment.md`) and save it as a PDF.
7. Run `uv run signals site`, then drag `~/Signals/site` onto app.netlify.com/drop. In Netlify, connect your
   domain; Netlify shows the DNS records to add in Google's domain settings.

**C. The automation (about 1 hour, after I've built it)**
8. Update the code (drag out the old code folder, unzip the new one, `uv sync`), then run
   `uv run signals keys` to add the email app password.
9. Send yourself a test digest: `uv run signals send --test`.
10. In the Claude app, connect **Gmail** (Settings → Connectors) with the new Workspace account.

**D. Areas and prospects (about 1½ hours)**
11. Run `uv run signals prospects` to list the consultancies and see which regions have the most.
12. Choose **3 regions**: London (already loaded) plus the two others with the most prospects. Then:
    - add those two regions to `signals.yaml`;
    - run `uv run signals backfill --dry-run --only-new` to see how many API calls it needs and how long;
    - then run `uv run signals backfill --only-new` (it runs unattended, roughly 30–60 minutes per region).
13. **Find the email addresses with Claude.** In the Claude app, with web search on, attach `prospects.csv` and
    paste:
    > For each company in this file, find its website and the business email address published on that website
    > (a contact, info or hello address, or a named person's address at the company's own domain). Only use
    > addresses the company publishes itself; never guess one. Add columns `website`, `email`, `first_name` (if a
    > person is named) and `source_page` (the page where you found the email). Leave the email blank if you can't
    > find one. Return the CSV.

    Save the result as `~/Signals/prospects.csv`. Then top it up by searching Google for
    "CQC consultant [region]" and adding any **Ltd or LLP** consultancies it finds.
    **Target: 150 consultancies with an email address.**
14. **Approve the list.** Open `prospects.csv`, delete anything that isn't a CQC consultancy, and type `yes` in the
    `approved` column for the rest. Only approved rows are ever emailed. This is the one human check.
15. **Side test.** Add 20 rows with `segment` set to `supplier`. Choose from:
    - care software companies (for example Birdie, Log my Care, Nourish, CareLineLive);
    - care training providers, care recruitment agencies and care insurance brokers.

    They get the supplier email (section 7).

---

## 5. The 8 weeks

| Week | Dates | Happens automatically | You do | Your time |
|---|---|---|---|---|
| 1 | 5–11 Oct | 50 consultancies get Email 1 (Tue–Thu). First Monday digests for any trials. Scoreboard. | Check Claude's drafts in Gmail; send. For each "yes": `signals customer add`. | 1½–2 h |
| 2 | 12–18 Oct | Next 50 get Email 1; the first 50 get Email 2. Trials get their digests. | As week 1. | 1½–2 h |
| 3 | 19–25 Oct | Last 50 get Email 1; follow-ups continue; the 20 suppliers get their email. **Outreach closes Fri 23 Oct**, so every trial has its 4 weeks before 29 Nov. | As week 1. | 1½–2 h |
| 4 | 26 Oct–1 Nov | Last follow-ups. Week-2 check-in email to early trials. | Reply to check-in answers (drafted). | 45 min |
| 5 | 2–8 Nov | Digests. Check-ins. First "trial ends next week" emails with both payment links. | Mark payers: `signals customer paid NAME`. | 30–45 min |
| 6 | 9–15 Nov | Digests. More trial endings. "Why not?" email to anyone whose trial ended unpaid. | Mark payers; read the "why not?" answers. | 30–45 min |
| 7 | 16–22 Nov | Final trials end (the last Monday digest for a trial started 26 Oct is 16 Nov). | Mark payers. | 30 min |
| 8 | 23–29 Nov | Paid customers keep receiving digests; unpaid trials have stopped. Final scoreboard. | Fill in the decision table (section 1). | 1 h |

**Rules of thumb while it runs:**
- **Reply the same day.** Speed matters more than polish; Claude's drafts make this take seconds.
- **Each week, choose one trial user who replied positively** and ask (by email): "Could I quote you?" and
  "Do you know another consultancy in a different area who'd want this?" Referrals are free prospects.
- **Only change the offer after week 3**, once outreach has closed. Changing it mid-test muddles the numbers.

---

## 6. The offer

- **Free:** the full list of every service in their area that's **due for inspection** (rating 4+ years old, or a
  year without an inspection), plus **4 weekly digests**. No card needed.
- **Then:** £149 a month per area, with at most 2 consultancies per area; or **£249 a month** to have the area to
  themselves. Monthly, cancel any time.
- **Founding customers** (the first 10) keep their price for 12 months and get first pick of their area.
- **"Area"** means the councils they cover or a whole CQC region, whichever they prefer.

The free "due for inspection" list is the hook. It's big, useful the day they get it, and costs you nothing to
produce. Leading with it should get far more replies than "would you like a trial?".

---

## 7. The emails

The automation fills in anything in {braces}. Numbers come from your live data for the prospect's region.

**Email 1 (consultancies).** Subject: `{n_due} services in {region} CQC hasn't inspected in years`

> Hi {first_name or "there"},
>
> CQC is working through its backlog, oldest ratings first. In {region} right now, {n_due} care services have a
> rating that is 4 or more years old, or have waited over a year for their first inspection. Most of them will be
> inspected soon, and many will want a mock inspection first.
>
> I've put the full list together: service, rating, how long it's waited, phone, website and a note on how you
> may contact each one lawfully. Would you like it for {region}? It's free: just reply "yes".
>
> I'll also send you 4 weeks of our Monday digest, covering new poor ratings, newly registered services and new
> care companies in your area, so you can see if it's worth keeping. Sample: {website}/sample.html
>
> Best wishes,
> {your_name}, {brand}
>
> *{brand} is a trading name of {legal_name}. We found {company} on Companies House. Reply "no thanks" and I won't
> contact you again.*

**Email 2** (4 days later, same thread). Subject: `Re: …`

> Hi {first_name or "there"}, a quick nudge in case this got buried. In the last 4 weeks in {region}, {n_poor_4w}
> services were newly rated Requires improvement or Inadequate and {n_new_4w} registered with CQC. Shall I send you the
> free due-for-inspection list? Just reply "yes". *Reply "no thanks" to stop.*

**Email 3** (a week after Email 2). Subject: `Re: …`

> Hi {first_name or "there"}, I won't email again. If the list would help at any point, just reply "yes" and it's
> yours. All the best, {your_name}

**Supplier email (side test).** Subject: `New CQC registrations each week, for {company}'s sales team`

> Hi {first_name or "there"},
>
> Every week in England, new care services register with CQC, new care companies are formed, and services
> become due for inspection. They're usually a care supplier's best prospects. {brand} lists them every Monday
> (England-wide or by region) as spreadsheets with phone, website and legal form.
>
> Would a free 4-week trial be useful to your sales team? Just reply "yes". Sample: {website}/sample.html
>
> {your_name}, {brand}. *Reply "no thanks" and I won't contact you again.*

**Automatic customer emails** (sent by `signals send`):

1. **Welcome** (straight away). This attaches the due-for-inspection list and links the terms:
   "Here's your list. Your first Monday digest arrives on {date}; your trial covers 4 digests."
2. **Check-in** (after digest 2):
   "Quick question. Reply with a number:
   1 = I've contacted some of these leads;
   2 = useful but not used yet;
   3 = not useful for me.
   Anything you'd change?"
3. **Trial ends next week** (with digest 3). It includes both payment links and the founding-customer terms,
   and says: "If you'd like to keep it, pick one. Otherwise do nothing and it simply stops."
4. **Last trial digest** (with digest 4): the same links; "this is your last free digest."
5. **Why not?** (the Monday after an unpaid trial ends):
   "One question, and then I'll leave you alone: what would have made it worth paying for?
   (Price, area, the leads themselves, or just not the right time?)"

---

## 8. Staying legal (already built in)

- **Email only limited companies and LLPs.** `signals prospects` only lists these. For anything you add by hand,
  check it says "Ltd" or "LLP".
- **Every email says who you are** (brand, legal name) and has a one-line opt-out. The website has a privacy
  notice and an opt-out page.
- **"No thanks" means never again.** The outreach tool adds them to the do-not-contact list automatically.
- **Customers get the terms** with the welcome email (`business/customer-terms.md`, published on the site).
- **Opt-outs from people listed in the leads:** run `uv run signals suppress ID`.

---

## 9. If something goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| Almost no replies by the end of week 1 (0–1 from 50) | Landing in spam, or the wrong subject | Send a test to a Gmail and an Outlook address. Check DKIM is on. Try the other subject line in week 2. |
| Replies, but people say "no" | Wrong people on the list | Check the list: are they really CQC consultancies? Are they small, and in areas we cover? |
| Trials start but nobody uses them | Leads are too few or not relevant | Offer a wider area, or ask what they'd want instead (check-in answers). |
| People use it but won't pay £149 | Price or area | Offer £99 for one smaller area to the next group. Only change the price after week 3. |
| Your Mac was off on Monday | The weekly job didn't run | Run `uv run signals run` and `uv run signals send` when it's back on; digests are the same whenever they're made. |

---

## Note: why the ICO fee is on the list

- **It's the law, not a stage decision.** Anyone who handles personal data for a business must pay the fee, unless
  an exemption applies. Your digests include **sole traders' names and contact details**, and you pass them to
  customers. The exemptions (for example, only marketing your own business, or only keeping your own accounts)
  don't cover selling lead data.
- **It's cheap next to the alternative.** The fee is £47 by direct debit. Not paying risks a £400 fixed penalty.
- **People check.** Anyone can look you up on the public ICO register, and a data business with no entry looks
  wrong. If a sole trader ever complains, it's the first thing the ICO checks.
- **The website needs the number.** Your privacy notice shows your ICO number.
- **If you'd rather wait:** we could run the trial on **companies only**, leaving out every sole trader and
  partnership, so that almost no personal data is handled. That removes a small part of the market. I'd still
  just pay the £47.
