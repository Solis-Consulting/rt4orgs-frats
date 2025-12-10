# subtam_descriptions.py

SUBTAM_DESCRIPTIONS = {
    # --- Interest ---
    "light_interest": "User shows mild interest. Responses like 'ok', 'sounds good', 'sure'.",
    "strong_interest": "User is very interested. Expressions like definitely, really want this.",
    "confused_interest": "User sounds unsure, confused but maybe open to learning more.",
    "want_proof": "User wants proof or verification before moving forward.",
    "want_numbers": "User wants quantity or statistical information.",

    # --- Questions ---
    "pricing_question": "User is asking for pricing information.",
    "deliverable_question": "User is asking what specifically they receive.",
    "timeline_question": "User is asking about delivery speed or time required.",
    "data_source_question": "User is asking where data is pulled from.",
    "accuracy_question": "User is asking about data accuracy.",
    "volume_question": "User is asking how many names or how large the list is.",
    "refund_question": "User is asking about refunds.",
    "custom_request_question": "User has a specific customized request.",

    # --- Pricing ---
    "asks_for_price": "User is asking how much it costs or what the price is.",
    "negotiates_price": "User is trying to negotiate, haggle, ask for discounts.",
    "bulk_price_question": "User is asking for price for multiple chapters.",
    "confused_about_tiers": "User is confused about pricing tiers.",

    # --- Objections ---
    "price_too_high": "User believes price is too expensive.",
    "no_time": "User claims to be too busy.",
    "not_interested": "User rejects offer, uninterested.",
    "already_have_list": "User says they already have a list.",
    "send_info_only": "User wants information but not engaging right now.",
    "who_are_you": "User questions legitimacy or identity.",
    "sketchy_vibes": "User thinks the situation seems suspicious.",
    "long_delay": "User delayed heavily or hasn't responded.",

    # --- Demo ---
    "asks_for_example_list": "User wants an example list or preview.",
    "asks_for_specific_name": "User wants particular person from example.",
    "wants_chapter_preview": "User wants preview specific to their chapter.",
    "asks_for_pdf": "User wants downloadable PDF sample.",

    # --- Link Actions ---
    "clicked_purchase_link": "User clicked purchase link.",
    "clicked_example_link": "User clicked example link.",
    "clicked_site": "User clicked general site link.",

    # --- Purchase ---
    "confirmed_payment": "User has paid and confirms.",
    "sent_venmo": "User sent a Venmo payment.",
    "waiting_on_exec_board": "User is waiting on executive board approval.",
    "wants_invoice": "User wants formal invoice.",

    # --- Follow-up & Terminal ---
    "followup_24hr": "System should follow up in 24 hours.",
    "followup_10day": "System should follow up in 10 days.",
    "dead": "Conversation permanently dead.",

    # --- Buy Signals ---
    "buy_signal": "User expresses clear intent to purchase.",
    "ready_to_pay": "User wants to pay right now.",
    "send_payment_info": "User asks how to pay.",
    "how_fast_can_you_deliver": "User wants speed of delivery, strong intent.",

    # --- Stall ---
    "later": "User asks to follow up later.",
    "busy_now": "User is busy and postponing.",
    "checking_with_exec_board": "User is consulting chapter exec board."
}
