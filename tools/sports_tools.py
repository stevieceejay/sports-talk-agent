def get_team_info(team):
    team = team.strip()
    if not team:
        raise ValueError("team must not be empty")

    return {
        "team": team,
        "sport": "football",
        "data_status": "mock",
        "message": (
            f"TOOL SUCCESSFULLY CALLED FOR {team}"
        ),
    }