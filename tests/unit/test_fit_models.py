import dataclasses
import importlib.util
import math
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "fit_models.py"
_spec = importlib.util.spec_from_file_location("fit_models", SCRIPT)
assert _spec and _spec.loader
fit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fit)


def test_thermal_voltage_at_27_c() -> None:
    assert fit.thermal_voltage() == pytest.approx(0.025865, abs=1e-6)


def test_a_diode_fit_recovers_the_parameters_it_was_made_from() -> None:
    made = fit.DiodeFit(is_=2.52e-9, n=1.752, rs=0.568)  # the 1N4148 card's values
    points = [(made.volts(i), i) for i in (1e-5, 1e-4, 1e-3, 1e-2, 0.1)]
    got = fit.fit_diode(points)
    assert got.is_ == pytest.approx(2.52e-9, rel=1e-3)
    assert got.n == pytest.approx(1.752, rel=1e-4)
    assert got.rs == pytest.approx(0.568, rel=1e-3)


def test_a_fit_lands_on_points_it_wasnt_given() -> None:
    made = fit.DiodeFit(is_=1e-19, n=2.0, rs=10.0)  # an LED-like curve
    points = [(made.volts(i), i) for i in (1e-3, 4e-3, 16e-3)]
    got = fit.fit_diode(points)
    assert got.volts(8e-3) == pytest.approx(made.volts(8e-3), abs=1e-4)


def test_no_visible_series_resistance_fits_the_exponential_alone() -> None:
    made = fit.DiodeFit(is_=1e-9, n=1.5, rs=0.0)
    points = [(made.volts(i), i) for i in (1e-5, 1e-4, 1e-3)]
    got = fit.fit_diode(points)
    assert got.rs >= 0.0 and got.n == pytest.approx(1.5, rel=1e-3)


def test_n_never_goes_below_one() -> None:
    # nearly straight: series resistance dominating, as on a linear-scale plot
    points = [(0.60 + 15.0 * i, i) for i in (1e-3, 4e-3, 8e-3, 12e-3, 16e-3)]
    got = fit.fit_diode(points)
    assert got.n == pytest.approx(1.0)
    assert got.rs > 0.0


def test_is_stays_above_ngspices_floor() -> None:
    made = fit.DiodeFit(is_=1e-26, n=1.3, rs=12.0)  # GaP-like: a tiny IS
    points = [(made.volts(i) + 0.15, i) for i in (1e-3, 4e-3, 8e-3, 16e-3)]  # 150 mV higher
    got = fit.fit_diode(points)
    assert got.is_ == fit.IS_MIN
    assert got.volts(8e-3) == pytest.approx(made.volts(8e-3) + 0.15, abs=2e-3)


def test_is_max_caps_the_reverse_current() -> None:
    made = fit.DiodeFit(is_=1e-4, n=5.0, rs=20.0)  # a soft germanium curve: leaky
    points = [(made.volts(i), i) for i in (1e-3, 4e-3, 10e-3, 25e-3)]
    assert fit.fit_diode(points).is_ > 5e-5  # uncapped, it leaks
    capped = fit.fit_diode(points, is_max=1e-5)
    assert capped.is_ == 1e-5
    assert capped.volts(4e-3) == pytest.approx(made.volts(4e-3), abs=0.05)


@pytest.mark.parametrize(
    "points", [[(0.6, 1e-3), (0.7, 1e-2)], [(0.6, 0.0), (0.7, 1e-2), (0.8, 0.1)]]
)
def test_too_few_or_zero_current_points_are_refused(points: list[tuple[float, float]]) -> None:
    with pytest.raises(ValueError):
        fit.fit_diode(points)


def test_a_falling_curve_is_refused() -> None:
    with pytest.raises(ValueError, match="rise"):
        fit.fit_diode([(0.8, 1e-3), (0.7, 1e-2), (0.6, 0.1)])


