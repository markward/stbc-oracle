/*
 * Lockstep.asi - fixed-step virtual clock for the stbc-oracle measurement copy of Bridge
 * Commander (the oracle's own copy of the game only).
 *
 * Under Rosetta the game often manages only 25-40 loop iterations a second, so each game step
 * covers 1.5-2.5x the game time of a 60 Hz Windows step, and step size changes results (shown by
 * the time-scale tests).  This plugin makes stbc.exe's clocks (QueryPerformanceCounter,
 * timeGetTime, GetTickCount, via its import table) return a VIRTUAL time that advances by exactly
 * 1/HZ seconds at the start of every main-loop iteration (UtopiaApp_PerFrameTick 0x00438E20,
 * address verified on the GOG 1.1 exe).  Every step is then a 60 Hz step however slow the host
 * is, and the game runs as fast as the host allows.
 *
 * Lockstep.ini in the game folder:  mode=0|1|2  hz=60  step_extra_us=0
 *   mode 0  rebase only (clocks count from just before start)
 *   mode 1  lockstep virtual clock
 *   mode 2  lockstep + skip the scene pass 0x00418660 (called from TopWindow::Update at
 *           0x0043B709 between profiler calls; a tail call to vtable+0x68 of the object at
 *           0x0097E9C0; ~60% of frame time).  Believed to be the scene draw: mode 2 is only
 *           trusted where it reproduces mode 1 exactly.
 *   mode 3  mode 2 + skip the per-window passes 0x0070FDB0 / 0x0070FDF0 (called from
 *           UtopiaApp_FrameWork 0x00438E60 on the manager at 0x0099BA00; they walk its window
 *           list).  Experimental: trusted only where it reproduces mode 1 exactly.
 * Lockstep.log: every 2 s of REAL time: iterations, game ticks (TopWindow::Update 0x0043B4F0),
 * virtual seconds, real seconds, Sleep calls/ms from stbc.exe.
 */
#include <windows.h>
#include <stdio.h>
#include "minhook/include/MinHook.h"

#define START_OFFSET_MS 60000ULL

static int g_mode, g_hz = 60, g_extra_us;
static LONGLONG g_freq, g_qpc_base, g_virt;        /* virtual time in QPC units since base */
static DWORD g_tick_base, g_mm_base;
static volatile LONG g_iter, g_ticks, g_sleeps, g_sleep_ms;
static FILE *g_log;

static BOOL (WINAPI *real_QPC)(LARGE_INTEGER *);
static DWORD (WINAPI *real_GetTickCount)(void);
static DWORD (WINAPI *real_timeGetTime)(void);
static void (WINAPI *real_Sleep)(DWORD);

static LONGLONG virt_now(void)
{
    LARGE_INTEGER n;
    if (g_mode == 0) { real_QPC(&n); return n.QuadPart - g_qpc_base; }
    return g_virt;
}
static BOOL WINAPI h_QPC(LARGE_INTEGER *c) { if (!c) return FALSE; c->QuadPart = virt_now(); return TRUE; }
static DWORD WINAPI h_GetTickCount(void)
{
    if (g_mode == 0) return real_GetTickCount() - g_tick_base;
    return (DWORD)(g_virt * 1000 / g_freq);
}
static DWORD WINAPI h_timeGetTime(void)
{
    if (g_mode == 0) return real_timeGetTime() - g_mm_base;
    return (DWORD)(g_virt * 1000 / g_freq);
}
static void WINAPI h_Sleep(DWORD ms)
{
    InterlockedIncrement(&g_sleeps);
    InterlockedExchangeAdd(&g_sleep_ms, (LONG)ms);
    real_Sleep(ms);
}

/* main-loop iteration: advance the virtual clock one fixed step before the game reads it */
static void (__fastcall *o_PerFrame)(void *, void *);
/* x87 control word on the game's main thread (it is per thread): precision control bits 8-9 =
   0 single (24-bit), 2 double, 3 extended. Direct3D device creation sets single precision unless
   the game asks to preserve it; Wine imitates that, Rosetta's x87 emulation may not honour it. */
/* Profile (real time, real_QPC): cumulative ticks inside each hooked pass, so the log shows what the
   rest of the loop costs. Nested: Scene runs inside TopUpdate; WinA/WinB and TopUpdate inside PerFrame
   (as far as the hook points show). Main thread only, so plain adds. */
