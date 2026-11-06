/*
 * CombatTap.asi - per-hit "black box" recorder for Bridge Commander's damage pipeline.
 * Installed ONLY in the oracle's own copy of the game (stbc-oracle measurements).
 *
 * Hooks the game's own functions (addresses from the public STBC-Reverse-Engineering project,
 * github.com/SandboxServers/STBC-Reverse-Engineering; each
 * prologue checked against the GOG 1.1 stbc.exe before hooking; a mismatch skips that hook):
 *
 *   0x005AF010 WeaponHitHandler   __thiscall(ship, WeaponHitEvent*)              ret 4
 *   0x005AF160 shield-hit path    __thiscall(ship, WeaponHitEvent*)              ret 4
 *   0x005AF420 ApplyWeaponDamage  __thiscall(ship, WeaponHitEvent*)              ret 4
 *   0x00594020 DoDamage           __thiscall(ship, float *dir, float a, DWORD b) ret 0xC
 *   0x005AFD70 SubsystemDamageDistributor
 *                                 __thiscall(ship, float *pos, float *dmg, float r, void *src, int coll) ret 0x14
 *   0x005AF4A0 per-subsystem damage
 *                                 __thiscall(ship, subsys, float dmg, void *attacker, int force) ret 0x10, returns float overflow
 *   0x0056C470 SetCondition       __thiscall(subsys, float hp)                   ret 4
 *   0x0056A5C0 SetCurShields      __thiscall(shields, int face, float value)     ret 8
 *
 * WeaponHitEvent fields (from the game's SWIG accessors): +0x2C weapon type, +0x30 object-space
 * hit normal, +0x3C object-space hit point, +0x4C radius (GetRadius), +0x50 condition
 * (GetCondition), +0x54 damage (GetDamage), +0x58 hull-hit flag (IsHullHit).
 * Subsystem current HP is at +0x30. Game time is UtopiaModule(*0x009A09D0)+0x90 (GetGameTime).
 *
 * Output: CombatTap.log in the game folder, one line per event, "kind key=value ...".
 */
#include <windows.h>
#include <stdio.h>
#include "minhook/include/MinHook.h"

static FILE *g_log;
static CRITICAL_SECTION g_cs;

static float gtime(void)
{
    DWORD app = *(DWORD *)0x009A09D0;
    return app ? *(float *)(app + 0x90) : -1.0f;
}

static void out(const char *fmt, ...)
{
    va_list ap;
    if (!g_log) return;
    EnterCriticalSection(&g_cs);
    fprintf(g_log, "%.4f ", gtime());
    va_start(ap, fmt); vfprintf(g_log, fmt, ap); va_end(ap);
    LeaveCriticalSection(&g_cs);
}

static float fget(void *p, int off) { return *(float *)((BYTE *)p + off); }

/* --- hooks --- */
static int (__fastcall *o_WeaponHit)(void *, void *, void *);
static int __fastcall h_WeaponHit(void *ship, void *edx, void *hit)
{
    int r;
    BYTE *h = hit;
    out("H ship=%p hit=%p type=%d hull=%d rad=%.4f cond=%.4f dmg=%.4f op=%.4f,%.4f,%.4f on=%.4f,%.4f,%.4f\n",
        ship, hit, *(int *)(h + 0x2C), h[0x58], fget(h, 0x4C), fget(h, 0x50), fget(h, 0x54),
        fget(h, 0x3C), fget(h, 0x40), fget(h, 0x44), fget(h, 0x30), fget(h, 0x34), fget(h, 0x38));
    {   /* raw event words for later decoding (+0x00..+0x5C) */
        char buf[16 * 24 + 8], *q = buf;
        int k;
        for (k = 0; k < 24; k++) q += sprintf(q, "%08lx%s", ((DWORD *)h)[k], k < 23 ? "," : "");
        out("HR hit=%p raw=%s\n", hit, buf);
    }
    r = o_WeaponHit(ship, edx, hit);
    out("h ship=%p hit=%p end\n", ship, hit);
    return r;
}

