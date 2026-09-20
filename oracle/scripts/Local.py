# Local.py -- oracle startup hook.  Imported by the stock Autoexec.py
# (`try: import Local`), so no stock script is modified.  Python 1.5.
#
# Goal: boot stbc.exe straight into Oracle.OracleGame with no movies and no
# menu clicks.  The engine drives MainMenu.mainmenu through a fixed set of
# entry points (LoadConfigPart1 is the first, then PlayOpeningMovies, ...).
# Autoexec runs before the localization manager exists, so MainMenu.mainmenu
# cannot be imported here; instead a real module object full of forwarding
# stubs is planted in sys.modules.  The first stub the engine calls imports
# the real module, patches PlayOpeningMovies, and swaps itself out.
#
# Python 1.5 traps that shaped this file:
#   - no closures: a nested def cannot see its enclosing scope, so the stub
#     is a class instance carrying its name;
#   - a failed `import MainMenu.mainmenu` from here leaves the boot on a
#     black screen (Autoexec swallows the exception);
#   - the engine treats the sys.modules entry as a module (PyModule_GetDict),
#     so it must be a real module object, not an instance with __getattr__;
#   - 1.5's import does not set the `mainmenu` attribute on the MainMenu
#     package when the submodule is already in sys.modules -- set it by hand.
import App
import sys
import new

_cfg = App.g_kConfigMapping
_marks = []

def _mark(key, value):
    try:
        _marks.append((key, str(value)[:180]))
        i = 0
        for k, v in _marks:
            _cfg.SetStringValue("OracleHook", "%02d_%s" % (i, k), v)
            i = i + 1
        _cfg.SaveConfigFile("oracle_boot.cfg")
    except:
        pass

def _exc():
    return "%s %s" % (str(sys.exc_type), str(sys.exc_value))

_mark("local_imported", "1")
_mark("python", sys.version)

GAME_MODULE = "Oracle.OracleGame"
NEW_GAME_DELAY_S = 4.0
# 0: stock movies play and the driver presses ESC to skip them (fully stock
#    engine flow up to the menu).  1: replace PlayOpeningMovies in Python.
SKIP_MOVIES_IN_PYTHON = 0
ET_ORACLE_START = App.UtopiaModule_GetNextEventType()
_started = [0]

def OnDeferredStart(pObject, pEvent):
    if _started[0]:
        return
    _started[0] = 1
    try:
        _mark("deferred_fired", "1")
        pTopWindow = App.TopWindow_GetTopWindow()
        pOptionsWindow = pTopWindow.FindMainWindow(App.MWT_OPTIONS)
        App.Game_SetDifficulty(1)          # QuickBattleHandler does this first
        pNew = App.TGStringEvent_Create()
        pNew.SetEventType(App.ET_NEW_GAME)
        pNew.SetString(GAME_MODULE)
        pNew.SetDestination(pOptionsWindow)
        App.g_kEventManager.AddEvent(pNew)
        _mark("new_game_posted", GAME_MODULE)
    except:
        _mark("deferred_error", _exc())


def _schedule_start():
    """Defer the actual start by a few seconds through a timer whose event
    is handled in Python (OnDeferredStart); a timer that delivers ET_NEW_GAME
    directly is never acted on."""
    try:
        pTopWindow = App.TopWindow_GetTopWindow()
        pOptionsWindow = pTopWindow.FindMainWindow(App.MWT_OPTIONS)
        pOptionsWindow.AddPythonFuncHandlerForInstance(ET_ORACLE_START, "Local.OnDeferredStart")
        pEvent = App.TGIntEvent_Create()
        pEvent.SetEventType(ET_ORACLE_START)
        pEvent.SetDestination(pOptionsWindow)
        pTimer = App.TGTimer_Create()
        pTimer.SetTimerStart(App.g_kUtopiaModule.GetGameTime() + NEW_GAME_DELAY_S)
        pTimer.SetDelay(0)
        pTimer.SetDuration(0)
        pTimer.SetEvent(pEvent)
        App.g_kTimerManager.AddTimer(pTimer)
        _mark("new_game_scheduled", "%s in %.1fs" % (GAME_MODULE, NEW_GAME_DELAY_S))
    except:
        _mark("schedule_error", _exc())


def _OraclePlayOpeningMovies():
    """Replaces MainMenu.mainmenu.PlayOpeningMovies: the stock function with
    the four logo movies and the opening cutscene removed, so the sequence
    goes straight to FinishOpeningMovie (which builds the menu)."""
    _mark("play_opening_movies_hooked", "1")
    mod = _real[0]
    pTopWindow = App.TopWindow_GetTopWindow()
    if pTopWindow == None:
        return
    pTopWindow.SetNotVisible()
    App.InterfaceModule_DoTheRightThing()
    pMoviePane = App.TGPane_Create(1.0, 1.0)
    mod.g_idMoviePane = pMoviePane.GetObjID()
    pMoviePane2 = App.TGPane_Create(1.0, 1.0)
    mod.g_idMoviePane2 = pMoviePane2.GetObjID()
    App.g_kRootWindow.PrependChild(pMoviePane2, 0.00375, 0.005)
    App.g_kRootWindow.PrependChild(pMoviePane)
    mod.StopBackgroundMovies()
    pSequence = App.TGSequence_Create()
    pSequence.AddAction(App.TGScriptAction_Create("MainMenu.mainmenu", "FinishOpeningMovie"))
    mod.g_idOpeningSequence = pSequence.GetObjID()
    pSequence.Play()


def _OracleStartMusic():
    """Replaces StartMusic (the last call in FinishOpeningMovie): the menu is
    now fully built, so this is the moment to schedule the game start."""
    _mark("menu_ready", "1")
    _schedule_start()