static LONGLONG g_t_frame, g_t_top, g_t_scene, g_t_wina, g_t_winb;
static LONGLONG now_real(void);
static volatile unsigned short g_cw_first = 0xffff, g_cw_last = 0xffff;
static volatile LONG g_cw_changes;
static void __fastcall h_PerFrame(void *self, void *edx)
{
    unsigned short cw;
    __asm__ __volatile__("fnstcw %0" : "=m"(cw));
    if (g_cw_first == 0xffff) g_cw_first = cw;
    if (cw != g_cw_last) { g_cw_last = cw; InterlockedIncrement(&g_cw_changes); }
    InterlockedIncrement(&g_iter);
    if (g_mode >= 1)
        g_virt += g_freq / g_hz + g_freq * g_extra_us / 1000000;
    {
        LONGLONG t0 = now_real();
        o_PerFrame(self, edx);
        g_t_frame += now_real() - t0;
    }
}
static volatile LONG g_skipped;
static void (__fastcall *o_Scene)(void *, void *);
static void __fastcall h_Scene(void *self, void *edx)
{
    if (g_mode >= 2) { InterlockedIncrement(&g_skipped); return; }
    {
        LONGLONG t0 = now_real();
        o_Scene(self, edx);
        g_t_scene += now_real() - t0;
    }
}
static void (__fastcall *o_WinA)(void *, void *);
static void (__fastcall *o_WinB)(void *, void *);
static void __fastcall h_WinA(void *self, void *edx)
{
    LONGLONG t0;
    if (g_mode >= 3) return;
    t0 = now_real(); o_WinA(self, edx); g_t_wina += now_real() - t0;
}
static void __fastcall h_WinB(void *self, void *edx)
{
    LONGLONG t0;
    if (g_mode >= 3) return;
    t0 = now_real(); o_WinB(self, edx); g_t_winb += now_real() - t0;
}
static void (__fastcall *o_TopUpdate)(void *, void *);
static void __fastcall h_TopUpdate(void *self, void *edx)
{
    InterlockedIncrement(&g_ticks);
    {
        LONGLONG t0 = now_real();
        o_TopUpdate(self, edx);
        g_t_top += now_real() - t0;
    }
}

static int patch_import(HMODULE module, const char *dll, const char *func, void *hook)
{
    BYTE *base = (BYTE *)module;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_DATA_DIRECTORY dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    IMAGE_IMPORT_DESCRIPTOR *imp;
    int patched = 0;
    if (!dir.VirtualAddress) return 0;
    for (imp = (IMAGE_IMPORT_DESCRIPTOR *)(base + dir.VirtualAddress); imp->Name; imp++)
    {
        IMAGE_THUNK_DATA *names, *iat;
        if (lstrcmpiA((const char *)(base + imp->Name), dll)) continue;
        names = (IMAGE_THUNK_DATA *)(base + (imp->OriginalFirstThunk ? imp->OriginalFirstThunk : imp->FirstThunk));
        iat = (IMAGE_THUNK_DATA *)(base + imp->FirstThunk);
        for (; names->u1.AddressOfData; names++, iat++)
        {
            IMAGE_IMPORT_BY_NAME *ibn;
            DWORD old;
            if (IMAGE_SNAP_BY_ORDINAL(names->u1.Ordinal)) continue;
            ibn = (IMAGE_IMPORT_BY_NAME *)(base + names->u1.AddressOfData);
            if (lstrcmpA((const char *)ibn->Name, func)) continue;
            VirtualProtect(&iat->u1.Function, sizeof(iat->u1.Function), PAGE_READWRITE, &old);
            iat->u1.Function = (ULONG_PTR)hook;
            VirtualProtect(&iat->u1.Function, sizeof(iat->u1.Function), old, &old);
            patched++;
        }
    }
    return patched;
}

static LONGLONG now_real(void)
{
    LARGE_INTEGER q;
    real_QPC(&q);
    return q.QuadPart;
}

