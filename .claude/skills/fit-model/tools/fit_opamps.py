"""Build our own op-amp models (D-162) from each sheet's typical figures: .lib and .json.

python .claude/skills/fit-model/tools/fit_opamps.py ID [ID...]
then measure: add_model.py .claude/skills/fit-model/tools/fit_opamps.py ID
(both in the dev image, `make run CMD=…`).
Each PART holds the OpAmpFit figures, the record fields and its validations (no `simulated`:
add_model.py measures them). SPECS (for add_model.py) re-measures every record.
"""

import importlib.util
import json
import math
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("fm", "scripts/fit_models.py")
fm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fm)

ROOT = Path("library/models/opamp")
DIP8 = {"a.out": 1, "a.-": 2, "a.+": 3, "V-": 4, "b.+": 5, "b.-": 6, "b.out": 7, "V+": 8}
LICENCE = "Our own model built from the maker's data sheet (D-162): the values are Solum Builder's"


def db(v_per_mv: float) -> float:
    return 20 * math.log10(v_per_mv * 1e3)


PARTS: dict[str, dict] = {}
METHOD = (
    "A small macromodel (scripts/fit_models.py opamp_card, D-162): a tanh transconductance stage "
    "limited to 10 µA into C1 sets the slew rate, gm the unity-gain crossing and R1 the "
    "open-loop gain; "
    "a second pole gives the phase margin; diode clamps and an output resistance set the swing; "
    "the "
    "supply current is drawn from the rails."
)
NOTE = (
    "Input bias, offset, noise, common-mode limits and the output's current limit are not "
    "modelled: the "
    "input stage is ideal (1 TΩ)."
)

ON5532 = "onsemi NE5532/D Rev. 2 (September 2013)"
TI5532 = "TI NE5532 data sheet SLOS075K (revised December 2025)"
PARTS["NE5532"] = {
    "description": "NE5532 low-noise bipolar dual op-amp, ±18 V max (our model from onsemi's "
    "and TI's sheets)",
    "sheet": f"{ON5532} and {TI5532}, NE5532 at ±15 V",
    "manufacturer": "onsemi / Texas Instruments",
    "url": "https://www.ti.com/lit/ds/symlink/ne5532.pdf",
    "retrieved": "2026-10-29",
    "figure": "onsemi electrical characteristics at ±15 V: AVOL 100 V/mV typ, GBW 10 MHz, slew "
    "rate 9 V/µs, follower "
    "overshoot 10 % (100 "
    "mVp-p, "
    "CL "
    "100 pF, RL 600 Ω), "
    "supply "
    "current 8 mA for "
    "both "
    "amplifiers, VOUT "
    "±13.5 "
    "V "
    "typ "
    "at RL ≥ 2 kΩ and "
    "±13 "
    "V "
    "at "
    "600 "
    "Ω",
    "method": "Phase margin 65.3° fitted so a follower at the sheet's load (600 Ω, 100 pF) "
    "overshoots 10 % (.claude/skills/fit-model/tools/opamp_pm_fit.py); output resistance 33.5 Ω "
    "and clamps 1.27 V "
    "from "
    "each "
    "rail fitted to both "
    "swing "
    "rows "
    "(simulated 1.47 V "
    "at "
    "2 "
    "kΩ, "
    "1.97 V at 600 Ω). "
    "Checked: "
    "slews at 8.85 V/µs.",
    "fit": dict(
        aol_db=100.0,
        gbw=10e6,
        slew=9e6,
        phase_margin=65.3,
        rout=33.5,
        head_pos=1.27,
        head_neg=1.27,
        iq=8e-3 / 2,
    ),
    "ratings": {
        "vs_max": 36.0,
        "cm_neg_headroom": 3.0,
        "cm_pos_headroom": 3.0,
        "out_neg_headroom": 1.5,
        "out_pos_headroom": 1.5,
    },
    "rating_source": (
        f"{TI5532}: vs_max ±18 V (Absolute Maximum Ratings; onsemi allows ±22 V); common-mode "
        f"range VICR ±12 V min at ±15 V; output headroom from {ON5532}: VOUT ±13.5 V typ at "
        "RL ≥ 2 kΩ (no 10 kΩ row)"
    ),
    "pinout_source": f"{TI5532}, D/P/PS package pinout (onsemi's N/D8 the same)",
    "validation": [
        {
            "quantity": "aol_db",
            "conditions": {"supply": 15.0},
            "datasheet": {
                "min": db(25),
                "typ": db(100),
                "source": TI5532,
                "note": "AVD 25 V/mV min, 100 V/mV typ, ±15 V, RL ≥ 2 kΩ, VO = ±10 V (onsemi "
                "the same)",
            },
        },
        {
            "quantity": "gbw",
            "conditions": {"supply": 15.0},
            "datasheet": {
                "typ": 10e6,
                "source": ON5532,
                "note": "GBW 10 MHz typ, CL = 100 pF, RL = 600 Ω; 10 % follower overshoot at "
                "the same load, so "
                "phase "
                "margin 65.3° fitted to it; TI's Rev K gives 12 MHz unity-gain "
                "bandwidth but still says 10 MHz in its description",
            },
        },
        {
            "quantity": "swing_pos",
            "conditions": {"supply": 15.0, "load": 2000.0},
            "datasheet": {
                "typ": 1.5,
                "max": 2.0,
                "source": f"{ON5532}: VOUT ±13.5 V typ, ±13 V min, RL ≥ 2 kΩ",
            },
        },
        {
            "quantity": "swing_neg",
            "conditions": {"supply": 15.0, "load": 2000.0},
            "datasheet": {
                "typ": 1.5,
                "max": 2.0,
                "source": f"{ON5532}: VOUT ±13.5 V typ, ±13 V min, RL ≥ 2 kΩ",
            },
        },
        {
            "quantity": "swing_pos",
            "conditions": {"supply": 15.0, "load": 600.0},
            "datasheet": {
                "typ": 2.0,
                "max": 3.0,
                "source": f"{ON5532}: VOUT ±13 V typ, ±12 V min, RL ≥ 600 Ω",
            },
        },
        {
            "quantity": "swing_neg",
            "conditions": {"supply": 15.0, "load": 600.0},
            "datasheet": {
                "typ": 2.0,
                "max": 3.0,
                "source": f"{ON5532}: VOUT ±13 V typ, ±12 V min, RL ≥ 600 Ω",
            },
        },
    ],
}

