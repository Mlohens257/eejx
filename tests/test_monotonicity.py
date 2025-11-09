from ee_mvp import DEFAULT_CONFIG
from ee_mvp.nec import ampacity_adjusted
from ee_mvp.vd import voltage_drop_percent


def test_ampacity_increases_with_size():
    sizes = ["#3", "#2", "#1", "1/0", "2/0", "3/0", "4/0", "250", "300", "350", "400", "500"]
    values = [
        ampacity_adjusted(size, "Cu", "THHN", 75, 30.0, None, 3, 75, 1)
        for size in sizes
    ]
    assert all(later > earlier for earlier, later in zip(values, values[1:]))


def test_voltage_drop_decreases_with_size():
    base_current = 100.0
    voltage = 480.0
    length = 100.0
    sizes = ["#3", "#2", "#1", "1/0", "2/0", "3/0", "4/0", "250"]
    drops = [
        voltage_drop_percent(base_current, voltage, "Cu", size, length, "EMT", 1, DEFAULT_CONFIG["pf"])
        for size in sizes
    ]
    assert all(later < earlier for earlier, later in zip(drops, drops[1:]))
