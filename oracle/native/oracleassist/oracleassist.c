/*
 * OracleAssist.asi - lets the stbc-oracle measurement copy of Bridge Commander run in the
 * background on the Mac (CrossOver) without taking the user's focus, mouse or cursor.
 * Installed ONLY in the oracle's own copy of the game, never in a playable install.
 *
 *  - No focus stealing: top-level windows are created with WS_EX_NOACTIVATE, which CrossOver's
 *    Mac driver turns into a non-activating window (winemac.drv window.c / cocoa_window.m
 *    preventsAppActivation), so launching a run never brings the game in front of the user.
 *  - Activation: the game window is told it is active (WM_ACTIVATEAPP/WM_ACTIVATE TRUE) and
 *    deactivation messages are swallowed, so the game behaves as if it always has focus.
 *    GetForegroundWindow/GetActiveWindow/GetFocus report the game window to game code.
 *  - Cursor: SetCursorPos and ClipCursor become no-ops and the game cannot hide the Mac cursor,
 *    so the game's mouse-look never moves or traps the user's pointer.
 *  - Movie skip: the game reads the keyboard through DirectInput (posted window messages never
 *    reach it), and the stock movie sequence must run (replacing it in Python crashes the first
 *    battle frame at 0x0044E6A9, as the oracle README documents). So the keyboard device's
 *    GetDeviceData/GetDeviceState are wrapped and an ESC press+release (DIK_ESCAPE) is injected
 *    every 1.5 s until Local.py reports "menu_ready" in oracle_boot.cfg, then never again.
 *    While injecting, a not-acquired keyboard (no real focus) reads as "no keys" rather than
 *    an error.
 *  - Keyboard: after the menu, a keyboard read while the game window is not really the foreground
 *    window returns no keys, so typing in other windows never reaches a run (DirectInput reads
 *    the keyboard in background mode).
 *  - Diagnostics: counts game ticks (TopWindow::Update 0x0043b4f0, address verified on the
 *    GOG 1.1 exe) and activation messages, written to OracleAssist.log
 *    every 2 s, so a driver can tell whether the loop is running.
 */
#include <windows.h>
#include <stdio.h>
#define DIRECTINPUT_VERSION 0x0700
#include <dinput.h>
#include "minhook/include/MinHook.h"

static FILE *g_log;
static HWND g_hwnd;
static WNDPROC g_oldproc;
static volatile LONG g_ticks, g_swallowed, g_cursor_blocked;
static DWORD g_main_tid;
static int g_esc;

static void alog(const char *fmt, ...)
{
    va_list ap;
    if (!g_log) return;
    va_start(ap, fmt); vfprintf(g_log, fmt, ap); va_end(ap);
    fflush(g_log);
}

/* --- user32 hooks --- */
static BOOL (WINAPI *o_SetCursorPos)(int, int);
static BOOL (WINAPI *o_ClipCursor)(const RECT *);
static int  (WINAPI *o_ShowCursor)(BOOL);
static HWND (WINAPI *o_GetForegroundWindow)(void);
static HWND (WINAPI *o_GetActiveWindow)(void);
static HWND (WINAPI *o_GetFocus)(void);
static HWND (WINAPI *o_CreateWindowExA)(DWORD, LPCSTR, LPCSTR, DWORD, int, int, int, int, HWND, HMENU, HINSTANCE, LPVOID);

static HWND WINAPI h_CreateWindowExA(DWORD ex, LPCSTR cls, LPCSTR name, DWORD style, int x, int y, int w, int h,
                                     HWND parent, HMENU menu, HINSTANCE inst, LPVOID param)
{
    if (!parent && !(style & WS_CHILD))
    {
        ex |= WS_EX_NOACTIVATE;
        alog("CreateWindowExA top-level \"%s\" %dx%d: WS_EX_NOACTIVATE added\n",
             (cls && ((DWORD_PTR)cls >> 16)) ? cls : "#atom", w, h);
    }
    return o_CreateWindowExA(ex, cls, name, style, x, y, w, h, parent, menu, inst, param);
}

