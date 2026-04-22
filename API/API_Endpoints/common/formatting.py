def format_team_name(team_id: str) -> str:
    if not team_id:
        return ""

    special = {
        "rb": "RB",
    }
    if team_id in special:
        return special[team_id]

    return team_id.replace("_", " ").title()
