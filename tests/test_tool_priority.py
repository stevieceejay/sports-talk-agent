from agent import SportAgent


def test_tool_priority_prefers_db_then_live_then_search():
    agent = SportAgent()
    assert agent._tool_priority_hint("Who do the Rams play next weekend?")
    assert agent._tool_priority_hint("Who do the Rams play next weekend?").startswith("get_team_schedule")
    assert "search_web" in agent._tool_priority_hint("Who do the Rams play next weekend?")


def test_search_tool_is_registered():
    agent = SportAgent()
    names = [tool["name"] for tool in agent.tools]
    assert "search_web" in names