TI833 = "TI LM833 data sheet SLOS481B (revised October 2014)"
PARTS["LM833"] = {
    "description": "LM833 high-speed audio bipolar dual op-amp, ±18 V max (our model from TI's "
    "sheet)",
    "sheet": f"{TI833}, at ±15 V",
    "manufacturer": "Texas Instruments",
    "url": "https://www.ti.com/lit/ds/symlink/lm833.pdf",
    "retrieved": "2026-10-29",
    "figure": "Electrical characteristics at ±15 V: AVD 110 dB typ, unity-gain frequency 9 MHz "
    "(GBW 16 MHz at 100 "
    "kHz), "
    "slew "
    "rate 7 V/µs, phase "
    "margin "
    "55°, "
    "open-loop output "
    "impedance "
    "37 "
    "Ω, 2.05 mA per channel, "
    "VOM "
    "14.1 / −14.6 V typ "
    "at "
    "10 "
    "kΩ",
    "method": "Output resistance the sheet's 37 Ω, clamps 0.85 V under V+ and 0.35 V over V− so "
    "the 10 kΩ swing lands "
    "on "
    "the "
    "typical (simulated "
    "0.87 "
    "and "
    "0.37 V). Checked: "
    "slews "
    "at "
    "6.87 V/µs.",
    "fit": dict(
        aol_db=110.0,
        gbw=9e6,
        slew=7e6,
        phase_margin=55.0,
        rout=37.0,
        head_pos=0.848,
        head_neg=0.346,
        iq=2.05e-3,
    ),
    "ratings": {
        "vs_max": 36.0,
        "cm_neg_headroom": 2.0,
        "cm_pos_headroom": 2.0,
        "out_neg_headroom": 0.4,
        "out_pos_headroom": 0.9,
    },
    "rating_source": (
        f"{TI833}: vs_max ±18 V (Absolute Maximum Ratings); common-mode range VICR ±13 V min; "
        "output headroom VOM+ 14.1 V and VOM– –14.6 V typ at RL = 10 kΩ"
    ),
    "pinout_source": f"{TI833}, D/DGK/P package pinout",
    "validation": [
        {
            "quantity": "aol_db",
            "conditions": {"supply": 15.0},
            "datasheet": {
                "min": 90.0,
                "typ": 110.0,
                "source": TI833,
                "note": "AVD 90 dB min, 110 dB typ, RL ≥ 2 kΩ, VO = ±10 V",
            },
        },
        {
            "quantity": "gbw",
            "conditions": {"supply": 15.0},
            "datasheet": {
                "typ": 9e6,
                "source": TI833,
                "note": "B1 unity-gain frequency 9 MHz typ, open loop (GBW 16 MHz typ at 100 kHz); "
                "phase margin 55° typ, open-loop output impedance 37 Ω",
            },
        },
        {
            "quantity": "swing_pos",
            "conditions": {"supply": 15.0, "load": 10000.0},
            "datasheet": {
                "typ": 0.9,
                "max": 1.5,
                "source": f"{TI833}: VOM+ 14.1 V typ, 13.5 V min, RL = 10 kΩ",
            },
        },
        {
            "quantity": "swing_neg",
            "conditions": {"supply": 15.0, "load": 10000.0},
            "datasheet": {
                "typ": 0.4,
                "max": 1.0,
                "source": f"{TI833}: VOM– –14.6 V typ, –14 V min, RL = 10 kΩ",
            },
        },
        {
            "quantity": "swing_pos",
            "conditions": {"supply": 15.0, "load": 2000.0},
            "datasheet": {
                "typ": 1.2,
                "max": 1.8,
                "source": f"{TI833}: VOM+ 13.8 V typ, 13.2 V min, RL = 2 kΩ",
            },
        },
        {
            "quantity": "swing_neg",
            "conditions": {"supply": 15.0, "load": 2000.0},
            "datasheet": {
                "typ": 1.3,
                "max": 1.8,
                "source": f"{TI833}: VOM– –13.7 V typ, –13.2 V min, RL = 2 kΩ",
            },
        },
    ],
}