static DWORD WINAPI reporter(LPVOID a)
{
    DWORD t0 = real_GetTickCount();
    for (;;)
    {
        real_Sleep(2000);
        fprintf(g_log, "real=%7.1fs virt=%8.2fs iter=%ld ticks=%ld sleeps=%ld sleep_ms=%ld scene_skipped=%ld"
                " fpu_cw=%04x fpu_cw_first=%04x fpu_cw_changes=%ld"
                " ms_frame=%.0f ms_top=%.0f ms_scene=%.0f ms_wina=%.0f ms_winb=%.0f\n",
                (real_GetTickCount() - t0) / 1000.0, virt_now() / (double)g_freq, g_iter, g_ticks,
                g_sleeps, g_sleep_ms, g_skipped, g_cw_last, g_cw_first, g_cw_changes,
                g_t_frame * 1000.0 / g_freq, g_t_top * 1000.0 / g_freq, g_t_scene * 1000.0 / g_freq,
                g_t_wina * 1000.0 / g_freq, g_t_winb * 1000.0 / g_freq);
        fflush(g_log);
    }
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved)
{
    if (reason == DLL_PROCESS_ATTACH)
    {
        char path[MAX_PATH], ini[MAX_PATH], *slash;
        HMODULE exe = GetModuleHandleA(NULL), k32 = GetModuleHandleA("kernel32.dll"), mm = LoadLibraryA("winmm.dll");
        LARGE_INTEGER f, now;
        int a, b, c, d;
        DisableThreadLibraryCalls(inst);
        GetModuleFileNameA(inst, path, sizeof(path));
        slash = strrchr(path, '\\');
        strcpy(ini, path); strcpy(ini + (slash - path) + 1, "Lockstep.ini");
        strcpy(slash + 1, "Lockstep.log");
        g_log = fopen(path, "w");
        g_mode = GetPrivateProfileIntA("lockstep", "mode", 0, ini);
        g_hz = GetPrivateProfileIntA("lockstep", "hz", 60, ini);
        g_extra_us = GetPrivateProfileIntA("lockstep", "step_extra_us", 0, ini);
        real_QPC = (void *)GetProcAddress(k32, "QueryPerformanceCounter");
        real_GetTickCount = (void *)GetProcAddress(k32, "GetTickCount");
        real_Sleep = (void *)GetProcAddress(k32, "Sleep");
        real_timeGetTime = (void *)GetProcAddress(mm, "timeGetTime");
        QueryPerformanceFrequency(&f);
        g_freq = f.QuadPart;
        real_QPC(&now);
        g_qpc_base = now.QuadPart - (LONGLONG)(START_OFFSET_MS * g_freq / 1000);
        g_tick_base = real_GetTickCount() - (DWORD)START_OFFSET_MS;
        g_mm_base = real_timeGetTime() - (DWORD)START_OFFSET_MS;
        g_virt = (LONGLONG)(START_OFFSET_MS * g_freq / 1000);
        a = patch_import(exe, "KERNEL32.dll", "QueryPerformanceCounter", h_QPC);
        b = patch_import(exe, "KERNEL32.dll", "GetTickCount", h_GetTickCount);
        c = patch_import(exe, "WINMM.dll", "timeGetTime", h_timeGetTime);
        d = patch_import(exe, "KERNEL32.dll", "Sleep", h_Sleep);
        fprintf(g_log, "Lockstep mode=%d hz=%d extra_us=%d freq=%lld patched qpc=%d tick=%d mm=%d sleep=%d\n",
                g_mode, g_hz, g_extra_us, g_freq, a, b, c, d);
        if (MH_Initialize() == MH_OK)
        {
            static const BYTE pf[] = { 0x00 };
            BYTE *p = (BYTE *)0x00438E20, *q = (BYTE *)0x0043B4F0;
            fprintf(g_log, "PerFrameTick prologue %02x %02x %02x %02x, TopWindow::Update %02x %02x\n",
                    p[0], p[1], p[2], p[3], q[0], q[1]);
            if (MH_CreateHook(p, h_PerFrame, (void **)&o_PerFrame) == MH_OK && MH_EnableHook(p) == MH_OK)
                fprintf(g_log, "perframe hook ok\n");
            else
                fprintf(g_log, "perframe hook FAILED\n");
            if (MH_CreateHook(q, h_TopUpdate, (void **)&o_TopUpdate) == MH_OK && MH_EnableHook(q) == MH_OK)
                fprintf(g_log, "tick hook ok\n");
            {
                BYTE *r = (BYTE *)0x00418660;
                static const BYTE want[] = { 0x8B, 0x49, 0x04, 0x85, 0xC9 };
                if (memcmp(r, want, sizeof(want)))
                    fprintf(g_log, "scene pass prologue MISMATCH, not hooked\n");
                else if (MH_CreateHook(r, h_Scene, (void **)&o_Scene) == MH_OK && MH_EnableHook(r) == MH_OK)
                    fprintf(g_log, "scene hook ok\n");
            }
            {
                static const BYTE want[] = { 0x56, 0x8B, 0xF1, 0x57, 0x33, 0xFF, 0x8B, 0x46, 0x4C };
                BYTE *wa = (BYTE *)0x0070FDB0, *wb = (BYTE *)0x0070FDF0;
                if (!memcmp(wa, want, sizeof(want)) && !memcmp(wb, want, sizeof(want)) &&
                    MH_CreateHook(wa, h_WinA, (void **)&o_WinA) == MH_OK && MH_EnableHook(wa) == MH_OK &&
                    MH_CreateHook(wb, h_WinB, (void **)&o_WinB) == MH_OK && MH_EnableHook(wb) == MH_OK)
                    fprintf(g_log, "window pass hooks ok\n");
                else
                    fprintf(g_log, "window pass hooks NOT installed\n");
            }
            (void)pf;
        }
        fflush(g_log);
        CloseHandle(CreateThread(NULL, 0, reporter, NULL, 0, NULL));
    }
    return TRUE;
}