static int (__fastcall *o_ShieldPath)(void *, void *, void *);
static int __fastcall h_ShieldPath(void *ship, void *edx, void *hit)
{
    int r;
    out("SP ship=%p hit=%p begin\n", ship, hit);
    r = o_ShieldPath(ship, edx, hit);
    out("sp ship=%p hit=%p end\n", ship, hit);
    return r;
}

static int (__fastcall *o_ApplyWeapon)(void *, void *, void *);
static int __fastcall h_ApplyWeapon(void *ship, void *edx, void *hit)
{
    int r;
    out("AW ship=%p hit=%p begin\n", ship, hit);
    r = o_ApplyWeapon(ship, edx, hit);
    out("aw ship=%p hit=%p end\n", ship, hit);
    return r;
}

static int (__fastcall *o_DoDamage)(void *, void *, float *, float, DWORD);
static int __fastcall h_DoDamage(void *ship, void *edx, float *dir, float a, DWORD b)
{
    out("DD ship=%p dir=%.4f,%.4f,%.4f a=%.4f b=%.4f\n", ship, dir ? dir[0] : 0, dir ? dir[1] : 0,
        dir ? dir[2] : 0, a, *(float *)&b);
    return o_DoDamage(ship, edx, dir, a, b);
}

static int (__fastcall *o_Distrib)(void *, void *, float *, float *, float, void *, int);
static int __fastcall h_Distrib(void *ship, void *edx, float *pos, float *dmg, float r, void *src, int coll)
{
    int ret;
    float before = dmg ? *dmg : -1;
    out("DS ship=%p pos=%.4f,%.4f,%.4f dmg=%.4f r=%.4f src=%p coll=%d\n", ship,
        pos ? pos[0] : 0, pos ? pos[1] : 0, pos ? pos[2] : 0, before, r, src, coll & 0xff);
    ret = o_Distrib(ship, edx, pos, dmg, r, src, coll);
    out("ds ship=%p dmg_after=%.4f\n", ship, dmg ? *dmg : -1);
    return ret;
}

static float (__fastcall *o_SubDamage)(void *, void *, void *, float, void *, int);
static float __fastcall h_SubDamage(void *ship, void *edx, void *sub, float dmg, void *att, int force)
{
    float before = fget(sub, 0x30), ov;
    ov = o_SubDamage(ship, edx, sub, dmg, att, force);
    out("W ship=%p sub=%p dmg=%.4f att=%p force=%d hp=%.4f->%.4f overflow=%.4f\n",
        ship, sub, dmg, att, force & 0xff, before, fget(sub, 0x30), ov);
    return ov;
}

static int (__fastcall *o_SetCond)(void *, void *, float);
static int __fastcall h_SetCond(void *sub, void *edx, float hp)
{
    float before = fget(sub, 0x30);
    int r = o_SetCond(sub, edx, hp);
    if (fget(sub, 0x30) != before)
        out("C sub=%p hp=%.4f->%.4f\n", sub, before, fget(sub, 0x30));
    return r;
}

static int (__fastcall *o_SetShields)(void *, void *, int, float);
static int __fastcall h_SetShields(void *sh, void *edx, int face, float v)
{
    int r = o_SetShields(sh, edx, face, v);
    out("S sh=%p face=%d set=%.4f\n", sh, face, v);
    return r;
}

/* --- speed commands (added 2026-10-17): every ShipClass::SetImpulse / SetSpeed, by caller ---
 *   0x005AC470 SetImpulse  __thiscall(ship, float impulse, TGPoint3 *dir, int space)  ret 0xC
 *   0x005AC590 SetSpeed    __thiscall(ship, float speed,   TGPoint3 *dir, int space)  ret 0xC (calls SetImpulse)
 * Python's ShipClass.SetImpulse wrapper calls from 0x0060AAD5 (return 0x0060AADA); compiled callers (e.g. the
 * engine's own AvoidObstacles) show up with their own return addresses. A row is written only when the
 * value or the caller changes for that ship, with the number of identical calls since the last row:
 *   IMP ship=<ptr> v=<impulse> caller=<ret addr> n=<calls since last row>
 *   SPD ship=<ptr> v=<speed>   caller=<ret addr> n=<...>                                                    */