TI2134 = "TI OPAx134 data sheet SBOS058B (revised November 2024)"
PARTS["OPA2134"] = {
    "description": "OPA2134 FET-input audio dual op-amp, ±18 V max (our model from TI's sheet)",
    "sheet": f"{TI2134}, at ±15 V",
    "manufacturer": "Texas Instruments",
    "url": "https://www.ti.com/lit/ds/symlink/opa2134.pdf",
    "retrieved": "2026-10-29",
    "figure": "Electrical characteristics at ±15 V: AOL 120 dB typ, GBW 8 MHz, slew rate 20 "
    "V/µs, open-loop output "
    "impedance 10 Ω at "
    "10 "
    "kHz, "
    "4 "
    "mA "
    "per amplifier, swing "
    "limits "
    "(V+) − 1.2 V and "
    "(V−) "
    "+ "
    "0.5 "
    "V "
    "at 10 kΩ; phase margin "
    "about "
    "45° read off Figure "
    "5-9",
    "method": "Output resistance the sheet's 10 Ω, clamps 1.1 V under V+ and 0.4 V over V− so "
    "the swing sits inside "
    "the "
    "10 "
    "kΩ and 2 kΩ limits "
    "(the "
    "sheet "
    "gives no typical). "
    "Checked: "
    "slews at 19.9 V/µs.",
    "fit": dict(
        aol_db=120.0,
        gbw=8e6,
        slew=20e6,
        phase_margin=45.0,
        rout=10.0,
        head_pos=1.1,
        head_neg=0.4,
        iq=4e-3,
    ),
    "ratings": {
        "vs_max": 36.0,
        "cm_neg_headroom": 2.5,
        "cm_pos_headroom": 3.5,
        "out_neg_headroom": 0.5,
        "out_pos_headroom": 1.2,
    },
    "rating_source": (
        f"{TI2134}: vs_max 36 V (Absolute Maximum Ratings); common-mode range (V–) + 2.5 V to "
        "(V+) – 3.5 V; output headroom from the swing limits at RL = 10 kΩ, (V+) – 1.2 V and "
        "(V–) + 0.5 V (the sheet gives no typical)"
    ),
    "pinout_source": f"{TI2134}, OPA2134 D and P package pinout",
    "validation": [
        {
            "quantity": "aol_db",
            "conditions": {"supply": 15.0},
            "datasheet": {
                "min": 104.0,
                "typ": 120.0,
                "source": TI2134,
                "note": "AOL 104 dB min, 120 dB typ, RL = 10 kΩ and 2 kΩ",
            },
        },
        {
            "quantity": "gbw",
            "conditions": {"supply": 15.0},
            "datasheet": {
                "typ": 8e6,
                "source": TI2134,
                "note": "GBW 8 MHz typ; phase margin about 45° read off Figure 5-9; open-loop "
                "output impedance 10 Ω at 10 kHz",
            },
        },
        {
            "quantity": "swing_pos",
            "conditions": {"supply": 15.0, "load": 10000.0},
            "datasheet": {"max": 1.2, "source": f"{TI2134}: VO ≥ (V+) – 1.2 V, RL = 10 kΩ"},
        },
        {
            "quantity": "swing_neg",
            "conditions": {"supply": 15.0, "load": 10000.0},
            "datasheet": {"max": 0.5, "source": f"{TI2134}: VO ≤ (V–) + 0.5 V, RL = 10 kΩ"},
        },
        {
            "quantity": "swing_pos",
            "conditions": {"supply": 15.0, "load": 2000.0},
            "datasheet": {"max": 1.5, "source": f"{TI2134}: VO ≥ (V+) – 1.5 V, RL = 2 kΩ"},
        },
        {
            "quantity": "swing_neg",
            "conditions": {"supply": 15.0, "load": 2000.0},
            "datasheet": {"max": 1.2, "source": f"{TI2134}: VO ≤ (V–) + 1.2 V, RL = 2 kΩ"},
        },
    ],
}