def test_the_card_carries_the_fit_and_extras() -> None:
    card = fit.diode_card("LEDG", fit.DiodeFit(is_=1e-19, n=2.0, rs=10.0), cjo=15e-12, bv=5.0)
    assert card == ".model LEDG D(is=1e-19 n=2 rs=10 cjo=1.5e-11 bv=5)\n"


def test_amps_inverts_volts() -> None:
    made = fit.DiodeFit(is_=2.52e-9, n=1.752, rs=0.568)
    assert made.amps(made.volts(3e-3)) == pytest.approx(3e-3, rel=1e-6)


def test_a_pair_recovers_two_diodes_in_parallel() -> None:
    made = fit.DiodePair(
        low=fit.DiodeFit(is_=1e-8, n=1.05, rs=80.0), high=fit.DiodeFit(is_=5e-10, n=1.7, rs=0.7)
    )
    points = [(made.volts(i), i) for i in (1e-6, 1e-5, 1e-4, 1e-3, 3e-3, 2e-2, 5e-2, 0.1, 0.2)]
    got = fit.fit_diode_pair(points, split=3e-3)
    for i in (5e-4, 1e-2, 0.15):  # points it wasn't given
        assert got.volts(i) == pytest.approx(made.volts(i), abs=0.01)


def test_a_pair_needs_points_above_the_split() -> None:
    made = fit.DiodeFit(is_=1e-9, n=1.5, rs=1.0)
    points = [(made.volts(i), i) for i in (1e-5, 1e-4, 1e-3, 1e-2)]
    with pytest.raises(ValueError, match="above the split"):
        fit.fit_diode_pair(points, split=5e-3)


def test_the_pair_card_is_a_two_pin_subcircuit() -> None:
    pair = fit.DiodePair(low=fit.DiodeFit(1e-8, 1.0, 80.0), high=fit.DiodeFit(5e-10, 1.7, 0.7))
    card = fit.diode_pair_card("BAT41", pair, cjo=2e-12)
    assert card.splitlines()[0] == ".subckt BAT41 1 2"
    assert "D1 1 2 BAT41_low" in card and "D2 1 2 BAT41_high" in card
    assert ".model BAT41_low D(is=1e-08 n=1 rs=80 cjo=2e-12)" in card
    assert card.endswith(".ends\n")


def test_middle_is_geometric_and_keeps_the_sign() -> None:
    assert fit.middle(0.2e-3, 1e-3) == pytest.approx(0.4472e-3, rel=1e-4)
    assert fit.middle(-0.3, -1.5) == pytest.approx(-0.6708, rel=1e-4)
    with pytest.raises(ValueError):
        fit.middle(-1.0, 1.0)


def test_cut_off_from_a_gate_voltage_at_a_current() -> None:
    # 2N5457: VGS -2.5 V at 100 µA, Idss 3 mA → Vp = -2.5 / (1 - √(0.1/3)) = -3.058 V
    assert fit.jfet_vp(-2.5, 100e-6, 3e-3) == pytest.approx(-3.0585, rel=1e-4)
    with pytest.raises(ValueError):
        fit.jfet_vp(-2.5, 4e-3, 3e-3)


def test_a_jfet_card_has_beta_from_idss_and_vp() -> None:
    j = fit.JfetFit(idss=3e-3, vp=-3.0, lam=3.3e-3, cgd=1.5e-12)
    assert j.beta == pytest.approx(3.333e-4, rel=1e-3)  # Idss / Vp²
    assert fit.jfet_card("J2N5457", j) == (
        ".model J2N5457 NJF(vto=-3 beta=0.0003333 lambda=0.0033 cgd=1.5e-12)\n"
    )


