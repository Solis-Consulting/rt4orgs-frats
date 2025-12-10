from __future__ import annotations
from typing import Dict, Any, Optional

# --------------------------
# STATE → REPLY MAPPINGS
# --------------------------

STATE_RESPONSES = {
    # --- Interest ---
    "light_interest": "Gotchu. What are you thinking for spring rush?",
    "strong_interest": "Fire. Want me to show you exactly how many PNMs we can pull for your chapter?",
    "confused_interest": "No worries — quick version: we generate a verified PNM list for your chapter. Want the 10-second breakdown?",
    "want_proof": "Easy — we gave 392 verified names to SAE Nationals at Towson. Want your chapter's preview?",
    "want_numbers": "Totally. For chapters your size we typically pull 150–450 verified PNMs. Want your exact range?",

    # --- Questions ---
    "pricing_question": "For most chapters it's $400–$800 depending on size. Want the exact number for your chapter?",
    "deliverable_question": "You get a verified list: name, photo, year, affiliations, socials, and rush-likelihood score.",
    "timeline_question": "We deliver within hours. How fast do you need it?",
    "data_source_question": "We pull from public socials, enrollment signals, org rosters, and verified engagement. Want the breakdown?",
    "accuracy_question": "We only send verified PNMs — no filler. Want to see the real sample?",
    "volume_question": "Depends on campus size — want your exact predicted range?",
    "refund_question": "If we ever miss delivery or quality, we refund. What’s your concern?",
    "custom_request_question": "Easy — what custom fields do you want included?",

    # --- Pricing ---
    "asks_for_price": "Price depends on chapter size, usually $400–$800. Want your exact quote?",
    "negotiates_price": "We can talk — what budget are you working with?",
    "bulk_price_question": "For multiple chapters we discount hard. How many chapters?",
    "confused_about_tiers": "Basic = list only. Premium = list + segmentation. Want the clean breakdown?",

    # --- Objections ---
    "price_too_high": "Totally get it — what number *would* work for you?",
    "no_time": "All good — I can keep it 10 seconds. What’s the main question?",
    "not_interested": "All good — if anything changes just text me.",
    "already_have_list": "Respect. Ours usually finds 3–5× more than manual lists. Want a quick comparison?",
    "send_info_only": "Sure — here’s the short version: https://rt4orgs.com",
    "who_are_you": "I’m David with rt4orgs — we build rush lists for fraternities nationwide.",
    "sketchy_vibes": "Totally understand — want proof? I can show delivery receipts.",
    "long_delay": "Still here btw — want the TL;DR?",

    # --- Demo ---
    "asks_for_example_list": "Here’s a real chapter example — want one tailored to yours?",
    "asks_for_specific_name": "If he's rush-active we can pull him — want me to run him?",
    "wants_chapter_preview": "I can show predicted volume + sample batch. Want that?",
    "asks_for_pdf": "Easy — want the PDF for your chapter or a generic one?",

    # --- Link Actions ---
    "clicked_purchase_link": "Looks like you're checking it out — want the fast checkout link?",
    "clicked_example_link": "Want the full preview for your chapter?",
    "clicked_site": "Saw you clicked — anything you're curious about?",

    # --- Purchase ---
    "confirmed_payment": "Got it — starting your list now.",
    "sent_venmo": "Received — we'll deliver today.",
    "waiting_on_exec_board": "All good — what do they usually ask?",
    "wants_invoice": "Easy — what's the billing email?",

    # --- Follow-up / Terminal ---
    "followup_24hr": "Yo — still want the spring list?",
    "followup_10day": "Quick check-in — want this for spring rush?",
    "dead": "Copy. I’ll close this out.",

    # --- Buy Signals ---
    "buy_signal": "Say the word and I'll send checkout — want the link?",
    "ready_to_pay": "Perfect — Venmo or card?",
    "send_payment_info": "Easy — want the Venmo or Stripe link?",
    "how_fast_can_you_deliver": "Today if needed. Want me to start now?",

    # --- Stall ---
    "later": "All good — when should I check back?",
    "busy_now": "No stress — want me to ping you later?",
    "checking_with_exec_board": "Totally — what’s the board’s usual concern?",
}


DEFAULT_FAILSAFE = "Got your message — what’s your main question?"


# ------------------------------------
# MAIN RESPONSE GENERATOR
# ------------------------------------

def generate_message(contact: Dict[str, Any],
                     purchased_example: Optional[Dict[str, Any]] = None,
                     template_path=None,
                     intent: Optional[Dict[str, Any]] = None,
                     next_state: Optional[str] = None) -> str:
    """
    The ONLY place outbound replies are generated.
    This now uses next_state → response mapping.
    """

    # 1. If we were not passed an intent or state, fallback to intro message
    if not next_state:
        return (
            f"Hello {contact.get('name')}, we would like to know how "
            f"{contact.get('fraternity')}'s spring rush could be with a FRESH PNM list.\n\n"
            f"See how we gave 392 verified PNMs to SAE Nationals at Towson "
            f"and saved their rush chair DAYS. I'm David with rt4orgs."
        )

    # 2. Look up a mapped reply
    if next_state in STATE_RESPONSES:
        return STATE_RESPONSES[next_state]

    # 3. Fallback
    return DEFAULT_FAILSAFE