NJ4580 = "Nisshinbo Micro Devices NJM4580 data sheet (Ver. 20260723)"
PARTS["JRC4580"] = {
    "description": "JRC4580 (NJM4580) low-noise bipolar dual op-amp, ±18 V max (our model from "
    "Nisshinbo's sheet)",
    "sheet": f"{NJ4580}, at ±15 V; phase margin assumed (D-169)",
    "manufacturer": "Nisshinbo (New Japan Radio)",
    "url": "https://www.nisshinbo-microdevices.co.jp/en/pdf/datasheet/NJM4580_E.pdf",
    "retrieved": "2026-11-02",
    # GB 15 MHz is the gain at 10 kHz times 10 kHz: held, with the assumed 60°
    # (the user, 2026-11-02)
    "figure": "Electrical characteristics at ±15 V: AV 110 dB typ, GB 15 MHz at 10 kHz, slew "
    "rate 5 V/µs, supply "
    "current "
    "6 "
    "mA, VOM ±13.5 V typ "
    "at "
    "RL "
    "≥ "
    "2 "
    "kΩ; Maximum Output "
    "Voltage "
    "vs. "
    "Load Resistance graph, "
    "about "
    "±14 V at 10 kΩ. No "
    "phase "
    "margin",
    "method": "The gain at 10 kHz held to the sheet's GB (the crossing set to 15 MHz × cos "
    "30°); phase margin "
    "60° "
    "assumed, as the user "
    "chose "
    "(D-169): the sheet's "
    "only "
    "phase data, a 40 "
    "dB "
    "closed-loop graph, "
    "fits "
    "a "
    "slower part (9.3 "
    "MHz, "
    "about "
    "31°) that disagrees "
    "with "
    "its "
    "own table. Output "
    "resistance "
    "93 Ω and clamps 0.87 "
    "V "
    "from "
    "each rail fitted "
    "to "
    "the "
    "2 "
    "kΩ "
    "row and the 10 kΩ "
    "graph "
    "point.",
    "fit": dict(
        aol_db=110.0,
        gbw=15e6 * math.cos(math.radians(30)),
        slew=5e6,
        phase_margin=60.0,
        rout=93.0,
        head_pos=0.87,
        head_neg=0.87,
        iq=6e-3 / 2,
    ),
    "ratings": {
        "vs_max": 36.0,
        "cm_neg_headroom": 3.0,
        "cm_pos_headroom": 3.0,
        "out_neg_headroom": 1.0,
        "out_pos_headroom": 1.0,
    },
    "rating_source": (
        f"{NJ4580}: vs_max ±18 V (Absolute Maximum Ratings); common-mode range VICM ±12 V min; "
        "output headroom about 1.0 V from each rail at RL = 10 kΩ, read off the Maximum Output "
        "Voltage vs. Load Resistance graph (the table gives ±13.5 V typ at RL ≥ 2 kΩ)"
    ),
    "pinout_source": f"{NJ4580}, pin configuration (DIP8, SOP8 and others the same)",
    "validation": [
        {
            "quantity": "aol_db",
            "conditions": {"supply": 15.0},
            "datasheet": {
                "min": 90.0,
                "typ": 110.0,
                "source": NJ4580,
                "note": "AV 90 dB min, 110 dB typ, RL ≥ 2 kΩ, VO = ±10 V",
            },
        },
        {
            "quantity": "gbw",
            "conditions": {"supply": 15.0},
            "datasheet": {
                "typ": 15e6,
                "source": NJ4580,
                "note": "GB 15 MHz typ at f = 10 kHz (gain there times 10 kHz), held in the "
                "model; the "
                "sheet gives no phase margin, 60° assumed (the user, D-169), so the gain crosses "
                "1 near 13 MHz. Its 40 dB gain/phase graph fits a slower part (9.3 MHz, ~31°)",
            },
        },
        {
            "quantity": "swing_pos",
            "conditions": {"supply": 15.0, "load": 2000.0},
            "datasheet": {
                "typ": 1.5,
                "max": 3.0,
                "source": f"{NJ4580}: VOM ±13.5 V typ, ±12 V min, RL ≥ 2 kΩ",
            },
        },
        {
            "quantity": "swing_neg",
            "conditions": {"supply": 15.0, "load": 2000.0},
            "datasheet": {
                "typ": 1.5,
                "max": 3.0,
                "source": f"{NJ4580}: VOM ±13.5 V typ, ±12 V min, RL ≥ 2 kΩ",
            },
        },
        {
            "quantity": "swing_pos",
            "conditions": {"supply": 15.0, "load": 10000.0},
            "datasheet": {
                "typ": 1.0,
                "tol": 0.3,
                "source": f"{NJ4580}: Maximum Output Voltage vs. Load "
                "Resistance graph, about +14.0 V at 10 kΩ (read off the figure)",
            },
        },
    ],
}

