"""HumAID label set and the one prompt every system gets."""

LABELS = {
    "requests_or_urgent_needs": "asks for help or reports urgent needs: rescue, food, water, shelter, medicine",
    "injured_or_dead_people": "reports people injured or killed",
    "missing_or_found_people": "reports people missing, trapped, or found",
    "displaced_people_and_evacuations": "people displaced, evacuations, evacuation orders, shelters",
    "infrastructure_and_utility_damage": "damage to buildings, roads, bridges, power, water or other utilities",
    "caution_and_advice": "warnings, forecasts, safety advice or instructions",
    "rescue_volunteering_or_donation_effort": "rescue operations, volunteering, donation drives or fundraising",
    "sympathy_and_support": "prayers, condolences, emotional support",
    "other_relevant_information": "other disaster information not covered above",
    "not_humanitarian": "not about the disaster or humanitarian response",
}
RESCUE_CRITICAL = {"requests_or_urgent_needs", "injured_or_dead_people", "missing_or_found_people"}

SYSTEM = ("You triage social media posts written during natural disasters for emergency dispatchers. "
          "Classify the post into exactly one category. Answer with the category name only.\n\nCategories:\n"
          + "\n".join(f"- {k}: {v}" for k, v in LABELS.items()))


def build_messages(text, shots=None):
    msgs = [{"role": "system", "content": SYSTEM}]
    for s in shots or []:
        msgs += [{"role": "user", "content": f"Post: {s['text']}"}, {"role": "assistant", "content": s["label"]}]
    return msgs + [{"role": "user", "content": f"Post: {text}"}]


def parse_label(out):
    out = (out or "").strip().lower()
    for k in LABELS:
        if k in out:
            return k
    for k in LABELS:
        if k.split("_")[0] in out:
            return k
    return "other_relevant_information"