def test_an_op_amps_inner_values_follow_its_figures() -> None:
    a = fit.OpAmpFit(aol_db=106.0, gbw=0.73e6, slew=0.55e6, phase_margin=57.0, rout=200.0,
                     head_pos=0.04, head_neg=0.0, iq=212e-6)  # fmt: skip
    assert a.c1 == pytest.approx(10e-6 / 0.55e6)  # slew = Imax / C1
    # GBW = gm / 2πC1, raised so the second pole leaves the crossing at 0.73 MHz
    assert a.gm / (2 * math.pi * a.c1) == pytest.approx(0.73e6 / math.cos(math.radians(33)))
    assert a.gm * a.r1 == pytest.approx(10 ** (106 / 20))  # Aol = gm R1
    assert a.second_pole == pytest.approx(0.73e6 / math.tan(math.radians(33)))
    card = fit.opamp_card("TLC2262", a)
    assert card.startswith(".subckt TLC2262 1 2 3 4 5\n") and card.endswith(".ends\n")
    assert "Iq 3 4 DC 0.000212" in card and "Rout o2 5 200" in card


def test_least_squares_solves_within_its_bounds() -> None:
    line = [(x, 2.0 * x + 1.0) for x in range(5)]

    def residuals(p: object) -> list[float]:
        a, b = p  # type: ignore[misc]
        return [a * x + b - y for x, y in line]

    assert fit.least_squares(residuals, [0.0, 0.0], [-5, -5], [5, 5]) == pytest.approx([2, 1])
    assert fit.least_squares(residuals, [0.0, 0.0], [-5, -5], [1.5, 5])[0] == pytest.approx(1.5)


IDEAL = dict(is_=1e-14, nf=1.0, bf=200.0, ise=0.0, ne=1.5, ikf=1e6, vaf=1e9)


def test_an_ideal_transistors_gain_is_bf_and_vbe_its_diode_law() -> None:
    q = fit.GummelPoon(**IDEAL)
    vbe, hfe = q.forward(1e-3, 5.0)
    assert hfe == pytest.approx(200.0, rel=1e-4)
    assert vbe == pytest.approx(fit.thermal_voltage() * math.log(1e-3 / 1e-14), abs=1e-5)


def test_vce_sat_follows_ebers_moll() -> None:
    """With no knee, Early effect or resistances: VCE(sat) = Vt·ln[(1/aR + b/BR)/(1 - b/BF)]
    for a forced beta b, aR = BR/(1 + BR)."""
    q = fit.GummelPoon(**{**IDEAL, "br": 2.0})
    a_r, forced = 2.0 / 3.0, 10.0
    expected = fit.thermal_voltage() * math.log((1 / a_r + forced / 2.0) / (1 - forced / 200.0))
    assert q.vce_sat(1e-3, 1e-4) == pytest.approx(expected, abs=1e-5)


def test_a_bjt_fit_recovers_the_transistor_it_was_made_from() -> None:
    made = fit.GummelPoon(is_=6e-15, nf=1.02, bf=230.0, ise=2e-14, ne=1.6, ikf=0.15, vaf=100.0,
                          re=0.5)  # fmt: skip
    ics = [1e-5, 1e-4, 1e-3, 1e-2, 5e-2, 0.1]
    got = fit.fit_bjt_forward([(i, made.forward(i, 5.0)[1]) for i in ics],
                              [(i, made.forward(i, 5.0)[0]) for i in ics], 5.0, 100.0)  # fmt: skip
    for i in (3e-5, 3e-3, 0.07):  # currents it wasn't given
        assert got.forward(i, 5.0)[1] == pytest.approx(made.forward(i, 5.0)[1], rel=0.01)
        assert got.forward(i, 5.0)[0] == pytest.approx(made.forward(i, 5.0)[0], abs=1e-3)


def test_rb_adds_its_base_current_drop_to_vbe() -> None:
    plain = fit.GummelPoon(**IDEAL)
    vbe, hfe = fit.GummelPoon(**{**IDEAL, "rb": 25.0}).forward(1e-2, 5.0)
    assert hfe == pytest.approx(plain.forward(1e-2, 5.0)[1])
    assert vbe - plain.forward(1e-2, 5.0)[0] == pytest.approx(25.0 * 1e-2 / 200.0, rel=1e-3)