NJ3404 = "Nisshinbo Micro Devices NJM3404A data sheet (Ver. 20260723)"
PARTS["NJM3404A"] = {
    "description": "NJM3404A single-supply bipolar dual op-amp (an improved NJM2904/LM358), 36 "
    "V max: the Boss DS-1's "
    "(our "
    "model from Nisshinbo's "
    "sheet)",
    "sheet": f"{NJ3404}, at ±15 V and at a single 5 V; phase margin assumed (D-169)",
    "manufacturer": "Nisshinbo (New Japan Radio)",
    "url": "https://www.nisshinbo-microdevices.co.jp/en/pdf/datasheet/NJM3404A_E.pdf",
    "retrieved": "2026-11-10",
    "figure": "Electrical characteristics at ±15 V: AV 100 dB typ (88 min, RL > 2 kΩ), unity "
    "gain bandwidth 1.2 "
    "MHz, "
    "slew "
    "rate 1.2 V/µs, operating "
    "current 2.0 mA (both "
    "amplifiers), VOM "
    "±14 "
    "V "
    "typ, "
    "±13 min at RL = 2 "
    "kΩ, "
    "VICM "
    "−15 "
    "to +13 V; Maximum "
    "Output "
    "Voltage Swing vs. "
    "Load "
    "Resistance graph "
    "(V+ "
    "= "
    "5 "
    "V): "
    "+VOM about 4.0 V "
    "from "
    "1 "
    "kΩ "
    "to "
    "10 kΩ, −VOM about "
    "1 "
    "mV. "
    "No "
    "phase margin",
    "method": "Unity gain bandwidth 1.2 MHz as the table gives it, phase margin 60° assumed as "
    "for the other sheets "
    "without "
    "one (D-169). A single-supply "
    "output like the LM358's: "
    "the "
    "clamps are 0.95 V "
    "from "
    "V+ "
    "and "
    "5 mV from V− (the "
    "5 "
    "V "
    "graph: "
    "+VOM about 4.0 V, "
    "−VOM "
    "about "
    "1 "
    "mV), with 10 Ω of "
    "output "
    "resistance, so ±15 "
    "V "
    "into "
    "2 "
    "kΩ "
    "swings to 1.0 V of "
    "V+ "
    "(the "
    "table's ±14 V typ). "
    "The "
    "table's −14 V is "
    "the "
    "output "
    "sinking 7 mA into "
    "a "
    "load "
    "at "
    "the middle, which "
    "this "
    "output "
    "stage doesn't model: "
    "it "
    "swings "
    "nearer V−.",
    "fit": dict(
        aol_db=100.0,
        gbw=1.2e6,
        slew=1.2e6,
        phase_margin=60.0,
        rout=10.0,
        head_pos=0.95,
        head_neg=0.005,
        iq=2.0e-3 / 2,
    ),
    "ratings": {
        "vs_max": 36.0,
        "cm_neg_headroom": 0.0,
        "cm_pos_headroom": 2.0,
        "out_neg_headroom": 0.005,
        "out_pos_headroom": 1.0,
    },
    "rating_source": (
        f"{NJ3404}: vs_max 36 V (Absolute Maximum Ratings); common-mode range VICM −15 to +13 V "
        "at ±15 V (down to V−, 2 V short of V+); output about 1.0 V short of V+ and within a "
        "few mV of "
        "V− at V+ = 5 V, RL 1 kΩ to 10 kΩ, read off the Maximum Output Voltage Swing vs. Load "
        "Resistance graph"
    ),
    "pinout_source": f"{NJ3404}, pin configuration (NJM3404AD DIP8, NJM3404AM, NJM3404AV the "
    "same): 1 A output, "
    "2 "
    "A "
    "−input, "
    "3 A +input, 4 V−, "
    "5 "
    "B "
    "+input, "
    "6 B −input, 7 B output, "
    "8 "
    "V+",
    "validation": [
        {
            "quantity": "aol_db",
            "conditions": {"supply": 15.0},
            "datasheet": {
                "min": 88.0,
                "typ": 100.0,
                "source": NJ3404,
                "note": "AV 88 dB min, 100 dB typ, RL > 2 kΩ",
            },
        },
        {
            "quantity": "gbw",
            "conditions": {"supply": 15.0},
            "datasheet": {
                "typ": 1.2e6,
                "source": NJ3404,
                "note": "unity gain bandwidth fT 1.2 MHz typ; no phase margin given, 60° "
                "assumed (D-169)",
            },
        },
        {
            "quantity": "swing_pos",
            "conditions": {"supply": 15.0, "load": 2000.0},
            "datasheet": {
                "typ": 1.0,
                "max": 2.0,
                "source": f"{NJ3404}: VOM ±14 V typ, ±13 V min, RL = 2 kΩ",
            },
        },
        {
            "quantity": "swing_neg",
            "conditions": {"supply": 15.0, "load": 2000.0},
            "datasheet": {
                "max": 2.0,
                "source": f"{NJ3404}: VOM ±14 V typ, ±13 V min, RL = 2 kΩ",
                "note": "the model swings nearer V− than the table's typical 1 V: its output "
                "stage follows the "
                "5 "
                "V "
                "graph's "
                "few mV and doesn't "
                "model "
                "sinking into a load "
                "at "
                "the "
                "middle",
            },
        },
    ],
}