static BOOL WINAPI h_SetCursorPos(int x, int y) { InterlockedIncrement(&g_cursor_blocked); return TRUE; }
static BOOL WINAPI h_ClipCursor(const RECT *r) { if (r) InterlockedIncrement(&g_cursor_blocked); return o_ClipCursor(NULL); }
static int  WINAPI h_ShowCursor(BOOL show) { return show ? 0 : -1; }
static HWND WINAPI h_GetForegroundWindow(void) { return g_hwnd ? g_hwnd : o_GetForegroundWindow(); }
static HWND WINAPI h_GetActiveWindow(void) { return g_hwnd ? g_hwnd : o_GetActiveWindow(); }
static HWND WINAPI h_GetFocus(void) { return g_hwnd ? g_hwnd : o_GetFocus(); }

/* --- tick counter: TopWindow::Update is __thiscall(this), no stack args --- */
static void (__fastcall *o_TopWindowUpdate)(void *, void *);
static void __fastcall h_TopWindowUpdate(void *self, void *edx)
{
    InterlockedIncrement(&g_ticks);
    o_TopWindowUpdate(self, edx);
}

/* --- window subclass --- */
static LRESULT CALLBACK subproc(HWND h, UINT m, WPARAM w, LPARAM l)
{
    switch (m)
    {
    case WM_ACTIVATEAPP:
        if (!w) { InterlockedIncrement(&g_swallowed); return 0; }
        break;
    case WM_ACTIVATE:
        if (LOWORD(w) == WA_INACTIVE) { InterlockedIncrement(&g_swallowed); return 0; }
        break;
    case WM_KILLFOCUS:
    case WM_NCACTIVATE:
        if (m == WM_KILLFOCUS || !w) { InterlockedIncrement(&g_swallowed); if (m == WM_NCACTIVATE) return TRUE; return 0; }
        break;
    }
    return CallWindowProcA(g_oldproc, h, m, w, l);
}


/* --- DirectInput keyboard injection --- */
static void *g_kbd;                       /* the keyboard IDirectInputDevice */
static volatile LONG g_inject;            /* 0 idle, 1 = send key down, 2 = send key up */
static volatile LONG g_injected;
static DWORD g_seq = 0x40000000;
static HRESULT (WINAPI *o_GetDeviceData)(void *, DWORD, LPDIDEVICEOBJECTDATA, LPDWORD, DWORD);
static HRESULT (WINAPI *o_GetDeviceState)(void *, DWORD, LPVOID);
static HRESULT (WINAPI *o_CreateDevice)(void *, REFGUID, void **, LPUNKNOWN);
static HRESULT (WINAPI *o_CreateDeviceEx)(void *, REFGUID, REFIID, void **, LPUNKNOWN);
static HRESULT (WINAPI *o_DirectInputCreateEx)(HINSTANCE, DWORD, REFIID, void **, LPUNKNOWN);
static int g_menu;
static volatile LONG g_keys_dropped;

/* After the menu, the user's typing in OTHER windows must never reach the run: the game reads the
   keyboard with DirectInput in background mode, so on Windows it saw every key the user typed
   elsewhere. Keys reach the game only when its window really is the foreground window. */
static int user_elsewhere(void)
{
    return g_menu && g_hwnd && o_GetForegroundWindow && o_GetForegroundWindow() != g_hwnd;
}

static HRESULT WINAPI h_GetDeviceData(void *self, DWORD cb, LPDIDEVICEOBJECTDATA data, LPDWORD n, DWORD flags)
{
    DWORD want = n ? *n : 0;
    HRESULT hr = o_GetDeviceData(self, cb, data, n, flags);
    if (self == g_kbd && user_elsewhere())
    {
        if (n && *n) InterlockedIncrement(&g_keys_dropped);
        if (n) *n = 0;
        return DI_OK;
    }
    if (self != g_kbd || g_menu) return hr;
    if (FAILED(hr)) { if (n) *n = 0; hr = DI_OK; }
    if (g_inject && data && n && *n < want && !(flags & DIGDD_PEEK) && cb >= sizeof(DIDEVICEOBJECTDATA_DX3))
    {
        LPDIDEVICEOBJECTDATA d = (LPDIDEVICEOBJECTDATA)((BYTE *)data + *n * cb);
        memset(d, 0, cb);
        d->dwOfs = DIK_ESCAPE;
        d->dwData = g_inject == 1 ? 0x80 : 0;
        d->dwTimeStamp = GetTickCount();
        d->dwSequence = g_seq++;
        (*n)++;
        g_inject = g_inject == 1 ? 2 : 0;
        InterlockedIncrement(&g_injected);
    }
    return hr;
}

