from typing import List
from mafia import PlayerName

# Remember that you can use your body and face to express yourself. Put your actions between asterisks to do this. For example, '*nods*', '*smirks*', etc..


def get_townsperson_role_prompt(name: str) -> str:
    return f"""
You are {name}, a townsperson trying to identify mafia members.
"""


def get_mafia_role_prompt(name: str, mafia_names: List[PlayerName]) -> str:
    return f"""
You are {name}, a mafia member pretending to be a townsperson. 
The names of all the mafia members, including you, are: {mafia_names}.
"""


def get_intro_phase_prompt(
    role_prompt: str,
    player_names: List[PlayerName],
    current_messages: str,
    player_name: str,
) -> str:
    return f"""
{role_prompt}
The players in the game are {player_names}. 
It's the first day of the game, and the town has just been informed that there are mafia hiding among you. The beloved mayor of the town, Mayor Wyatt, was killed yesterday by mafia. Everyone must make a case for why they should be trusted and are not mafia.
{current_messages}

It's your turn to introduce yourself as {player_name}. 
Make a compelling case for who you are, and why you should be trusted and are not mafia. Give a specific alibi for what you were doing yesterday. Be strategic. Mention also if you noticed anything suspicious yesterday related to the mayor's death, especially in relation to specific participants in the game. 
"""


def get_day_vote_phase_prompt(
    role_prompt: str,
    alive_players: List[PlayerName],
    eliminated_players: List[PlayerName],
    knowledge_base: str,
    player_name: str,
) -> str:
    return f"""
{role_prompt}
The current alive players are: {alive_players}. 
The eliminated players are: {eliminated_players}. 
Your accumulated knowledge from previous phases: {knowledge_base}
It's time to vote. Choose ONE player (not yourself) to eliminate who you suspect is a mafia member. 
Use your accumulated knowledge to make an informed decision. 
You CANNOT vote for yourself ({player_name}). 
Please respond with ONLY the name of the player you want to eliminate. You MAY NOT abstain.
"""


def get_day_discussion_phase_prompt(
    role_prompt: str,
    player_names: List[PlayerName],
    alive_players: List[PlayerName],
    eliminated_players: List[PlayerName],
    knowledge_base: str,
    current_discussion: str,
    day_count: int,
    player_name: str,
) -> str:
    return f"""
{role_prompt}
The players in the game are: {player_names}. 
The current alive players are: {alive_players}. 
The eliminated players are: {eliminated_players}. 
Your accumulated knowledge from previous phases: {knowledge_base}
Current discussion (Day {day_count}): {current_discussion}
It's your turn to speak. Generate a message to contribute to the discussion about who is likely to be mafia. 
Use your accumulated knowledge to make informed decisions. Be specific. 
Propose one or more specific people who might be mafia, and give concrete reasons based on their past behavior. 
If suspicions are being raised about you, make sure to defend yourself.
Remember that you are {player_name}. Focus on game strategy.
"""


def get_night_discussion_phase_prompt(
    player_name: str,
    fellow_mafia: List[PlayerName],
    alive_players: List[PlayerName],
    eliminated_players: List[PlayerName],
    eliminated_mafia: List[PlayerName],
    knowledge_base: str,
    current_messages: str,
) -> str:
    return f"""
You are {player_name}, a mafia member. 
Your fellow mafia members are: {fellow_mafia}. 
The current alive players are: {alive_players}. 
The eliminated players are: {eliminated_players}. 
Of whom, the eliminated mafia members are: {eliminated_mafia}. 
Your accumulated knowledge from previous phases: {knowledge_base}
Current mafia discussion: {current_messages}
Discuss with your fellow mafia members who to eliminate. 
Consider the voting patterns and discussions from previous phases. 
You can only eliminate non-mafia players.
"""


def get_night_vote_phase_prompt(
    player_name: str,
    fellow_mafia: List[PlayerName],
    alive_players: List[PlayerName],
    eliminated_players: List[PlayerName],
    eliminated_mafia: List[PlayerName],
    knowledge_base: str,
    night_count: int,
) -> str:
    return f"""
You are {player_name}, a mafia member. 
Your fellow alive mafia members are: {fellow_mafia}. 
The current alive players are: {alive_players}. 
The eliminated players are: {eliminated_players}. 
Of whom, the eliminated mafia members are: {eliminated_mafia}. 
Your accumulated knowledge from previous phases: {knowledge_base}
It's night {night_count}, and you need to choose one player to eliminate. 
You can choose any alive player who is NOT a mafia member (not yourself or your fellow mafia). 
Please respond with ONLY the name of the player you want to eliminate.
"""


def get_summary_prompt(
    player_name: str,
    role: str,
    phase_type: str,
    day_count: int,
    phase_transcript: str,
    knowledge_base: str,
    fellow_mafia: List[PlayerName],
) -> str:
    prompt = f"""
    You are {player_name}, a {role} in the game. 
    Your current knowledge base is: {knowledge_base}. 

    Here is a transcript of what just happened in {phase_type} {day_count} (when people speak, their speech is enclosed in brackets specifiying their names: <John>Hello</John>):
    {phase_transcript}

    Please update your current knowledge base with any relevant information from the transcript of what just happened in {phase_type} {day_count}.
    Focus on key information that will be useful for future decision making. Be concise. 
    Include specific details about votes, discussions, suspicions, and outcomes.
    Keep track of who you think is mafia and who you think is townsperson. 
    Only you can see this information. 
    If you are a townsperson, you should be focused on identifying mafia members. 
    If you are a mafia member, you should be focused on deflecting suspicion away from you and your fellow mafia and sowing suspicion among the townspeople. 
    Your knowledge base will be replaced with what you return here, so make sure it includes important previous information as well. 
    """

    if role == "mafia":
        prompt += f"\n the names of all the mafia members, including you, are: {', '.join(fellow_mafia)}"
    elif role == "townsperson":
        pass
    else:
        raise ValueError(f"Invalid role: {role}")
    return prompt