#define MAXSHIPS 16
static struct { void *ship; float v; DWORD caller; LONG n; } g_im[MAXSHIPS], g_sp[MAXSHIPS];

static void note_cmd(const char *kind, void *tbl_, void *ship, float v, DWORD caller)
{
    struct { void *ship; float v; DWORD caller; LONG n; } *tbl = tbl_;
    int i;
    EnterCriticalSection(&g_cs);
    for (i = 0; i < MAXSHIPS; i++)
        if (tbl[i].ship == ship || tbl[i].ship == NULL) break;
    if (i < MAXSHIPS)
    {
        if (tbl[i].ship == ship && tbl[i].v == v && tbl[i].caller == caller) { tbl[i].n++; LeaveCriticalSection(&g_cs); return; }
        tbl[i].ship = ship; tbl[i].v = v; tbl[i].caller = caller;
    }
    LeaveCriticalSection(&g_cs);
    out("%s ship=%p v=%.4f caller=%08lx n=%ld\n", kind, ship, v, caller, i < MAXSHIPS ? tbl[i].n : 0L);
    if (i < MAXSHIPS) tbl[i].n = 1;
}

static void (__fastcall *o_SetImpulse)(void *, void *, float, void *, int);
static void __fastcall h_SetImpulse(void *ship, void *edx, float v, void *dir, int space)
{
    note_cmd("IMP", g_im, ship, v, (DWORD)__builtin_return_address(0));
    o_SetImpulse(ship, edx, v, dir, space);
}

static void (__fastcall *o_SetSpeed)(void *, void *, float, void *, int);
static void __fastcall h_SetSpeed(void *ship, void *edx, float v, void *dir, int space)
{
    note_cmd("SPD", g_sp, ship, v, (DWORD)__builtin_return_address(0));
    o_SetSpeed(ship, edx, v, dir, space);
}

/* --- compiled FireScript activity (added 2026-10-17) ---
 *   0x00483500 OptimizedFireScript::FireSystemAtTarget __thiscall(fs, weaponSystem, target, subsystem) ret 0xC
 *   0x00484570 OptimizedFireScript::CheckGoodShot      __thiscall(fs, weaponSystem, target, subsystem) ret 0xC, al
 * Which FireScript instance tries which weapon system, and how often its aim check passes. Counted per
 * (fs, weapon system) and written once per game second:
 *   FSN fs=<ptr> name=<AI node name>                      (first time an instance is seen)
 *   FSA fs=<ptr> w=<weapon system ptr> tgt=<ptr> n=<FireSystemAtTarget calls> good=<CheckGoodShot true>
 * The node name is the ArtificialIntelligence name (char * at +0x0C, as the SequenceAI profiling strings use). */
#define MAXFS 64
static struct { void *fs; void *w; void *tgt; LONG n, good; } g_fsa[MAXFS];
static void *g_fs_seen[MAXFS];
static float g_fs_next = -1.0f;

static void fs_flush_locked(float now)
{
    int i;
    for (i = 0; i < MAXFS && g_fsa[i].fs; i++)
        if (g_fsa[i].n || g_fsa[i].good)
        {
            fprintf(g_log, "%.4f FSA fs=%p w=%p tgt=%p n=%ld good=%ld\n", now, g_fsa[i].fs, g_fsa[i].w, g_fsa[i].tgt,
                    g_fsa[i].n, g_fsa[i].good);
            g_fsa[i].n = g_fsa[i].good = 0;
        }
}

