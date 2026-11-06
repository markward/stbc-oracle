/*
 * RandTap.asi - control and record the C runtime random generator inside stbc.exe (stbc-oracle).
 *
 * stbc.exe links the multithreaded MSVC CRT statically (no msvcrt import), so rand/srand are hooked by
 * address, verified on the GOG 1.1 exe before hooking:
 *   srand 0x00859DE6:  E8 xx xx xx xx (call _getptd)  8B 4C 24 04  89 48 14  C3
 *   rand  0x00859DF3:  E8 xx xx xx xx (call _getptd)  8B 48 14  69 C9 FD 43 03 00  81 C1 C3 9E 26 00 ...
 * (holdrand = holdrand*214013 + 2531011, per thread; returns (holdrand >> 16) & 0x7FFF.)
 *
 * RandTap.ini in the game folder:  seed=<n>|-1  trace=0|1
 *   seed >= 0: every srand() call is given this seed instead of its argument, AND srand(seed) is
 *              applied on the first rand() call of each thread that never called srand itself.
 *   trace=1:   every rand() call -> RandTap.trace (binary: uint32 index, uint32 caller, uint16 value).
 *   isolate=<hex>,<hex>,...: rand() calls whose return address is listed are answered from a SEPARATE
 *              generator (same LCG, own state seeded from seed+1) and never touch the game's holdrand.
 *              For co-simulation: 0x004EA435 is a render/effects loop (fills a float array with rand()
 *              per element; 95% of all rand() calls) whose call count varies run to run, which reshuffles
 *              every later draw the AI makes. Default off: the oracle's validated setup is unchanged.
 * RandTap.log: the srand calls (original argument, caller) and, every 2 s of real time, the number of
 * rand() calls so far and the top callers (return addresses into stbc.exe) -- which engine code uses chance.
 * rand() itself is the original: the plugin only seeds and observes.
 * GetRandomNumber 0x0071AEC0 (E8 -> rand, 33 D2, F7 74 24 04, 8B C2, C2 04 00): every call -> RandTap.grn
 * (binary: uint32 index of the underlying rand() call, uint32 n, uint32 result, uint32 caller) when
 * trace=1 -- the script-level random sequence a co-simulating Dauntless can replay.
 */
#include <windows.h>
#include <stdio.h>
#include "minhook/include/MinHook.h"

#define SRAND_VA 0x00859DE6
#define RAND_VA  0x00859DF3
#define GRN_VA   0x0071AEC0   /* TGSystemWrapper::GetRandomNumber(n) = rand() % n -- what the AI scripts call */
#define MAXC 64

static FILE *g_log, *g_trace, *g_grn;
static DWORD g_iso[16]; static int g_niso; static unsigned int g_iso_state; static volatile LONG g_iso_calls;
static volatile LONG g_grn_calls;
static unsigned int (__stdcall *o_grn)(unsigned int);
static long g_seed = -1;
static int g_trace_on;
static volatile LONG g_calls, g_srand_calls;
static DWORD g_tls_seeded = TLS_OUT_OF_INDEXES;
static struct { DWORD caller; LONG n; } g_callers[MAXC];
static CRITICAL_SECTION g_cs;

static void (__cdecl *o_srand)(unsigned int);
static int (__cdecl *o_rand)(void);

static void count_caller(DWORD c)
{
    int i;
    EnterCriticalSection(&g_cs);
    for (i = 0; i < MAXC; i++) {
        if (g_callers[i].caller == c) { g_callers[i].n++; break; }
        if (g_callers[i].caller == 0) { g_callers[i].caller = c; g_callers[i].n = 1; break; }
    }
    LeaveCriticalSection(&g_cs);
}

static void __cdecl h_srand(unsigned int s)
{
    DWORD caller = (DWORD)__builtin_return_address(0);
    InterlockedIncrement(&g_srand_calls);
    if (g_log) { fprintf(g_log, "srand(%u) from %08lx -> %s%ld\n", s, caller, g_seed >= 0 ? "seed " : "kept ", g_seed >= 0 ? g_seed : (long)s); fflush(g_log); }
    if (g_tls_seeded != TLS_OUT_OF_INDEXES) TlsSetValue(g_tls_seeded, (LPVOID)1);
    o_srand(g_seed >= 0 ? (unsigned int)g_seed : s);
}

static int __cdecl h_rand(void)
{
    DWORD caller = (DWORD)__builtin_return_address(0);
    LONG idx;
    int v;
    if (g_seed >= 0 && g_tls_seeded != TLS_OUT_OF_INDEXES && !TlsGetValue(g_tls_seeded)) {
        TlsSetValue(g_tls_seeded, (LPVOID)1);
        o_srand((unsigned int)g_seed);
    }
    {
        int k;
        for (k = 0; k < g_niso; k++)
            if (g_iso[k] == caller) {
                g_iso_state = g_iso_state * 214013u + 2531011u;
                InterlockedIncrement(&g_iso_calls);
                return (int)((g_iso_state >> 16) & 0x7FFF);
            }
    }
    v = o_rand();
    idx = InterlockedIncrement(&g_calls);
    count_caller(caller);
    if (g_trace) {
        unsigned short vv = (unsigned short)v;
        EnterCriticalSection(&g_cs);
        fwrite(&idx, 4, 1, g_trace); fwrite(&caller, 4, 1, g_trace); fwrite(&vv, 2, 1, g_trace);
        LeaveCriticalSection(&g_cs);
    }
    return v;
}

