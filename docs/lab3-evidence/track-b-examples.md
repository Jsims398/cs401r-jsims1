# Track B — Examples and Failure Cases

Judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0`, `max_tokens=4096` (raised from the starter harness's unset default — see `evaluation/run_track_b.py`; the default caused `LLMDidNotFinishException` on 11 of 12 faithfulness calls in an initial run).
Generator model: same model, via `rag/generate.py`.
Query strategy: `hybrid` (see `docs/lab3-evidence/query-strategy-comparison.csv` for why).
Scores below are from the single-run `docs/lab3-evidence/rag_eval_with_profile.csv` (profile-context injection on — the configuration used for the graded run).

## Correct Examples

All five pass every hard requirement in the prompt templates' own checklist: no offer claims free expedited shipping, none implies final-sale merchandise is returnable, the Platinum example doesn't lead with a discount percentage, none claims a benefit above the customer's actual tier, and each includes an incentive + a known category + a call to action.

### Example 1 — CUST-10000317 (Gold, mostly online, Outdoor/Footwear)
**Profile:** churn_probability=0.81, total_lifetime_value=$3,120.40, avg_order_value=$186.25, online_to_store_ratio=0.72
**Retrieved chunks:** POL-SHP-007-2, POL-LOY-011-2, POL-LOY-011-6, KB-FAQ-022-3, KB-FAQ-022-5, POL-SHP-007-5
**Generated offer:**
> Subject: Your Gold Free Returns + Early Access to New Outdoor Gear
>
> Body: We've noticed it's been a while since your last visit, and we'd love to welcome you back. As a Gold member, you currently receive free return shipping on all orders—a benefit that makes trying new outdoor gear and footwear risk-free. This week, you'll get 24-hour early access to our upcoming seasonal sale, giving you first pick on the categories you love most. Shop online or visit a store by [DATE] to claim your early access and rediscover why Gold members save time and money on every purchase.

**Scores:** faithfulness=0.267, answer_relevancy=0.384, context_recall=1.000
**Why it's correct:** conditional phrasing ("As a Gold member, you currently receive..."), both cited benefits (free return shipping, 24-hour early access) are real Gold entitlements per POL-LOY-011 §4, no invented numbers.

### Example 2 — CUST-10000904 (Bronze, mostly in store, Apparel)
**Profile:** churn_probability=0.74, total_lifetime_value=$312.80, avg_order_value=$41.15, online_to_store_ratio=0.20
**Retrieved chunks:** POL-SHP-007-2, POL-LOY-011-2, KB-FAQ-022-3, KB-FAQ-022-5, POL-LOY-011-6, POL-SHP-007-5
**Generated offer:**
> Subject: Your $10 bonus points are waiting—plus a fresh look at fall apparel
>
> Body: We've noticed it's been a couple of months since your last visit, and we'd love to welcome you back. As a Bronze member, you're earning 1× points on every purchase, and we're adding a one-time **10 bonus points** ($0.50 in value) when you shop apparel in the next 14 days—your favorite category.

**Scores:** faithfulness=0.238, answer_relevancy=0.339, context_recall=0.200 (lowest of the 4 cases)
**Flagged for discussion:** correctly states Bronze's 1x points rate and never claims a higher-tier benefit, but invents a specific "10 bonus points ($0.50)" mechanic that appears nowhere in policy — see Failure 1. The low context_recall is explained in Failure 2 below: the retrieval strategy never surfaces POL-RET-004, so the ground truth's required fact (Bronze pays $7.95 for returns) was never available to ground against.

### Example 3 — CUST-10000122 (Platinum, mixed channel, Outdoor/Electronics/Home)
**Profile:** churn_probability=0.66, total_lifetime_value=$8,940.00, avg_order_value=$447.00, online_to_store_ratio=0.55
**Retrieved chunks:** POL-SHP-007-2, POL-LOY-011-2, POL-LOY-011-6, KB-FAQ-022-3, KB-FAQ-022-5, POL-SHP-007-5
**Generated offer:**
> Subject: Your $100 Gear Credit Expires Soon — Plus Early Access to Our Outdoor Sale
>
> Body: As a Platinum member, you have an unused $100 gear credit waiting in your account through December 31—and we'd love to see you put it toward the outdoor and electronics gear you love. This Friday, you'll get 48-hour early access to our biggest seasonal sale, giving you first pick on premium outdoor equipment and home essentials before they sell out.

**Scores:** faithfulness=0.222, answer_relevancy=0.286, context_recall=0.333
**Why it's correct:** leads with recognition (the real, unused $100 annual gear credit from POL-LOY-011 §4.1) rather than a discount percentage, exactly per the lab's Platinum guidance; 48-hour early access is a real Platinum entitlement (correctly attributed, unlike Failure 2 below where the same number is misattributed to Gold).

### Example 4 — CUST-10000588 (Silver, near Gold threshold, Home/Beauty)
**Profile:** churn_probability=0.70, total_lifetime_value=$1,985.00 ($15 under the Gold threshold), online_to_store_ratio=0.61
**Retrieved chunks:** POL-SHP-007-2, POL-LOY-011-2, KB-FAQ-022-5, POL-LOY-011-6, POL-SHP-007-5, KB-FAQ-022-3
**Generated offer:**
> Subject: Your Silver Rewards Are About to Reset—Earn 25% More Points This Week
>
> Body: As a Silver member, you currently earn 1.25× points on every purchase, and this week we're giving you a bonus: earn an extra 25% on top of your points when you shop Home or Beauty—two categories where you've found great gear before.

**Scores:** faithfulness=0.286 (highest of the 4), answer_relevancy=0.394, context_recall=1.000
**Flagged for discussion:** correctly states only Silver benefits and never implies Gold benefits are already active (the near-threshold trap the handout specifically warns about) — but invents a "25% extra points" bonus, the same fabrication pattern as Example 2; see Failure 1.

### Example 5 — CUST-10099002 (Silver, mostly online, Apparel/Beauty — not in `OFFER_TEST_CASES`)
**Profile:** churn_probability=0.72, total_lifetime_value=$980.00, avg_order_value=$95.00, online_to_store_ratio=0.85
**Retrieved chunks:** POL-SHP-007-2, POL-LOY-011-2, KB-FAQ-022-5, POL-LOY-011-4, POL-SHP-007-5, KB-FAQ-022-3
**Generated offer:**
> Subject: Your Silver member early access + bonus points on apparel—starts tomorrow
>
> Body: We've noticed it's been 60 days since your last visit, and we'd love to welcome you back. As a Silver member, you currently receive 1.25× points on every purchase and 12-hour early access to our upcoming sale—both benefits that work especially well for apparel shoppers like you.

**Scores:** not in `OFFER_TEST_CASES`, no RAGAS ground truth exists for this ad hoc profile — included only to show the pattern holds outside the 4 built-in cases.
**Why it's correct:** real Silver entitlements only (1.25× points, 12-hour early access), no invented bonus quantity this time ("bonus points on your next order" is vague rather than fabricated-specific), conditional phrasing maintained.

## Failure Cases

### Failure 1 — Invented promotional specifics not grounded in retrieved context
**What went wrong:** 2 of the 5 sampled generations (Examples 2 and 4) invent a concrete numeric incentive that appears nowhere in the policy corpus or `TIER_GUIDELINES`: a "10 bonus points ($0.50)" mechanic for a Bronze customer, and a "25% extra points" bonus for a Silver customer. Neither number exists anywhere in `northstar-policy-docs/` or the static tier guidelines block. This is exactly what the system prompt's Constraints section and `GUARDRAILS` explicitly forbid ("Never invent a promotion, discount code, price, or product") — prompt instructions alone did not stop it.
**Why:** the model is asked to "create urgency" and given real tier facts (points rate, early access hours) but no explicit list of *allowed* incentive mechanics, so when a generic "we're giving you a bonus" framing feels natural, it fabricates a specific number to make the copy concrete, rather than reusing only the documented rate/threshold facts already in context.
**Proposed fix:** add a deterministic post-generation check: extract every number adjacent to a percent sign, dollar sign, or the word "point(s)"/"bonus" from the generated answer, and verify each one appears verbatim in the retrieved contexts or the static `TIER_GUIDELINES` text. Flag (or regenerate) any answer where a number fails that check, rather than relying on the prompt instruction alone to prevent fabrication.

### Failure 2 — Cross-tier benefit leakage
**What went wrong:** a live run on a Gold customer (CUST-10099001, shopping mostly in store for Electronics/Home — not in `OFFER_TEST_CASES`, generated via `scripts/extra_example_rag.py`) produced: *"we're extending an exclusive preview: shop our latest electronics and home goods starting tomorrow at 6 AM ET—48 hours before the general public."* 48-hour early access is a **Platinum-only** benefit per `POL-LOY-011 §4` / `TIER_GUIDELINES`; Gold is entitled to 24 hours. This directly violates "Never promise a benefit belonging to a tier above the customer's own," stated in both the system prompt's Constraints and in `GUARDRAILS`.
**Why:** same root cause as Failure 1 — the model is told the rule in two places but nothing checks its output against it. Unlike the invented-number case, this failure is specifically dangerous because the fabricated claim corresponds to a *real* benefit (just the wrong tier's), making it read as entirely plausible and harder to catch by eye.
**Proposed fix:** extend the Failure 1 validator into a structured claims check: extract tier-benefit-shaped phrases (hour counts next to "early access", day counts next to "return window", dollar amounts next to "gear credit") from the answer, look up what the customer's actual tier is entitled to in `TIER_GUIDELINES`, and reject any answer where the stated value doesn't match the customer's own tier's row in the benefits table. This is a stronger, tier-aware version of the same post-generation fact-check as Failure 1, and the two fixes should ship together rather than as two separate systems.