MI5218 = (
    "Mitsubishi M5218AL/P/FP data sheet (data book pages 2-467 to 2-471, with the 8P2S-A "
    "outline of March "
    "1998)"
)
MI5218_URL = "https://www.retroamplis.com/WebRoot/StoreES2/Shops/62070367/65CC/B1C0/F3AA/400F/9D14/0A0C/6D0E/C92F/MITSUBISHI_M5218P_DATASHEET_-_RETROAMPLIS.pdf"
PARTS["M5218AL"] = {
    "description": "M5218AL dual low-noise op-amp (Mitsubishi; a 4558 type, SIL-8): the Boss "
    "BD-2's (our model "
    "from "
    "Mitsubishi's M5218AL/P/FP "
    "sheet)",
    "sheet": f"{MI5218}, at ±15 V; phase margin assumed (D-169)",
    "manufacturer": "Mitsubishi (Renesas)",
    "url": f"{MI5218_URL} (Retroamplis' copy)",
    "retrieved": "2026-11-10",
    "datasheet": MI5218_URL,
    "figure": "Electrical characteristics at ±15 V: GVO 110 dB typ (86 min, RL ≥ 2 kΩ), fT 7 "
    "MHz, SR 3.0 V/µs "
    "(GV "
    "= "
    "0 "
    "dB, "
    "RL = 2 kΩ), ICC 3.0 "
    "mA "
    "(both "
    "amplifiers), VOM "
    "±14 "
    "V "
    "typ "
    "at "
    "RL ≥ 10 kΩ and ±13 "
    "V "
    "at "
    "RL "
    "≥ "
    "2 "
    "kΩ, VCM ±14 V typ. "
    "The "
    "voltage "
    "gain vs frequency "
    "figure "
    "falls "
    "at 20 dB a decade "
    "to "
    "0 "
    "dB "
    "near "
    "7 MHz. No phase margin",
    "method": "The sheet names the M5218AL (SIL-8, outline 8P5) with the P and FP. Gain "
    "bandwidth 7 MHz and "
    "slew "
    "rate "
    "3.0 V/µs as the table "
    "gives "
    "them (Mitsubishi's "
    "1984 "
    "data "
    "book gave 2.2 V/µs "
    "for "
    "the "
    "M5218L), phase margin "
    "60° "
    "assumed (D-169). "
    "The "
    "output "
    "clamps 0.8 V from "
    "each "
    "rail "
    "behind 180 Ω, so "
    "it "
    "swings "
    "to "
    "1.05 V of the rails "
    "into "
    "10 "
    "kΩ "
    "and 1.97 V into 2 "
    "kΩ "
    "(the "
    "table's ±14 V and "
    "±13 "
    "V "
    "typ).",
    "fit": dict(
        aol_db=110.0,
        gbw=7e6,
        slew=3.0e6,
        phase_margin=60.0,
        rout=180.0,
        head_pos=0.8,
        head_neg=0.8,
        iq=3.0e-3 / 2,
    ),
    "ratings": {
        "vs_max": 36.0,
        "cm_neg_headroom": 1.0,
        "cm_pos_headroom": 1.0,
        "out_neg_headroom": 1.0,
        "out_pos_headroom": 1.0,
    },
    "rating_source": (
        f"{MI5218}: vs_max ±18 V (Absolute Maximum Ratings); common input voltage range ±14 V "
        "typ at ±15 V "
        "(1 V from each rail); maximum output voltage ±14 V typ at RL ≥ 10 kΩ"
    ),
    "package": {
        "name": "8-pin SIL",
        "pins": {"a.out": 1, "a.-": 2, "a.+": 3, "V-": 4, "b.+": 5, "b.-": 6, "b.out": 7, "V+": 8},
        "source": f"{MI5218}, pin configuration, outline 8P5 (AL): 1 output 1, 2 inverted input "
        "1, 3 non-inverted "
        "input "
        "1, "
        "4 "
        "(−) power supply, "
        "5 "
        "non-inverted input "
        "2, "
        "6 "
        "inverted input 2, "
        "7 "
        "output "
        "2, "
        "8 (+) power supply",
    },
    "validation": [
        {
            "quantity": "aol_db",
            "conditions": {"supply": 15.0},
            "datasheet": {
                "min": 86.0,
                "typ": 110.0,
                "source": MI5218,
                "note": "GVO 86 dB min, 110 dB typ, RL ≥ 2 kΩ, VO = ±10 V",
            },
        },
        {
            "quantity": "gbw",
            "conditions": {"supply": 15.0},
            "datasheet": {
                "typ": 7e6,
                "source": MI5218,
                "note": "gain bandwidth product fT 7 MHz typ; no phase margin given, 60° "
                "assumed (D-169)",
            },
        },
        {
            "quantity": "swing_pos",
            "conditions": {"supply": 15.0, "load": 10000.0},
            "datasheet": {
                "typ": 1.0,
                "max": 3.0,
                "source": f"{MI5218}: VOM ±14 V typ, ±12 V min, RL ≥ 10 kΩ",
            },
        },
        {
            "quantity": "swing_neg",
            "conditions": {"supply": 15.0, "load": 10000.0},
            "datasheet": {
                "typ": 1.0,
                "max": 3.0,
                "source": f"{MI5218}: VOM ±14 V typ, ±12 V min, RL ≥ 10 kΩ",
            },
        },
        {
            "quantity": "swing_pos",
            "conditions": {"supply": 15.0, "load": 2000.0},
            "datasheet": {
                "typ": 2.0,
                "max": 5.0,
                "source": f"{MI5218}: VOM ±13 V typ, ±10 V min, RL ≥ 2 kΩ",
            },
        },
    ],
}