static int fs_slot_locked(void *fs, void *w, void *tgt)
{
    int i;
    float now = gtime();
    if (g_fs_next < 0.0f) g_fs_next = now + 1.0f;
    if (now >= g_fs_next) { fs_flush_locked(now); g_fs_next = now + 1.0f; }
    for (i = 0; i < MAXFS; i++)
    {
        if (g_fs_seen[i] == fs) break;
        if (g_fs_seen[i] == NULL)
        {
            const char *nm = NULL;
            g_fs_seen[i] = fs;
            if (!IsBadReadPtr((BYTE *)fs + 0x0C, 4)) nm = *(const char **)((BYTE *)fs + 0x0C);
            fprintf(g_log, "%.4f FSN fs=%p name=%s\n", now, fs, (nm && !IsBadStringPtrA(nm, 64)) ? nm : "?");
            break;
        }
    }
    for (i = 0; i < MAXFS; i++)
    {
        if (g_fsa[i].fs == fs && g_fsa[i].w == w) { g_fsa[i].tgt = tgt; return i; }
        if (g_fsa[i].fs == NULL) { g_fsa[i].fs = fs; g_fsa[i].w = w; g_fsa[i].tgt = tgt; return i; }
    }
    return -1;
}

static void (__fastcall *o_FireSysAt)(void *, void *, void *, void *, void *);
static void __fastcall h_FireSysAt(void *fs, void *edx, void *w, void *tgt, void *sub)
{
    int i;
    EnterCriticalSection(&g_cs);
    if (g_log && (i = fs_slot_locked(fs, w, tgt)) >= 0) g_fsa[i].n++;
    LeaveCriticalSection(&g_cs);
    o_FireSysAt(fs, edx, w, tgt, sub);
}

static char (__fastcall *o_GoodShot)(void *, void *, void *, void *, void *);
static char __fastcall h_GoodShot(void *fs, void *edx, void *w, void *tgt, void *sub)
{
    int i;
    char r = o_GoodShot(fs, edx, w, tgt, sub);
    if (r)
    {
        EnterCriticalSection(&g_cs);
        if (g_log && (i = fs_slot_locked(fs, w, tgt)) >= 0) g_fsa[i].good++;
        LeaveCriticalSection(&g_cs);
    }
    return r;
}

/* --- predicted-position inputs (added 2026-10-17) ---
 *   0x005A0B50 PredictedPosition core: out = pos + v*t + 0.5*a*t^2, stack args (out, pos, v, a, float t), ret 0x14;
 *   ECX is not used. Called by the SWIG GetPredictedPosition wrapper (Python AI: TorpedoRun, FireScript lead) and by
 *   compiled callers (OptimizedFireScript 0x484c42, ...). Throttled: at most one row per caller per 0.25 s game time.
 *   PP caller=<ret> pos=x,y,z v=x,y,z a=x,y,z t=<s>                                                              */
#define MAXPP 16
static struct { DWORD caller; float next; } g_pp[MAXPP];
static void (__fastcall *o_Pred)(void *, void *, float *, float *, float *, float *, float);
static void __fastcall h_Pred(void *ecx, void *edx, float *res, float *pos, float *v, float *a, float t)
{
    DWORD caller = (DWORD)__builtin_return_address(0);
    float now = gtime();
    int i, emit = 0;
    EnterCriticalSection(&g_cs);
    for (i = 0; i < MAXPP; i++)
    {
        if (g_pp[i].caller == caller || g_pp[i].caller == 0)
        {
            if (g_pp[i].caller == 0 || now >= g_pp[i].next) { g_pp[i].caller = caller; g_pp[i].next = now + 0.25f; emit = 1; }
            break;
        }
    }
    LeaveCriticalSection(&g_cs);
    if (emit && pos && v && a)
        out("PP caller=%08lx pos=%.3f,%.3f,%.3f v=%.4f,%.4f,%.4f a=%.4f,%.4f,%.4f t=%.4f\n", caller,
            pos[0], pos[1], pos[2], v[0], v[1], v[2], a[0], a[1], a[2], t);
    o_Pred(ecx, edx, res, pos, v, a, t);
}

