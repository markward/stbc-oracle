# OracleGame -- Game module for the oracle.  Python 1.5.
# Mirrors QuickBattle/QuickBattleGame.py step for step (reusing its music
# setup); diverging from it earned an access violation on the first frame.
import App

def Initialize(pGame):
    import Oracle.OracleLog
    Oracle.OracleLog.mark("game_initialize", "1")
    import QuickBattle.QuickBattleGame
    QuickBattle.QuickBattleGame.SetupMusic(pGame)
    import LoadTacticalSounds
    LoadTacticalSounds.LoadSounds()
    Oracle.OracleLog.mark("game_setup", "music+sounds")
    # ArtificialIntelligence_LogAITree: armed after an AI exists it kills the
    # process silently; armed here, before the episode, it stalls the boot at
    # this point.  Left wired for a future build, off by default.
    try:
        App.g_kConfigMapping.LoadConfigFile("oracle_in.cfg")
        if App.g_kConfigMapping.GetStringValue("OracleIn", "ai_log") == "1":
            App.ArtificialIntelligence_LogAITree("AITree.txt")
            Oracle.OracleLog.mark("ai_log_armed", "AITree.txt")
    except:
        Oracle.OracleLog.mark("ai_log_arm_error", Oracle.OracleLog.exc())
    App.g_kSetManager.ClearRenderedSet()
    pGame.LoadEpisode("Oracle.OracleEpisode")

def Terminate(pGame):
    import DynamicMusic
    DynamicMusic.Terminate(pGame)
    App.g_kSetManager.DeleteAllSets()