IS3260 = "Intersil CA3260 data sheet FN1266 Rev. 7.00 (December 2009)"
PARTS["CA3260"] = {
    "description": "CA3260 BiMOS dual op-amp, MOSFET input and CMOS rail-to-rail output, 16 V max "
    "(our model from Intersil's sheet)",
    "sheet": f"{IS3260}, at V+ = 15 V, V– = 0 (±7.5 V)",
    "manufacturer": "Intersil (Renesas)",
    "url": "https://www.renesas.com/ja-jp/www/doc/datasheet/ca3260.pdf",
    "retrieved": "2026-11-02",
    "figure": "Electrical characteristics at V+ = 15 V, V− = 0: AOL 320 kV/V typ; at ±7.5 V: "
    "unity-gain crossover "
    "4 "
    "MHz, "
    "slew rate 10 V/µs, "
    "follower "
    "overshoot 10 % (CL "
    "25 "
    "pF, "
    "RL "
    "2 "
    "kΩ); total supply "
    "current "
    "9 "
    "mA "
    "with outputs at mid-supply; "
    "VOM+ 13.3 V typ at "
    "10 "
    "kΩ, "
    "within 10 mV of each "
    "rail "
    "unloaded",
    "method": "CMOS output: clamps 35 mV from each rail and an output resistance of 1.28 kΩ "
    "(VOM+ 1.7 V short "
    "at "
    "1.33 "
    "mA). "
    "Phase margin 65.6° "
    "fitted "
    "so "
    "a "
    "follower at the sheet's "
    "load "
    "overshoots 10 %; "
    "internal "
    "slew "
    "16.4 V/µs so the "
    "output "
    "slews "
    "at the sheet's 10 "
    "V/µs "
    "into "
    "2 "
    "kΩ (the 1.28 kΩ output "
    "divides "
    "it).",
    "note": "The real output stage is nonlinear (22 mA short-circuit source current at 15 V); a "
    "fixed 1.28 kΩ is "
    "right "
    "near "
    "1 "
    "mA and pessimistic "
    "for "
    "heavy "
    "loads.",
    "fit": dict(
        aol_db=20 * math.log10(320e3),
        gbw=4e6,
        slew=16.4e6,
        phase_margin=65.6,
        rout=1280.0,  # slew: 10 V/µs at the 2 kΩ test load
        head_pos=0.035,
        head_neg=0.035,
        iq=9e-3 / 2,
    ),
    "ratings": {
        "vs_max": 16.0,
        "cm_neg_headroom": 0.0,
        "cm_pos_headroom": 5.0,
        "out_neg_headroom": 0.002,
        "out_pos_headroom": 1.7,
    },
    "rating_source": (
        f"{IS3260}: vs_max 16 V (V+ to V–); common-mode range 0 to 10 V min at V+ = 15 V; "
        "output headroom VOM+ 13.3 V typ and VOM– 0.002 V typ at RL = 10 kΩ (to the rails "
        "within 10 mV unloaded)"
    ),
    "pinout_source": f"{IS3260}, 8-lead PDIP pinout",
    "validation": [
        {
            "quantity": "aol_db",
            "conditions": {"supply": 7.5},
            "datasheet": {
                "min": 94.0,
                "typ": 110.0,
                "source": IS3260,
                "note": "AOL 50 kV/V min, 320 kV/V typ, V+ = 15 V, V– = 0, "
                "VO = 10 Vp-p, RL = 10 kΩ",
            },
        },
        {
            "quantity": "gbw",
            "conditions": {"supply": 7.5},
            "datasheet": {
                "typ": 4e6,
                "source": IS3260,
                "note": "Unity-gain crossover 4 MHz typ at ±7.5 V; 10 % overshoot as a follower "
                "(CL = 25 pF, RL = 2 kΩ): phase margin 65.6° fitted to it "
                "(.claude/skills/fit-model/tools/opamp_pm_fit.py). Reads low here: the 1.28 kΩ "
                "output "
                "drives the test's 10 kΩ load",
            },
        },
        {
            "quantity": "swing_pos",
            "conditions": {"supply": 7.5, "load": 1e9},
            "datasheet": {
                "min": 0.0,
                "max": 0.01,
                "source": f"{IS3260}: VOM+ 14.99 V min, 15 V typ, RL = ∞",
            },
        },
        {
            "quantity": "swing_neg",
            "conditions": {"supply": 7.5, "load": 1e9},
            "datasheet": {
                "min": 0.0,
                "max": 0.01,
                "source": f"{IS3260}: VOM– 0 V typ, 0.01 V max, RL = ∞",
            },
        },
        {
            "quantity": "swing_pos",
            "conditions": {"supply": 7.5, "load": 4360.0},
            "datasheet": {
                "typ": 1.7,
                "tol": 0.1,
                "source": f"{IS3260}: VOM+ 13.3 V typ, 11 V min, RL = 10 kΩ",
                "note": "The sheet's 10 kΩ goes to V– (1.33 mA at 13.3 V); here 4.36 kΩ to the "
                "midpoint draws the same current at the same output",
            },
        },
    ],
}

TI07X = "TI TL07xx data sheet SLOS080W (revised July 2025)"
TL07X_RATING = (
    f"{TI07X}: vs_max from 5.1 Absolute Maximum Ratings (36 V for NS/PS packages and M grades, "
    "42 V "
    "for others; the lower is used); common-mode headroom from 5.8 (TL07xC), VCM ±11 V min at "
    "±15 V; "
    "output headroom from 5.8, VOM ±13.5 V typ at RL = 10 kΩ (±12 V min)"
)
TL07X_SWING = f"{TI07X}, 5.8 (TL07xC): VOM ±13.5 V typ, ±12 V min, RL = 10 kΩ"