struct hk { DWORD addr; const char *pro; int n; void *det; void **orig; const char *name; };
static struct hk hooks[] = {
    { 0x005AF010, "\x53\x55\x56\x8B\x74\x24\x10", 7, h_WeaponHit, (void **)&o_WeaponHit, "WeaponHitHandler" },
    { 0x005AF160, NULL, 0, h_ShieldPath, (void **)&o_ShieldPath, "ShieldHitPath" },
    { 0x005AF420, "\x8B\x44\x24\x04\x8B\x50\x2C", 7, h_ApplyWeapon, (void **)&o_ApplyWeapon, "ApplyWeaponDamage" },
    { 0x00594020, "\x64\xA1\x00\x00\x00\x00", 6, h_DoDamage, (void **)&o_DoDamage, "DoDamage" },
    { 0x005AFD70, "\x6A\xFF\x68\x58\xB9\x87\x00", 7, h_Distrib, (void **)&o_Distrib, "SubsystemDamageDistributor" },
    { 0x005AF4A0, "\x83\xEC\x08\x57\x8B\xF9", 6, h_SubDamage, (void **)&o_SubDamage, "SubsystemDamage" },
    { 0x0056C470, "\x8B\x44\x24\x04\x56\x8B\xF1", 7, h_SetCond, (void **)&o_SetCond, "SetCondition" },
    { 0x0056A5C0, "\x8B\x41\x18\x56\x8B\x74\x24\x08", 8, h_SetShields, (void **)&o_SetShields, "SetCurShields" },
    { 0x005AC470, "\x8B\x81\xCC\x02\x00\x00\x85\xC0\x74\x65", 10, h_SetImpulse, (void **)&o_SetImpulse, "SetImpulse" },
    { 0x005AC590, "\x8B\x81\xCC\x02\x00\x00\x85\xC0\x74\x3F", 10, h_SetSpeed, (void **)&o_SetSpeed, "SetSpeed" },
    { 0x00483500, "\x83\xEC\x18\x53\x55\x8B\x6C\x24\x28", 9, h_FireSysAt, (void **)&o_FireSysAt, "FireSystemAtTarget" },
    { 0x00484570, "\x6A\xFF\x68\x8C\x48\x87\x00", 7, h_GoodShot, (void **)&o_GoodShot, "CheckGoodShot" },
    { 0x005A0B50, "\x83\xEC\x24\x8B\x44\x24\x30", 7, h_Pred, (void **)&o_Pred, "PredictedPosition" },
};

static DWORD WINAPI flusher(LPVOID a)
{
    for (;;) { Sleep(500); EnterCriticalSection(&g_cs); fflush(g_log); LeaveCriticalSection(&g_cs); }
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved)
{
    if (reason == DLL_PROCESS_ATTACH)
    {
        char path[MAX_PATH], *slash;
        unsigned i;
        DisableThreadLibraryCalls(inst);
        InitializeCriticalSection(&g_cs);
        GetModuleFileNameA(inst, path, sizeof(path));
        if ((slash = strrchr(path, '\\'))) strcpy(slash + 1, "CombatTap.log");
        g_log = fopen(path, "w");
        if (!g_log) return TRUE;
        setvbuf(g_log, NULL, _IOFBF, 1 << 20);
        fprintf(g_log, "# CombatTap 1\n");
        if (MH_Initialize() != MH_OK) { fprintf(g_log, "# MH_Initialize failed\n"); return TRUE; }
        for (i = 0; i < sizeof(hooks) / sizeof(hooks[0]); i++)
        {
            struct hk *k = &hooks[i];
            if (k->pro && memcmp((void *)k->addr, k->pro, k->n))
            {
                fprintf(g_log, "# hook %s 0x%08lx SKIPPED: prologue mismatch\n", k->name, k->addr);
                continue;
            }
            if (MH_CreateHook((void *)k->addr, k->det, k->orig) == MH_OK && MH_EnableHook((void *)k->addr) == MH_OK)
                fprintf(g_log, "# hook %s 0x%08lx ok\n", k->name, k->addr);
            else
                fprintf(g_log, "# hook %s 0x%08lx FAILED\n", k->name, k->addr);
        }
        fflush(g_log);
        CloseHandle(CreateThread(NULL, 0, flusher, NULL, 0, NULL));
    }
    return TRUE;
}
