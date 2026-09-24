# Legitimate interests assessment (LIA)

**Processing:** the Care Signals weekly lead service
**Controller:** [your legal name, as in `~/Signals/business.yaml`]
**Completed by:** [your name]  **Date:** [date]  **Next review:** [date + 12 months], or sooner if anything below changes

This assessment follows the ICO's three-part test (purpose, necessity, balancing). It is a record of your reasoning,
kept in case the ICO or anyone else asks. It is not legal advice: have it checked if you are unsure.

---

## 1. Purpose test: is there a legitimate interest?

**What we do.** Each week we read two public registers, the Care Quality Commission (CQC) register and Companies
House. We find care services and companies that have just:
- received a poor rating;
- registered with CQC and not yet been inspected; or
- been incorporated with a care activity code.

We sell these lists to CQC compliance consultancies, who may offer those services help.

**Whose interests.**
- **Ours:** running a lawful business.
- **Our customers':** finding organisations that may need their services.
- **The care providers':** well-timed offers of help when they face inspection or have been rated poorly.
- **The public's:** better compliance in adult social care, which is the purpose of CQC regulation in the first place.

**Is it legitimate?** Yes. Direct marketing and business development are recognised as legitimate interests
(UK GDPR Recital 47). The service supports regulatory compliance in a sector where it matters to vulnerable people.

**Would it be unethical or unlawful in any way?** No:
- the data is published by public bodies for transparency;
- we don't collect sensitive data;
- every lead carries its PECR contact rule, so customers can market lawfully.

## 2. Necessity test: is the processing necessary?

**Could we do this without personal data?** Almost entirely. The leads are organisations, and we deliberately:
- **remove** the names of registered managers and nominated individuals before anything is stored;
- **never fetch** company directors or persons with significant control;
- keep only the fields a customer needs to identify and contact the organisation.

The personal data that remains is unavoidable. Some care providers are **sole traders or partnerships**, whose
business name, address and phone number are the name and contact details of a person. Leaving them out would mean
leaving out those providers entirely, which would defeat the purpose for that part of the market.

**Is it proportionate?**
- **Scope:** only adult social care services in the areas customers subscribe to.
- **Frequency:** a weekly change check.
- **Retention:** 12 months, then deleted automatically.

**Less intrusive alternatives considered.**
- Leaving out sole traders entirely: rejected, because it would disadvantage small providers who often need
  compliance help most. Instead they get extra safeguards (below).
- Asking for consent first: impractical, because the providers are not our customers and we have no way to ask
  without contacting them, which is itself processing.

## 3. Balancing test: do the individual's interests override ours?

**Nature of the data.** Business contact details already published on statutory public registers. No special
category or criminal offence data. Ratings concern services, not people.

**Reasonable expectations.**
- CQC and Companies House publish this data so that the public, commissioners and businesses can see it.
- Care providers operate in a regulated, commercial market where compliance consultancies routinely contact them.
- A sole trader running a registered care service would reasonably expect business-to-business approaches about
  CQC compliance.
- They would not reasonably expect repeated or irrelevant contact, or contact after objecting. Our safeguards
  address both.

**Likely impact.**
- Low: at most an unwanted but relevant business approach, which is easy to decline.
- No financial, legal or reputational effect: the ratings are already public.
- No automated decisions with legal or similar effects.

**Vulnerable people?** No. The data subjects are business owners acting in a business capacity, not the people who
receive care.

**Safeguards** (these tip the balance):
1. **Minimisation:** individuals' names within organisations are stripped before storage (see `PRIVACY_NOTES.md` §1).
2. **Contact rules:**
   - every lead is labelled with its PECR rule;
   - sole traders and partnerships are **never** marked "email OK";
   - phone numbers must be screened against TPS/CTPS before calling.
3. **Each lead is sent once**, in the week of the event, not repeatedly.
4. **Easy opt-out:**
   - the website has an opt-out page, and the privacy notice explains the right to object;
   - `signals suppress` erases a person's data at once and blocks them from being added again.
5. **Transparency:**
   - a privacy notice (UK GDPR Article 14) is published on the website;
   - it is linked in the first contact where practical.
6. **Retention:** 12 months, enforced by the weekly `purge`.
7. **Customer terms:** customers must follow PECR, honour objections, and pass opt-outs back to us
   (see `customer-terms.md`).
8. **Security:**
   - data is held on an encrypted computer (FileVault);
   - keys are kept in a file only the account owner can read;
   - the site publishes only anonymised examples, never sole traders.

**Conclusion.** The processing is necessary for a legitimate purpose. With the safeguards above, the impact on
individuals, including sole traders, is low and within their reasonable expectations. Our legitimate interests are
therefore **not overridden**, and we may rely on Article 6(1)(f).

## 4. Actions and review

- [ ] Pay the ICO data protection fee and add the reference to `business.yaml`.
- [ ] Publish the privacy notice and opt-out page (`uv run signals site`) before sending the first digest.
- [ ] Put the customer terms in place before the first customer receives data.
- [ ] Keep a simple log of opt-out requests: the date, the ID and when you confirmed. `signals suppress` records the
      ID and date; add a note with `--note`.
- [ ] Review this assessment every 12 months, or sooner if we add data sources, fields, customers in new sectors,
      or automated emailing.

**Signed:** ______________________  **Date:** __________