def test_icbo_follows_ebers_moll() -> None:
    """Emitter open, collector far reversed: ICBO = IS·(1 - aF·aR)/aR."""
    q = fit.GummelPoon(**{**IDEAL, "br": 2.0})
    a_f, a_r = 200.0 / 201.0, 2.0 / 3.0
    assert q.icbo(10.0) == pytest.approx(1e-14 * (1 - a_f * a_r) / a_r, rel=1e-3)


def test_a_germanium_cards_gain_is_found_below_where_its_current_turns_over() -> None:
    """At a fixed VCE the model's IC rises with VBE, then falls past ~0.6 V (the reverse
    term outgrows the knee-limited forward one); the solver must find the first crossing."""
    ge = fit.GummelPoon(is_=1e-6, nf=1.05, bf=100.0, ise=1e-6, ne=1.6, ikf=0.05, vaf=math.inf,
                        re=0.5, rc=0.5, br=5.0, isc=1e-7, nc=1.5, nr=1.05)  # fmt: skip
    assert ge.currents(1.0, 1.0 - 0.144)[0] < 0  # past the turn
    vbe, hfe = ge.forward(12e-3, 0.15)
    assert 0.2 < vbe < 0.4
    assert 1 < hfe < 100


def test_iebo_follows_ebers_moll() -> None:
    """Collector open, emitter far reversed: IEBO = IS·(1 - aF·aR)/aF."""
    q = fit.GummelPoon(**{**IDEAL, "br": 2.0})
    a_f, a_r = 200.0 / 201.0, 2.0 / 3.0
    assert q.iebo(5.0) == pytest.approx(1e-14 * (1 - a_f * a_r) / a_f, rel=1e-3)


def test_vbe_sat_follows_ebers_moll() -> None:
    """With no knee, Early effect or resistances, ib in and ic out:
    exp(VBE/Vt) = (IC + (1 + BR)·IB) / (IS·(1 + (1 + BR)/BF))."""
    q = fit.GummelPoon(**{**IDEAL, "br": 2.0})
    ic, ib = 1e-3, 1e-4
    expected = fit.thermal_voltage() * math.log((ic + 3.0 * ib) / (1e-14 * (1 + 3.0 / 200.0)))
    vbe, vce = q.saturated(ic, ib)
    assert vbe == pytest.approx(expected, abs=1e-5)
    assert vce == pytest.approx(q.vce_sat(ic, ib))


def test_vbe_sat_adds_the_base_and_emitter_drops() -> None:
    plain = fit.GummelPoon(**{**IDEAL, "br": 2.0})
    both = fit.GummelPoon(**{**IDEAL, "br": 2.0, "rb": 50.0, "re": 2.0})
    ic, ib = 1e-2, 1e-3
    extra = 50.0 * ib + 2.0 * (ic + ib)
    assert both.saturated(ic, ib)[0] - plain.saturated(ic, ib)[0] == pytest.approx(extra, rel=1e-3)


def test_a_germanium_fit_recovers_its_transistor() -> None:
    """IS in microamps, past silicon's bound: `is_max` lets the fit reach it (D-170)."""
    made = fit.GummelPoon(is_=1.5e-5, nf=1.05, bf=95.0, ise=4e-7, ne=1.8, ikf=0.6, vaf=30.0,
                          re=0.2, rb=25.0, br=8.0, nr=1.05)  # fmt: skip
    ics = [5e-4, 1e-3, 3e-3, 1e-2, 3e-2, 0.1, 0.3]
    got = fit.fit_bjt_forward([(i, made.forward(i, 1.0)[1]) for i in ics],
                              [(i, made.forward(i, 1.0)[0]) for i in ics], 1.0, 30.0, rb=25.0,
                              is_max=1e-3, icbo=(made.icbo(10.0), 10.0))  # fmt: skip
    for i in (2e-3, 5e-2):
        assert got.forward(i, 1.0)[1] == pytest.approx(made.forward(i, 1.0)[1], rel=0.01)
        assert got.forward(i, 1.0)[0] == pytest.approx(made.forward(i, 1.0)[0], abs=1e-3)
    assert got.icbo(10.0) == pytest.approx(made.icbo(10.0), rel=0.01)
    assert got.nr == got.nf