static HRESULT WINAPI h_GetDeviceState(void *self, DWORD cb, LPVOID buf)
{
    HRESULT hr = o_GetDeviceState(self, cb, buf);
    if (self == g_kbd && user_elsewhere()) { memset(buf, 0, cb); return DI_OK; }
    if (self != g_kbd || g_menu) return hr;
    if (FAILED(hr)) { memset(buf, 0, cb); hr = DI_OK; }
    if (g_inject && cb > DIK_ESCAPE)
    {
        ((BYTE *)buf)[DIK_ESCAPE] = g_inject == 1 ? 0x80 : 0;
        g_inject = g_inject == 1 ? 2 : 0;
        InterlockedIncrement(&g_injected);
    }
    return hr;
}

static void patch_vtbl(void **slot, void *det, void **orig)
{
    DWORD old;
    if (*slot == det) return;
    VirtualProtect(slot, sizeof(void *), PAGE_EXECUTE_READWRITE, &old);
    if (!*orig) *orig = *slot;
    *slot = det;
    VirtualProtect(slot, sizeof(void *), old, &old);
}

static void wrap_keyboard(void *dev)
{
    void **vt = *(void ***)dev;
    g_kbd = dev;
    patch_vtbl(&vt[9], h_GetDeviceState, (void **)&o_GetDeviceState);
    patch_vtbl(&vt[10], h_GetDeviceData, (void **)&o_GetDeviceData);
    alog("keyboard device %p wrapped (vtable %p)\n", dev, vt);
}

static HRESULT WINAPI h_CreateDevice(void *self, REFGUID g, void **out, LPUNKNOWN u)
{
    HRESULT hr = o_CreateDevice(self, g, out, u);
    if (SUCCEEDED(hr) && out && *out && IsEqualGUID(g, &GUID_SysKeyboard)) wrap_keyboard(*out);
    return hr;
}

static HRESULT WINAPI h_CreateDeviceEx(void *self, REFGUID g, REFIID iid, void **out, LPUNKNOWN u)
{
    HRESULT hr = o_CreateDeviceEx(self, g, iid, out, u);
    if (SUCCEEDED(hr) && out && *out && IsEqualGUID(g, &GUID_SysKeyboard)) wrap_keyboard(*out);
    return hr;
}

static HRESULT WINAPI h_DirectInputCreateEx(HINSTANCE inst, DWORD ver, REFIID iid, void **out, LPUNKNOWN u)
{
    HRESULT hr = o_DirectInputCreateEx(inst, ver, iid, out, u);
    if (SUCCEEDED(hr) && out && *out)
    {
        void **vt = *(void ***)*out;
        patch_vtbl(&vt[3], h_CreateDevice, (void **)&o_CreateDevice);
        patch_vtbl(&vt[9], h_CreateDeviceEx, (void **)&o_CreateDeviceEx);
        alog("DirectInputCreateEx version %lx: CreateDevice/CreateDeviceEx wrapped\n", ver);
    }
    return hr;
}

static int menu_ready(void)
{
    /* oracle_boot.cfg is written by the game's ConfigMapping and contains NUL bytes,
       so search the raw bytes rather than with strstr. */
    static char buf[65536];
    static const char key[] = "menu_ready";
    FILE *f = fopen("oracle_boot.cfg", "rb");
    size_t n, i;
    if (!f) return 0;
    n = fread(buf, 1, sizeof(buf), f);
    fclose(f);
    for (i = 0; i + sizeof(key) - 1 <= n; i++)
        if (!memcmp(buf + i, key, sizeof(key) - 1)) return 1;
    return 0;
}

static BOOL CALLBACK find_wnd(HWND h, LPARAM lp)
{
    DWORD pid;
    char cls[64];
    GetWindowThreadProcessId(h, &pid);
    if (pid != GetCurrentProcessId() || !IsWindowVisible(h) || GetParent(h)) return TRUE;
    GetClassNameA(h, cls, sizeof(cls));
    if (strstr(cls, "IME") || strstr(cls, "Shell")) return TRUE;
    *(HWND *)lp = h;
    return FALSE;
}

