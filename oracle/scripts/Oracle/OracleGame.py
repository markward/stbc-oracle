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
    App.g_kSetManager.ClearRenderedSet()
    pGame.LoadEpisode("Oracle.OracleEpisode")

def Terminate(pGame):
    import DynamicMusic
    DynamicMusic.Terminate(pGame)
    App.g_kSetManager.DeleteAllSets()