def test_a_saturation_fit_lands_on_the_curve() -> None:
    made = fit.GummelPoon(**{**IDEAL, "ikf": 0.2, "br": 4.0, "isc": 1e-12, "nc": 1.6, "rc": 1.0})
    points = [(i, made.vce_sat(i, i / 10)) for i in (1e-4, 1e-3, 1e-2, 0.1)]
    got = fit.fit_bjt_saturation(fit.GummelPoon(**{**IDEAL, "ikf": 0.2}), points, 10.0)
    assert got.vce_sat(3e-3, 3e-4) == pytest.approx(made.vce_sat(3e-3, 3e-4), abs=2e-3)
    assert got.nr == 1.0  # NR follows NF


def test_a_saturation_fit_can_cap_the_leakage() -> None:
    """D-187: the 2SC1815's VCE(sat) curve is met about as well with ISC at its 1e-8 A
    bound (10 nA of leakage, so a floating base still passes 1.4 µA) as with 3 pA; the
    cap takes the small one, and the curve is still met. Its forward fit and the points
    it was given, from Toshiba's sheet (IC/IB = 10; hFE at VCE 6 V)."""
    start = fit.GummelPoon(is_=1.064e-13, nf=1.021, bf=152.7, ise=3.655e-14, ne=1.42, ikf=1.098,
                           vaf=math.inf, nkf=1.0, rb=50.0)  # fmt: skip
    points = [(2e-4, 0.0399), (5e-4, 0.0386), (1e-3, 0.0382), (2e-3, 0.0375), (5e-3, 0.0382),
              (1e-2, 0.0404), (2e-2, 0.0505), (5e-2, 0.0782), (0.1, 0.1192)]  # fmt: skip
    gain = [(2e-4, 139.2), (2e-3, 139.2), (2e-2, 139.2), (5e-2, 139.2), (0.1, 133.9)]
    free = fit.fit_bjt_saturation(start, points, 10.0, gain, 6.0)
    assert free.isc == pytest.approx(1e-8, rel=1e-3)  # at the bound
    capped = fit.fit_bjt_saturation(start, points, 10.0, gain, 6.0, isc_max=1e-10)
    assert capped.icbo(9.0) < 1e-9
    assert max(abs(capped.vce_sat(i, i / 10) - v) for i, v in points) < 2.2e-3


def test_the_direct_saturation_solve_agrees_with_the_nested_search() -> None:
    """D-274: Newton on both junctions lands where the nested search does, and the
    answer carries the currents asked for. The 2SC1815's fitted card (D-187), across
    its VCE(sat) curve."""
    q = fit.GummelPoon(is_=1.064e-13, nf=1.021, bf=152.7, ise=3.655e-14, ne=1.42, ikf=1.098,
                       vaf=math.inf, nkf=1.0, br=4.0, isc=3e-12, nc=1.3, rc=0.6,
                       nr=1.021)  # fmt: skip
    for ic in (2e-4, 1e-3, 1e-2, 0.1):
        direct = q._junctions(ic, ic / 10)
        assert direct is not None
        assert direct == pytest.approx(q._junctions_nested(ic, ic / 10), abs=1e-9)
        assert q.currents(*direct) == pytest.approx((ic, ic / 10), rel=1e-9)
    assert q._junctions(0.0, 1e-4) is None  # nothing drawn: left to the nested search


