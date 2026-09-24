# Sales outreach: finding and contacting consultancies

> **For the 8-week trial, use the emails in `8-week-trial-plan.md`** (they lead with the free "due for inspection"
> list and are sent automatically). This file is the general guide and the manual versions.

Your customers are **CQC compliance consultancies**: people who help care providers:
- register with CQC;
- prepare for inspections (mock inspections, policies, audits);
- recover from a poor rating.

## Who to contact, and the rules for your own emails

PECR applies to *your* marketing too:

| Prospect | How you may contact them |
|---|---|
| Limited company or LLP (for example, "ABC Compliance Ltd") | Cold email is fine. Say who you are, why you're writing, and give a one-line opt-out. |
| Sole-trader or partnership consultant | **No unsolicited marketing email.** Use LinkedIn, a phone call (check the number against TPS first) or a letter. |

Keep a list of anyone who says "no thanks", and never contact them again.

**Where to find them:**
- Search Google for: "CQC compliance consultant", "CQC registration support", "mock CQC inspection", "care home
  compliance consultancy", and each of those with your area's name.
- Search LinkedIn for people titled "CQC compliance consultant" or "care quality consultant".
- On Companies House, search company names containing "compliance", "care consultancy" or "CQC". Check the company
  type: "Ltd" or "LLP" means cold email is allowed.
- Care-sector events, local care associations' supplier lists, and consultants who advertise mock inspections.

**Start with 20–30 well-chosen prospects in the areas you already have data for**, and send them personal emails,
not a mass mailing.

**Before you start:** run `uv run signals site` for fresh numbers, and `uv run signals sample --region <area>` to
make a sample digest for that prospect's area. Attach the sales sheet PDF, or link to your sample page.

---

## Email 1: introduction

**Subject options:**
- 6 care services in {area} rated poorly in the last month
- New CQC registrations in {area}, weekly
- A lead list for CQC consultants in {area}

> Hi {first name},
>
> In the last four weeks in {area}, {n_poor} care services were rated Requires improvement or Inadequate,
> {n_new} new services registered with CQC, and {n_companies} new care companies were set up. Every one of them
> is a potential client for a consultancy like {their company}.
>
> {Brand} sends you exactly these every Monday: new poor ratings (with the previous rating), newly registered
> services awaiting their first inspection, and brand-new care companies. Each comes with contact details and the
> rule for contacting it lawfully.
>
> Here's an anonymised sample: {website}/sample.html
>
> Would a free 4-week trial for {area} be useful? Just reply "yes" and tell me the area.
>
> Best wishes,
> {your name}
> {Brand} · {website}
>
> *If you'd rather not hear from me again, just reply "no thanks" and I won't contact you again.*

## Email 2: follow-up (4 days later, same thread)

**Subject:** Re: {original subject}

> Hi {first name},
>
> A quick example of what came up in {area} last week: a {service type} in {district} that had been rated Good was
> re-rated Requires improvement. It's the sort of service that usually looks for help with an action plan, and
> you'd have known on Monday.
>
> The first 4 weeks are free, with no card needed. Shall I set you up?
>
> {your name}
>
> *Reply "no thanks" and I won't write again.*

## Email 3: last note (a week later)

**Subject:** Re: {original subject}

> Hi {first name},
>
> I won't keep emailing. If weekly CQC leads for {area} would help at some point, reply to this email and I'll set
> up a free trial.
>
> All the best,
> {your name}

---

## LinkedIn

**Connection note (300 characters):**
> Hi {first name}, I run {Brand}, a weekly list of care services in {area} that have just been rated poorly or
> registered with CQC, made for compliance consultants. Happy to share a free sample if useful.

**Message after they accept:** use Email 1, shortened, with the sample link.

## Phone (screen the number against TPS/CTPS first)

> "Hi, it's {your name} from {Brand}. We send CQC compliance consultants a weekly list of care services in their
> area that have just been rated poorly or just registered with CQC. In {area} last month there were {n_poor} new
> poor ratings and {n_new} new registrations. Is finding new clients something you're working on at the moment?
> … Could I email you a sample and set up a free 4-week trial?"

---

## Replies

**"Yes, interested":**
> Great! Which areas do you cover? A CQC region (for example, London), specific councils, or postcode areas all
> work. Your first digest will arrive next Monday, and the first 4 weeks are free. After that it's £{price} per area
> per month, cancel any time. I've attached our short terms, which include how to handle the contact rules.

After they reply:
1. Add their area as a region in `~/Signals/signals.yaml`.
2. Run `uv run signals backfill --only-new`.
3. Add them to your customer list.

**"How is this different from searching CQC myself?"**
> You could, but you'd need to check every service in your area every week and compare it with last week. We do
> that, add new companies from Companies House (which aren't on CQC yet), follow companies registered at formation
> agents until they reveal where they operate, and label each lead with the PECR contact rule.

**"Too expensive":**
> Totally understand. One new client typically covers many months. Would a smaller area (a few councils rather
> than a whole region) work better?

**"Please remove me" / "no thanks":**
> Of course. I've removed you and won't contact you again. Apologies for the interruption.

Then add them to your do-not-contact list straight away.