/* GetRandomNumber is __thiscall-like via SWIG? It returns with `ret 4` and reads n at [esp+4] with ecx
   unused, so __stdcall(n) matches its stack contract. */
static unsigned int __stdcall h_grn(unsigned int n)
{
    DWORD caller = (DWORD)__builtin_return_address(0);
    unsigned int r = o_grn(n);
    LONG gi = InterlockedIncrement(&g_grn_calls);
    if (g_grn) {
        DWORD rec[4];
        rec[0] = (DWORD)g_calls; rec[1] = n; rec[2] = r; rec[3] = caller;
        EnterCriticalSection(&g_cs);
        fwrite(rec, 4, 4, g_grn);
        LeaveCriticalSection(&g_cs);
    }
    (void)gi;
    return r;
}

static DWORD WINAPI reporter(LPVOID a)
{
    DWORD t0 = GetTickCount();
    for (;;) {
        int i;
        Sleep(2000);
        EnterCriticalSection(&g_cs);
        fprintf(g_log, "real=%7.1fs rand_calls=%ld srand_calls=%ld grn_calls=%ld isolated=%ld callers:", (GetTickCount() - t0) / 1000.0, g_calls, g_srand_calls, g_grn_calls, g_iso_calls);
        for (i = 0; i < MAXC && g_callers[i].caller; i++) fprintf(g_log, " %08lx:%ld", g_callers[i].caller, g_callers[i].n);
        fprintf(g_log, "\n");
        if (g_trace) fflush(g_trace);
        if (g_grn) fflush(g_grn);
        LeaveCriticalSection(&g_cs);
        fflush(g_log);
    }
    return 0;
}

static int check(const BYTE *p, const BYTE *tail, int n)
{
    return p[0] == 0xE8 && !memcmp(p + 5, tail, n);
}

static int check_grn(void)
{
    static const BYTE tail[] = {0x33, 0xD2, 0xF7, 0x74, 0x24, 0x04, 0x8B, 0xC2, 0xC2, 0x04, 0x00};
    int ok = check((const BYTE *)GRN_VA, tail, sizeof(tail));
    if (g_log) fprintf(g_log, "GetRandomNumber prologue %s\n", ok ? "ok" : "MISMATCH - not hooked");
    return ok;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved)
{
    if (reason == DLL_PROCESS_ATTACH) {
        char path[MAX_PATH], *slash, ini[MAX_PATH];
        static const BYTE srand_tail[] = {0x8B, 0x4C, 0x24, 0x04, 0x89, 0x48, 0x14, 0xC3};
        static const BYTE rand_tail[] = {0x8B, 0x48, 0x14, 0x69, 0xC9, 0xFD, 0x43, 0x03, 0x00, 0x81, 0xC1, 0xC3, 0x9E, 0x26, 0x00};
        DisableThreadLibraryCalls(inst);
        InitializeCriticalSection(&g_cs);
        GetModuleFileNameA(inst, path, sizeof(path));
        if ((slash = strrchr(path, '\\'))) *(slash + 1) = 0;
        sprintf(ini, "%sRandTap.ini", path);
        g_seed = GetPrivateProfileIntA("randtap", "seed", -1, ini);
        g_trace_on = GetPrivateProfileIntA("randtap", "trace", 0, ini);
        { char lp[MAX_PATH]; sprintf(lp, "%sRandTap.log", path); g_log = fopen(lp, "w"); }
        if (g_trace_on) { char tp[MAX_PATH]; sprintf(tp, "%sRandTap.trace", path); g_trace = fopen(tp, "wb");
                          sprintf(tp, "%sRandTap.grn", path); g_grn = fopen(tp, "wb"); }
        g_tls_seeded = TlsAlloc();
        {
            char buf[256], *tok;
            GetPrivateProfileStringA("randtap", "isolate", "", buf, sizeof(buf), ini);
            for (tok = strtok(buf, ", "); tok && g_niso < 16; tok = strtok(NULL, ", "))
                g_iso[g_niso++] = (DWORD)strtoul(tok, NULL, 16);
            g_iso_state = (unsigned int)(g_seed >= 0 ? g_seed + 1 : 1);
        }
        fprintf(g_log, "RandTap seed=%ld trace=%d isolate=%d callers\n", g_seed, g_trace_on, g_niso);
        if (!check((const BYTE *)SRAND_VA, srand_tail, sizeof(srand_tail)) || !check((const BYTE *)RAND_VA, rand_tail, sizeof(rand_tail))) {
            fprintf(g_log, "rand/srand prologue MISMATCH - not hooked (not the GOG 1.1 exe?)\n"); fflush(g_log);
            return TRUE;
        }
        if (MH_Initialize() == MH_OK &&
            MH_CreateHook((LPVOID)SRAND_VA, h_srand, (void **)&o_srand) == MH_OK &&
            MH_CreateHook((LPVOID)RAND_VA, h_rand, (void **)&o_rand) == MH_OK &&
            (!check_grn() || MH_CreateHook((LPVOID)GRN_VA, h_grn, (void **)&o_grn) == MH_OK) &&
            MH_EnableHook(MH_ALL_HOOKS) == MH_OK)
            fprintf(g_log, "rand/srand hooks ok\n");
        else
            fprintf(g_log, "rand/srand hooks FAILED\n");
        fflush(g_log);
        CreateThread(NULL, 0, reporter, NULL, 0, NULL);
    }
    return TRUE;
}
