"""AL: alert-level events. The original ShipClass applies ET_SET_ALERT_LEVEL sent to it (QuickBattle StartSimulation
sends RED_ALERT to the player; the XO menu's alert buttons forward the same event)."""


def test_alert_event_applies(oracle, record):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=3000.0)
    App = s.App
    ship = s.atk
    ship.SetAlertLevel(App.ShipClass.GREEN_ALERT)
    s.step(2)
    ev = App.TGIntEvent_Create()
    ev.SetDestination(ship)
    ev.SetEventType(App.ET_SET_ALERT_LEVEL)
    ev.SetInt(App.ShipClass.RED_ALERT)
    App.g_kEventManager.AddEvent(ev)
    s.step(3)
    lvl = ship.GetAlertLevel()
    shields_up = bool(ship.GetShields().IsOn())
    record("AL1", "Alert", "ET_SET_ALERT_LEVEL(RED) sent to the ship (battle start, XO Red Alert button)",
           "red alert, shields up", f"alert {lvl} ({'red' if lvl == App.ShipClass.RED_ALERT else 'not red'}), shields {'up' if shields_up else 'down'}",
           "match" if lvl == App.ShipClass.RED_ALERT and shields_up else "wrong")