_STUB_NAMES = ['Add3rdPartyCredits', 'AddActivisionCredits', 'AddNonTGProductionCredits', 'AddTGCredits', 'AddViacomCredits', 'BackToOptions', 'BuildConfigureGeneralTab', 'BuildConfigureGraphicsTab', 'BuildConfigureKeyboardTab', 'BuildConfigureSoundTab', 'BuildConfigureTab', 'BuildCreditsPane', 'BuildInterface', 'BuildMainMenu', 'BuildMainMenuTopButtonPane', 'BuildMainMenuTopSection', 'BuildNewGamePane', 'BuildTestGamePane', 'ClearGlobals', 'ConvertVersionStringToInt', 'CreateMenuButton', 'CreateMenuButtonString', 'CreateMenuToggleButton', 'CreateMenuYesNoButton', 'CreateSubtitleWindow', 'CreateTextEntry', 'CreateVolumeButton', 'DoCollisionAlertToggle', 'DoCollisionsToggle', 'DoDedicatedServerToggle', 'DoDifficultyToggle', 'DoEffectDetailToggle', 'DoEnhancedGlowsToggle', 'DoFullscreenToggle', 'DoGlowMapsToggle', 'DoInternetHostToggle', 'DoLODSkipToggle', 'DoMipMapsToggle', 'DoMotionBlurToggle', 'DoMusicToggle', 'DoNumberOfLightsToggle', 'DoOutputBitsToggle', 'DoOutputRateToggle', 'DoQuitGameConfirmationToggle', 'DoSFXToggle', 'DoSpaceDustToggle', 'DoSpecularMapsToggle', 'DoStreamBufferSizeToggle', 'DoStreamMusicToggle', 'DoStreamVoicesToggle', 'DoSubtitlesToggle', 'DoTextureDetailToggle', 'DoToolTipsToggle', 'DoVisibleDamageToggle', 'DoVoiceToggle', 'E1M1', 'E1M2', 'E2M0', 'E2M1', 'E2M2', 'E2M3', 'E2M4', 'E3M1', 'E3M2', 'E3M3', 'E3M4', 'E3M5', 'E4M1', 'E4M2', 'E4M3', 'E4M4', 'E5M1', 'E5M2', 'E5M3', 'E5M4', 'E6M1', 'E6M2', 'E6M3', 'E7M1', 'E7M2', 'E7M3', 'E7M4', 'E7M5', 'E8M1', 'E8M2', 'E8M3', 'FinishOpeningMovie', 'GameEnded', 'GameLoaded', 'GameStarted', 'GetConfigOptionsDatabase', 'GetControlIndex', 'GetDisplayModeIndex', 'GetIndex', 'GetVolume', 'GraphicsCancel', 'HandleConfigureKeyboard', 'HandleConfigureTab', 'HandleCustomMission', 'HandleDedicatedServerToggle', 'HandleDeviceSelected', 'HandleDisplayModeSelected', 'HandleGameNameEntry', 'HandleGameNameEntryLostFocus', 'HandleGeneralTab', 'HandleGraphicsTab', 'HandleKeyboardOpening', 'HandleLoadGameButton', 'HandleLoadGameTab', 'HandleMultiplayerTab', 'HandleNewGameTab', 'HandlePlayerNameEntry', 'HandlePlayerNameEntryLostFocus', 'HandleQuit', 'HandleSaveGameTab', 'HandleSoundTab', 'HandleTestGameTab', 'InternetHostLostFocus', 'InternetHostSetup', 'LoadConfigPart1', 'LoadConfigPart2', 'MovieSubtitle', 'NewGameLostFocus', 'OpeningCredits', 'OpeningMovie', 'OpeningMovieCredit', 'OpeningMovieDatabaseCredit', 'PlayOpeningMovies', 'QuickBattleHandler', 'RebuildMiddleBackground', 'RunOverrideMission', 'SaveConfig', 'SaveGame', 'SetHandlers', 'SetNewGameDifficulty', 'SetupCreditsMusic', 'SetupGameFont', 'StartGame', 'StartMusic', 'StartNewGameHandler', 'StopBackgroundMovies', 'SwitchMiddlePane', 'TextEntryMouseHandler', 'ToggleFullscreen', 'UpdateGraphicsOptions', 'VolumeEntryLostFocus', 'VolumeHandler']

_real = [None]

def _resolve():
    if _real[0] is not None:
        return _real[0]
    if sys.modules.has_key("MainMenu.mainmenu"):
        del sys.modules["MainMenu.mainmenu"]
    try:
        mod = __import__("MainMenu.mainmenu", {}, {}, ["mainmenu"])
    except:
        _mark("lazy_import_error", _exc())
        raise
    if SKIP_MOVIES_IN_PYTHON:
        mod.PlayOpeningMovies = _OraclePlayOpeningMovies
    mod.StartMusic = _OracleStartMusic
    _real[0] = mod
    try:
        import MainMenu
        MainMenu.mainmenu = mod
    except:
        pass
    _mark("mainmenu_patched", "1")
    return mod

class _Stub:
    def __init__(self, name):
        self.name = name
    def __call__(self, *args, **kw):
        if _real[0] is None:
            _mark("first_call", self.name)
        return apply(getattr(_resolve(), self.name), args, kw)

_stub_mod = new.module("MainMenu.mainmenu")
for _n in _STUB_NAMES:
    setattr(_stub_mod, _n, _Stub(_n))
_stub_mod.__file__ = "Local.py(stub)"
sys.modules["MainMenu.mainmenu"] = _stub_mod
try:
    import MainMenu
    MainMenu.mainmenu = _stub_mod
except:
    _mark("package_import_error", _exc())
_mark("stub_module_installed", str(len(_STUB_NAMES)))
