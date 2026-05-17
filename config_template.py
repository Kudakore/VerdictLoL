# Verdict Configuration
# On first run, this template is auto-copied to config.py.
# Edit config.py with your own Riot API key and summoner name.
# Get your key at: https://developer.riotgames.com/
#
# Alternatively, set environment variables or create a .env file:
#   VERDICT_API_KEY=your_key_here
#   VERDICT_REGION=americas
#   VERDICT_PLATFORM=na1
#   VERDICT_GAME_NAME=YourSummonerName
#   VERDICT_TAG_LINE=YourTag

import os

API_KEY = os.environ.get("VERDICT_API_KEY", "YOUR_RIOT_API_KEY_HERE")

REGION   = os.environ.get("VERDICT_REGION", "americas")
PLATFORM = os.environ.get("VERDICT_PLATFORM", "na1")
MY_GAME_NAME = os.environ.get("VERDICT_GAME_NAME", "YourSummonerName")
MY_TAG_LINE  = os.environ.get("VERDICT_TAG_LINE", "YourTag")