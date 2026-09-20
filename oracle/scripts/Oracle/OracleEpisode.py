# OracleEpisode -- Episode module for the oracle.  Python 1.5.
#
# Loads the REAL Quick Battle mission (QuickBattle.QuickBattle) and lets it
# build the world exactly as it does for a player: bridge, region, model
# preload, player + enemy creation, AI.  Oracle.OracleMission wraps two of
# its functions to inject the scenario and take the ships over afterwards.
# Building a mission of our own reproduced every step in order and still
# access-violated on the first frame; riding the stock mission does not.
import App

def Initialize(pEpisode):
    import Oracle.OracleLog
    import Oracle.OracleMission
    Oracle.OracleMission.install_hooks()
    Oracle.OracleLog.mark("episode_initialize", "hooks installed")
    pMissionStartEvent = App.TGEvent_Create()
    pMissionStartEvent.SetEventType(App.ET_MISSION_START)
    pMissionStartEvent.SetDestination(pEpisode)
    pEpisode.LoadMission("QuickBattle.QuickBattle", pMissionStartEvent)

def Terminate(pEpisode):
    pass