def test_a_root_is_found_to_a_picovolt_and_the_ends_when_there_is_none() -> None:
    assert fit._bisect(lambda v: math.exp(v / 0.026), math.exp(0.6 / 0.026), 0.0, 1.5) == (
        pytest.approx(0.6, abs=1e-12)
    )
    assert fit._bisect(lambda v: v, 2.0, 0.0, 1.5) == 1.5  # never reaches it
    assert fit._bisect(lambda v: v, -1.0, 0.0, 1.5) == 0.0  # always past it
    # the first crossing of an f that turns over (3 again at 0.7), found in steps
    assert fit._bisect(lambda v: 16 * v * (1 - v), 3.0, 0.0, 1.5, 0.05) == pytest.approx(0.25)


def test_a_junction_capacitance_fit_recovers_its_law() -> None:
    points = [(v, 4e-12 / (1 + v / 0.7) ** 0.4) for v in (0.1, 0.5, 1, 3, 10, 30)]
    cj, vj, m = fit.fit_junction_cap(points)
    assert (cj, vj, m) == pytest.approx((4e-12, 0.7, 0.4), rel=1e-3)


def test_tf_is_the_transit_time_left_after_the_junctions_charge() -> None:
    q = fit.GummelPoon(**IDEAL)
    assert fit.bjt_tf(q, 300e6, 1e-2, 5.0) == pytest.approx(1 / (2 * math.pi * 300e6))
    with_caps = fit.GummelPoon(**{**IDEAL, "cje": 5e-12, "cjc": 0.0})  # 2·CJE·Vt/IC = 26 ps
    assert fit.bjt_tf(q, 300e6, 1e-2, 5.0) - fit.bjt_tf(with_caps, 300e6, 1e-2, 5.0) == (
        pytest.approx(2 * 5e-12 * fit.thermal_voltage() / 1e-2)
    )


def test_a_bjt_card_names_its_polarity_and_leaves_zeros_out() -> None:
    card = fit.bjt_card("Q2N3906", fit.GummelPoon(**{**IDEAL, "ise": 1e-15}), "PNP")
    assert card == (".model Q2N3906 PNP(is=1e-14 nf=1 bf=200 ise=1e-15 ne=1.5 ikf=1e+06 "
                    "vaf=1e+09 br=1 vje=0.75 mje=0.33 vjc=0.75 mjc=0.33)\n")  # fmt: skip
    germanium = fit.bjt_card("AC128", fit.GummelPoon(**{**IDEAL, "rb": 25.0}), "PNP", eg=0.67)
    assert germanium.endswith("mjc=0.33 rb=25 eg=0.67)\n")


def test_a_saturation_fit_keeps_the_gain_curve_it_is_given() -> None:
    """A flat VCE(sat) curve can be met by a large ISC, whose leakage then swamps a
    high-gain part's base current at low IC (the 2N5088's fit: hFE 450 → 631 at 10 µA)."""
    start = fit.GummelPoon(**{**IDEAL, "bf": 600.0, "ikf": 0.03})
    leaky = dataclasses.replace(start, br=20.0, isc=5e-9, nc=3.5, rc=1.4)
    points = [(i, leaky.vce_sat(i, i / 10)) for i in (1e-4, 1e-3, 1e-2, 5e-2)]
    gain = [(i, start.forward(i, 5.0)[1]) for i in (1e-5, 1e-4, 1e-3)]
    got = fit.fit_bjt_saturation(start, points, 10.0, gain, 5.0)
    for i, h in gain:
        assert got.forward(i, 5.0)[1] == pytest.approx(h, rel=0.02)


