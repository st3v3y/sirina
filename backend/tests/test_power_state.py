"""Power state parsing and the user-facing note shown while processing."""
from app.audio import power

BATT_AC = "Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t100%; charged;"
BATT_BAT = "Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t80%; discharging;"
SETTINGS_LPM_ON = "System-wide power settings:\nCurrently in use:\n lowpowermode         1\n sleep                1\n"
SETTINGS_LPM_OFF = "Currently in use:\n lowpowermode         0\n"


def test_parse_ac_without_low_power():
    assert power.parse_power_state(BATT_AC, SETTINGS_LPM_OFF) == {"on_battery": False, "low_power": False}


def test_parse_battery_with_low_power():
    assert power.parse_power_state(BATT_BAT, SETTINGS_LPM_ON) == {"on_battery": True, "low_power": True}


def test_note_prefers_low_power_message():
    assert "Low Power Mode" in power.power_note({"on_battery": True, "low_power": True})
    assert "battery" in power.power_note({"on_battery": True, "low_power": False})
    assert power.power_note({"on_battery": False, "low_power": False}) is None


def test_power_state_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(power, "_power_cache", None)
    monkeypatch.setattr(power.sys, "platform", "darwin")

    def fake(*args):
        calls.append(args)
        return BATT_BAT if args == ("-g", "batt") else SETTINGS_LPM_OFF

    monkeypatch.setattr(power, "_pmset", fake)
    assert power.power_state(now=100.0)["on_battery"] is True
    power.power_state(now=110.0)
    assert len(calls) == 2  # second call served from cache
    power.power_state(now=200.0)
    assert len(calls) == 4