def tl07x(pid: str, kind: str, channels: int, package: dict | None) -> dict:
    """The TL07xC channel (one die for the 071, 072 and 074) from 5.8 and 5.9 of TI's sheet."""
    part = {
        "description": f"{pid} JFET-input {kind} op-amp, ±18 V max (our model from TI's sheet)",
        "sheet": f"{TI07X}, TL07xC at ±15 V",
        "manufacturer": "Texas Instruments",
        "url": "https://www.ti.com/lit/ds/symlink/tl072.pdf",
        "retrieved": "2026-11-04",
        "datasheet": "https://www.ti.com/lit/ds/symlink/tl071.pdf",
        "figure": "5.8 and 5.9 (TL07xC) at ±15 V: AOL 200 V/mV typ, GBW 3 MHz (the classic die: "
        "NS/PS packages and "
        "M "
        "grades; "
        "5.25 MHz on newer "
        "dies), "
        "slew "
        "rate 20 V/µs, phase "
        "margin "
        "56° "
        "(G = +1, RL 10 kΩ, "
        "CL "
        "20 "
        "pF), "
        "open-loop output "
        "impedance "
        "125 "
        "Ω, quiescent current "
        "1.4 "
        "mA "
        "per amplifier, VOM "
        "±13.5 "
        "V "
        "typ "
        "at 10 kΩ",
        "method": "Output resistance the sheet's 125 Ω, clamps 1.33 V from each rail so the 10 "
        "kΩ swing lands on "
        "the "
        "typical "
        "±13.5 V. Replaces "
        "TI's "
        "1989 "
        "macromodel, whose "
        "RP "
        "(2.143 "
        "kΩ "
        "across the supplies) "
        "drew "
        "12.6 "
        "mA a channel at 27 "
        "V "
        "against "
        "the sheet's 1.4 mA "
        "(D-219).",
        "fit": dict(
            aol_db=db(200),
            gbw=3e6,
            slew=20e6,
            phase_margin=56.0,
            rout=125.0,
            head_pos=1.33,
            head_neg=1.33,
            iq=1.4e-3,
        ),
        "ratings": {
            "vs_max": 36.0,
            "cm_neg_headroom": 4.0,
            "cm_pos_headroom": 4.0,
            "out_neg_headroom": 1.5,
            "out_pos_headroom": 1.5,
        },
        "rating_source": TL07X_RATING,
        "channels": channels,
        "validation": [
            {
                "quantity": "aol_db",
                "conditions": {"supply": 15.0},
                "datasheet": {
                    "min": db(25),
                    "typ": db(200),
                    "source": TI07X,
                    "note": "TL07xC AOL 25 V/mV min, 200 V/mV typ, ±15 V",
                },
            },
            {
                "quantity": "gbw",
                "conditions": {"supply": 15.0},
                "datasheet": {
                    "typ": 3e6,
                    "source": TI07X,
                    "note": "3 MHz for the classic die (NS/PS packages, M grade); newer dies "
                    "are 5.25 MHz; "
                    "phase margin 56° typ",
                },
            },
            {
                "quantity": "swing_pos",
                "conditions": {"supply": 15.0, "load": 10000.0},
                "datasheet": {"typ": 1.5, "max": 3.0, "source": TL07X_SWING},
            },
            {
                "quantity": "swing_neg",
                "conditions": {"supply": 15.0, "load": 10000.0},
                "datasheet": {"typ": 1.5, "max": 3.0, "source": TL07X_SWING},
            },
        ],
    }
    if package:
        part["package"] = package
    else:
        part["pinout_source"] = (
            f"{TI07X}, Figure 4-5 and Table 4-3, Pin Functions: TL072x (D, P, PS packages)"
        )
    return part


def _package(pid: str) -> dict:
    return json.loads((ROOT / f"{pid}.json").read_text())["package"]


PARTS["TL072"] = tl07x("TL072", "dual", 2, None)
PARTS["TL071"] = tl07x("TL071", "single", 1, _package("TL071"))
PARTS["TL074"] = tl07x("TL074", "quad", 4, _package("TL074"))


def build(pid: str) -> None:
    p = PARTS[pid]
    fit = fm.OpAmpFit(**p["fit"])
    head = [f"* {p['description']}", f"* Built by Solum Builder from {p['sheet']} (D-162)"]
    (ROOT / f"{pid}.lib").write_text("\n".join(head) + "\n" + fm.opamp_card(pid, fit))
    rec = {
        "id": pid,
        "type": "opamp",
        "description": p["description"],
        "spice_name": pid,
        "kind": "subckt",
        "pins": ["+", "-", "V+", "V-", "out"],
        "card": f"{pid}.lib",
        "manufacturer": p["manufacturer"],
        "source": {
            "url": p["url"],
            "retrieved": p["retrieved"],
            "licence": LICENCE,
            "original": "Solum Builder fit",
        },
        **({"datasheet": p["datasheet"]} if "datasheet" in p else {}),
        "fixes": [],
        "ratings": p["ratings"],
        "rating_sources": {k: p["rating_source"] for k in p["ratings"]},
        "channels": p.get("channels", 2),
        "package": p.get("package")
        or {"name": "8-pin DIP", "pins": DIP8, "source": p["pinout_source"]},
        "fit": {
            "sheet": p["sheet"],
            "figure": p["figure"],
            "points": [],
            "method": METHOD + " " + p["method"],
            "note": NOTE + (" " + p["note"] if p.get("note") else ""),
        },
        "validation": [
            {**v, "simulated": 0.0} for v in p["validation"]
        ],  # measured by add_model.py
    }
    (ROOT / f"{pid}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    print(pid, f"C1 {fit.c1:.4g} gm {fit.gm:.4g} R1 {fit.r1:.4g} p2 {fit.second_pole:.4g} Hz")


SPECS = [{"id": i, "type": "opamp", "update": True, "remeasure": True} for i in PARTS]

if __name__ == "__main__":
    for pid in sys.argv[1:]:
        build(pid)
