# Launch checklist and automation plan

> **Start with `zero-cost-test.md`** (£0), then `8-week-trial-plan.md` if it shows interest. This checklist is the
> full version for once you're selling.

## Part 1: launch checklist (in this order)

**Foundations (about a week)**
1. **Pick the name.**
   - Check it's free on Companies House (search the register) and that a domain is available, e.g. `.co.uk`.
   - "Care Signals" is only a working name: change `brand` in `~/Signals/business.yaml`.
2. **Decide how you trade.**
   - As a sole trader: register with HMRC for Self Assessment.
   - As a limited company: form it on Companies House (about £50).
   - Either is fine to start. A company keeps the business separate from you.
3. **Pay the ICO data protection fee.**
   - It's required because you process personal data (sole traders' details) for business. It is about £50 a year
     for a micro business; check the current fee at ico.org.uk.
   - Put the reference number in `business.yaml`.
4. **Buy the domain** (about £10 a year) and **set up email on it**, e.g. `hello@yourdomain.co.uk`, with Google
   Workspace or Microsoft 365 (about £5–6 a month). A professional address matters for trust and for email
   delivery.

**Paperwork (an afternoon)**
5. Fill in `~/Signals/business.yaml`: legal name, address, email, website, ICO number and price.
6. Read and sign the **legitimate interests assessment** (`business/legitimate-interests-assessment.md`).
7. Adapt the **customer terms** (`business/customer-terms.md`). A solicitor's check is worth it once you have paying
   customers.

**Website (an hour)**
8. Run `uv run signals site`, then look at the result: `open ~/Signals/site/index.html`.
   - Highlighted [brackets] show anything still missing.
9. **Publish it** for free with **Netlify Drop**:
   - go to app.netlify.com/drop and drag the whole `~/Signals/site` folder onto the page;
   - then, in Netlify, connect your domain under "Domain settings";
   - Cloudflare Pages works too.
   - To update the site: run `uv run signals site` again and drag the folder again.
10. Make a PDF of the **sales sheet**:
    - `open ~/Signals/site/sales-sheet.html`, then **File → Print → Save as PDF**.

**Selling (ongoing)**
11. Take payment with **Stripe**: create a Payment Link for a monthly subscription (£149/month, or your price). No
    website code is needed; paste the link into your trial-ending emails.
12. Contact your first **20–30 prospects** using `business/outreach-emails.md`. Offer the free 4-week trial.
13. For each trial customer:
    - add their area to `~/Signals/signals.yaml`;
    - run `uv run signals backfill --only-new`;
    - send them the Monday digest from `~/Signals/outputs/`, until sending is automated (Part 2).

---

## Part 2: automation (can Claude run an email address?)

Split the work in two:
- **Routine, predictable jobs:** these should be automated with plain code. They're cheap and reliable, and
  never improvise.
- **Conversations with people:** Claude can help with these, with you approving what goes out.

### A. Fully automatic, no AI needed (I can build this next)

| Job | How |
|---|---|
| Send each customer their region's digest every Monday | A `signals send` command: the digest as the email body, the spreadsheets attached, sent from your domain's mailbox. It runs straight after the weekly run. |
| Customer list | `~/Signals/customers.yaml`: name, email, areas, trial or paid, start date. Commands to add, pause and remove customers. |
| Trial reminders | An automatic email in week 3 of a trial, with your Stripe payment link. The digest stops when the trial ends unless the customer is marked paid. |
| Opt-outs | When you run `signals suppress`, every customer who received that lead is emailed automatically, as your terms promise. |
| Prospect list | A weekly list of **newly formed compliance consultancies** from Companies House. They're your best prospects, and the same engine can find them. |

**What you'd need:**
- an email account on your domain (step 4 above), with an "app password" for sending;
- or a sending service such as Postmark or Resend, for better delivery.

It uses Python's built-in email support, so there are no new dependencies. Your Mac still needs to be on (asleep is
fine) on Monday mornings. Alternatively, move the whole thing to a small server (about £5 a month) so it never
depends on your laptop.

### B. Claude-assisted, with you approving

- **Inbox triage and replies:**
  - In the Claude app, connect **Gmail / Google Workspace** (Settings → Connectors). Claude can then read your
    business inbox, summarise new enquiries and **draft** replies (trial set-up, price questions, opt-outs) using
    the templates in `business/outreach-emails.md`.
  - You check each draft and press send.
- **Personalised prospecting:** each week, ask Claude to take the new prospects list and the week's numbers, look up
  each consultancy's website, and draft a tailored first email for each. You review and send them in a batch.
- **Scheduled help:**
  - Claude Code can run a task on a schedule (a "routine"), e.g. every Monday: "summarise this week's digests and
    draft the outreach emails".
  - These run in the cloud, so they need your data somewhere they can reach. That is one more reason to move to a
    small server once you have paying customers.

### C. What should not be fully automated

- **Sending cold sales emails without a person checking them.** PECR and UK GDPR put the responsibility on you:
  - every email must be to the right kind of recipient (companies, not sole traders);
  - it must be accurate;
  - it must honour opt-outs.
  - A human check per batch is cheap insurance.
- **Handling opt-out and data requests.** Automate the mechanics (suppression, notifying customers), but read each
  request yourself.
- **Taking payment decisions:** refunds, disputes.

### Suggested order

1. **Now:** launch checklist steps 1–10, then contact the first prospects by hand.
2. **Next build (Milestone 6):**
   - customer list;
   - automatic Monday emails;
   - trial reminders;
   - opt-out notifications;
   - the prospect list.
3. **Once you have 3–5 paying customers:** move to a small server, and set up Claude with Gmail for inbox triage and
   drafted replies.