static DWORD WINAPI worker(LPVOID arg)
{
    DWORD start = GetTickCount(), last_ticks = 0, last_esc = 0;
    for (;;)
    {
        Sleep(250);
        if (!g_hwnd)
        {
            HWND h = NULL;
            EnumWindows(find_wnd, (LPARAM)&h);
            if (h)
            {
                char title[128], cls[64];
                GetWindowTextA(h, title, sizeof(title));
                GetClassNameA(h, cls, sizeof(cls));
                g_oldproc = (WNDPROC)SetWindowLongA(h, GWL_WNDPROC, (LONG)subproc);
                g_hwnd = h;
                alog("%6lu ms  window %p class \"%s\" title \"%s\" subclassed; sending activate\n",
                     GetTickCount() - start, h, cls, title);
                PostMessageA(h, WM_ACTIVATEAPP, TRUE, 0);
                PostMessageA(h, WM_ACTIVATE, WA_ACTIVE, 0);
                PostMessageA(h, WM_SETFOCUS, 0, 0);
            }
        }
        if (g_hwnd && !g_menu && GetTickCount() - last_esc >= 1500)
        {
            last_esc = GetTickCount();
            if (menu_ready()) { g_menu = 1; alog("%6lu ms  menu ready, ESC injection stops (%ld injected)\n", GetTickCount() - start, g_injected); }
            else if (g_kbd && !g_inject) { g_inject = 1; g_esc++; }
        }
        if ((GetTickCount() - start) / 2000 != ((GetTickCount() - start - 250) / 2000))
        {
            LONG t = g_ticks;
            alog("%6lu ms  ticks %ld (+%ld)  swallowed %ld  cursor_blocked %ld  esc %d  real_fg=%p  keys_dropped %ld\n",
                 GetTickCount() - start, t, t - (LONG)last_ticks, g_swallowed, g_cursor_blocked,
                 g_esc, o_GetForegroundWindow(), g_keys_dropped);
            last_ticks = t;
        }
    }
    return 0;
}

static void hook_api(const char *name, void *det, void **orig)
{
    MH_STATUS s = MH_CreateHookApi(L"user32", name, det, orig);
    if (s == MH_OK) s = MH_EnableHook(MH_ALL_HOOKS);
    alog("hook %s: %s\n", name, s == MH_OK ? "ok" : MH_StatusToString(s));
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved)
{
    if (reason == DLL_PROCESS_ATTACH)
    {
        char path[MAX_PATH], *slash;
        static const BYTE expect[] = { 0x83, 0xEC };   /* checked below, logged only */
        DisableThreadLibraryCalls(inst);
        g_main_tid = GetCurrentThreadId();
        GetModuleFileNameA(inst, path, sizeof(path));
        if ((slash = strrchr(path, '\\'))) strcpy(slash + 1, "OracleAssist.log");
        g_log = fopen(path, "w");
        alog("OracleAssist loaded (main thread %lu)\n", g_main_tid);
        if (MH_Initialize() != MH_OK) { alog("MH_Initialize failed\n"); return TRUE; }
        hook_api("SetCursorPos", h_SetCursorPos, (void **)&o_SetCursorPos);
        hook_api("ClipCursor", h_ClipCursor, (void **)&o_ClipCursor);
        hook_api("ShowCursor", h_ShowCursor, (void **)&o_ShowCursor);
        hook_api("GetForegroundWindow", h_GetForegroundWindow, (void **)&o_GetForegroundWindow);
        hook_api("GetActiveWindow", h_GetActiveWindow, (void **)&o_GetActiveWindow);
        hook_api("GetFocus", h_GetFocus, (void **)&o_GetFocus);
        hook_api("CreateWindowExA", h_CreateWindowExA, (void **)&o_CreateWindowExA);
        {
            MH_STATUS st = MH_CreateHookApi(L"dinput", "DirectInputCreateEx", h_DirectInputCreateEx, (void **)&o_DirectInputCreateEx);
            if (st == MH_OK) st = MH_EnableHook(MH_ALL_HOOKS);
            alog("hook DirectInputCreateEx: %s\n", st == MH_OK ? "ok" : MH_StatusToString(st));
        }
        {
            BYTE *p = (BYTE *)0x0043b4f0;
            alog("TopWindow::Update prologue %02x %02x %02x %02x\n", p[0], p[1], p[2], p[3]);
            if (MH_CreateHook(p, h_TopWindowUpdate, (void **)&o_TopWindowUpdate) == MH_OK &&
                MH_EnableHook(p) == MH_OK)
                alog("tick hook ok\n");
            else
                alog("tick hook FAILED\n");
        }
        (void)expect;
        CloseHandle(CreateThread(NULL, 0, worker, NULL, 0, NULL));
    }
    return TRUE;
}
