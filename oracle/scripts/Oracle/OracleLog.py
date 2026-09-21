# OracleLog -- the only write path that works inside stbc.exe is the
# engine's ConfigMapping.SaveConfigFile.  Python 1.5.
#
#   mark(key, value)  -> [OracleBoot] in oracle_boot.cfg  (progress markers)
#   meta(key, value)  -> m_<key> in every output chunk
#   row(line)         -> buffered rows, flushed by flush() in chunks of
#                        CHUNK rows: oracle_out.cfg, oracle_out1.cfg, ...
#
# Every emitted value is capped at 180 chars: over-long cfg values corrupt the
# write and hard-crash the game (console-probe-workflow.md).
import App
import sys

_cfg = App.g_kConfigMapping
_marks = []
_rows = []
_meta = []
CHUNK = 400

def _short(v):
    v = str(v)
    if len(v) > 180:
        v = v[:180]
    return v

def mark(key, value):
    try:
        _marks.append((key, _short(value)))
        i = 0
        for k, v in _marks:
            _cfg.SetStringValue("OracleBoot", "%02d_%s" % (i, k), v)
            i = i + 1
        _cfg.SaveConfigFile("oracle_boot.cfg")
    except:
        pass

def pulse(value):
    """Heartbeat: one key rewritten in place (crash forensics), not a mark."""
    try:
        _cfg.SetStringValue("OracleBoot", "zz_pulse", _short(value))
        _cfg.SaveConfigFile("oracle_boot.cfg")
    except:
        pass

def exc():
    return "%s %s" % (str(sys.exc_type), str(sys.exc_value))

def meta(key, value):
    _meta.append((key, _short(value)))

def row(line):
    _rows.append(_short(line))

def _clear_section():
    # ConfigMapping keeps every key ever set; blank the row keys between
    # chunks so chunk N does not carry chunk N-1's rows.
    i = 0
    while i < CHUNK:
        _cfg.SetStringValue("OracleOut", "r%04d" % i, "")
        i = i + 1

def flush(done):
    try:
        for k, v in _meta:
            _cfg.SetStringValue("OracleOut", "m_" + k, v)
        n = len(_rows)
        nchunks = (n + CHUNK - 1) / CHUNK
        if nchunks == 0:
            nchunks = 1
        c = 0
        while c < nchunks:
            _clear_section()
            base = c * CHUNK
            i = 0
            while i < CHUNK and base + i < n:
                _cfg.SetStringValue("OracleOut", "r%04d" % i, _rows[base + i])
                i = i + 1
            _cfg.SetIntValue("OracleOut", "chunk", c)
            _cfg.SetIntValue("OracleOut", "chunks", nchunks)
            _cfg.SetIntValue("OracleOut", "rows_in_chunk", i)
            _cfg.SetIntValue("OracleOut", "rows", n)
            _cfg.SetIntValue("OracleOut", "done", done)
            if c == 0:
                _cfg.SaveConfigFile("oracle_out.cfg")
            else:
                _cfg.SaveConfigFile("oracle_out%d.cfg" % c)
            c = c + 1
        return 1
    except:
        mark("flush_error", exc())
        return 0