def test_collector_resistance_doesnt_upset_the_gain_at_high_current() -> None:
    """Out of saturation RC only lowers the inner VCE, which a part with no Early effect
    ignores (the 2N5088's fit read hFE -1 at 50 mA: the drops' iteration ran away)."""
    plain = fit.GummelPoon(is_=6.9e-14, nf=1.048, bf=1232.0, ise=6.6e-16, ne=1.167, ikf=0.027,
                           vaf=math.inf)  # fmt: skip
    with_rc = dataclasses.replace(plain, rc=1.418, re=0.5)
    for ic in (1e-3, 5e-2, 0.1):
        assert with_rc.forward(ic, 5.0)[1] == pytest.approx(plain.forward(ic, 5.0)[1], rel=1e-3)


def test_a_bjt_fit_finds_a_steeper_knee() -> None:
    """NKF (ngspice's high-current roll-off exponent, 0.5 by default) shapes the knee:
    the 2N5088's sheet falls faster past 20 mA than NKF 0.5 allows."""
    made = fit.GummelPoon(is_=7e-14, nf=1.05, bf=1600.0, ise=5e-16, ne=1.17, ikf=0.05, vaf=math.inf,
                          nkf=0.7)  # fmt: skip
    ics = [1e-5, 1e-4, 1e-3, 1e-2, 2e-2, 5e-2]
    hfe = [(i, made.forward(i, 5.0)[1]) for i in ics]
    got = fit.fit_bjt_forward(hfe, [(i, made.forward(i, 5.0)[0]) for i in ics], 5.0, math.inf)
    assert got.nkf == pytest.approx(0.7, abs=0.02)
    assert got.forward(3e-2, 5.0)[1] == pytest.approx(made.forward(3e-2, 5.0)[1], rel=0.01)


def test_a_bjt_card_writes_nkf_only_when_it_isnt_the_default() -> None:
    assert "nkf" not in fit.bjt_card("Q", fit.GummelPoon(**IDEAL))
    assert " nkf=0.7" in fit.bjt_card("Q", fit.GummelPoon(**IDEAL, nkf=0.7))


def test_a_leakage_term_fitted_to_its_floor_is_left_out() -> None:
    """A flat gain curve needs no ISE: one pinned at the bound would print `ise=1e-20 ne=4`."""
    made = fit.GummelPoon(**{**IDEAL, "ikf": 0.2})
    ics = [1e-5, 1e-4, 1e-3, 1e-2, 0.1]
    got = fit.fit_bjt_forward([(i, made.forward(i, 5.0)[1]) for i in ics],
                              [(i, made.forward(i, 5.0)[0]) for i in ics], 5.0, 1e9)  # fmt: skip
    assert got.ise == 0.0
    card = fit.bjt_card("Q", got)
    assert " ise=" not in card and " ne=" not in card


def test_a_saturation_fit_sets_nr_to_nf() -> None:
    """The onsemi BC546-550 curves give NF 1.23: with NR held at 1 the collector junction
    is the steeper one, and VCE(sat) sits ~0.12 V high whatever BR, ISC and RC do."""
    start = fit.GummelPoon(**{**IDEAL, "nf": 1.23, "ikf": 0.2})
    made = dataclasses.replace(start, nr=1.23, br=10.0, rc=1.0)
    points = [(i, made.vce_sat(i, i / 10)) for i in (1e-4, 1e-3, 1e-2, 5e-2)]
    got = fit.fit_bjt_saturation(start, points, 10.0)
    assert got.nr == 1.23
    assert got.vce_sat(3e-3, 3e-4) == pytest.approx(made.vce_sat(3e-3, 3e-4), abs=1e-3)
    assert " nr=1.23" in fit.bjt_card("Q", made) and " nr=" not in fit.bjt_card("Q", start)


def test_one_capacitance_point_sets_cj0_with_the_default_grading() -> None:
    """A sheet giving only Cib = 9 pF at 0.5 V can't pin VJ and M: keep ngspice's."""
    cj, vj, m = fit.fit_junction_cap([(0.5, 9e-12)])
    assert (vj, m) == (0.75, 0.33)
    assert cj / (1 + 0.5 / 0.75) ** 0.33 == pytest.approx(9e-12)
