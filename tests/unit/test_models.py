"""Model library: card parsing, the importer's D-029 fixes, layered loading."""

import json
import shutil
from pathlib import Path

import pytest

from solum.models import (
    Model,
    ModelError,
    clean_card,
    load_models,
    logical_lines,
    model_cards_text,
    parse_model_cards,
)

LIBRARY = Path(__file__).parents[2] / "library" / "models"


def test_continuation_lines_are_joined() -> None:
    assert logical_lines(".model X D(is=1n\n+ n=2)\n* c") == [".model X D(is=1n n=2)", "* c"]


def test_parse_model_cards_skips_subckt_internals() -> None:
    text = """.model DX D(Is=1n N=1.9)
.SUBCKT Y 1 2
.model DX2 D(IS=2n)
.ENDS
.MODEL J1 NJF (VTO=-0.90 BETA=7.00E-04
+ LAMBDA=.035)
.MODEL MD2 D XTI=1.0P"""
    cards = parse_model_cards(text)
    assert [(c.name, c.type) for c in cards] == [("DX", "D"), ("J1", "NJF"), ("MD2", "D")]
    assert cards[1].params == {"vto": "-0.90", "beta": "7.00E-04", "lambda": ".035"}
    assert cards[2].params == {"xti": "1.0P"}


def test_clean_card_moves_ltspice_bjt_params_to_metadata() -> None:
    """D-029: Vceo/Icrating/mfg are fatal in ngspice; they feed the rating rules."""
    out = clean_card(".model 2N5089 NPN(Is=5.911f Bf=1.434K Vceo=25 Icrating=100m mfg=Fairchild)")
    assert out.text == ".model 2N5089 NPN(is=5.911f bf=1.434K)\n"
    assert out.manufacturer == "Fairchild"
    assert out.ratings == {"vceo": 25.0, "ic": pytest.approx(0.1)}


def test_clean_card_strips_unsupported_jfet_params() -> None:
    out = clean_card(
        ".MODEL J2N5457 NJF(Beta=1.125m Vto=-1.372 Isr=1.747p Nr=2 Alpha=2.543u Vk=152.2)"
    )
    assert out.text == ".model J2N5457 NJF(beta=1.125m vto=-1.372)\n"
    assert out.fixes == ["dropped isr, nr, alpha, vk (not supported by ngspice's JFET)"]


def test_clean_card_drops_star_hash_and_ltspice_diode_labels() -> None:
    out = clean_card("*#\n.model 1N4148 D(Is=2.52n Iave=200m Vpk=75 mfg=OnSemi type=silicon)")
    assert out.text == ".model 1N4148 D(is=2.52n)\n"
    assert out.ratings == {"if_avg": pytest.approx(0.2), "vr_max": 75.0}
    assert out.fixes[0].startswith("dropped a '*#' line")


def test_clean_card_keeps_subcircuits_and_wraps_long_cards() -> None:
    sub = ".SUBCKT X 1 2\nR1 1 2 1k\n.ENDS"
    assert clean_card(sub).text == sub + "\n"
    long = ".model Q NPN(" + " ".join(f"p{i}=1" for i in range(40)) + ")"
    text = clean_card(long).text
    assert all(len(line) <= 90 for line in text.splitlines())
    assert parse_model_cards(text)[0].params == parse_model_cards(long)[0].params


def test_core_library_loads_and_every_card_matches_its_record() -> None:
    lib = load_models([LIBRARY])
    assert {"1N4148", "2N5089", "J201", "2N5457", "TL072", "RC4558", "LM308"} <= set(lib.ids())
    for model_id in lib.ids():
        model = lib.get(model_id)
        if model.info.kind == "model":
            assert model.statement is not None
        elif model.info.kind == "behavioural":  # a charge pump: datasheet values, cited
            assert not model.card and model.info.params
            assert set(model.info.params) <= set(model.info.param_sources)
            assert set(model.info.ratings) <= set(model.info.rating_sources)
        else:
            assert f".subckt {model.info.spice_name.lower()}" in model.card.lower()
            assert model.info.pins
        assert model.info.source.url and model.info.source.licence
        assert model.info.validation, f"{model_id} has no validation record"


def test_polarity_and_params() -> None:
    lib = load_models([LIBRARY])
    assert lib.get("J201").polarity == "n"
    assert lib.get("AC128").polarity == "p"
    assert lib.get("TL072").polarity is None
    n7000 = lib.get("2N7000")
    assert n7000.polarity == "n"  # VDMOS without pchan (D-175)
    pchan = Model(n7000.info, n7000.card.replace("VDMOS(", "VDMOS(pchan "))
    assert pchan.polarity == "p"
    assert lib.get("J201").param("VTO") == pytest.approx(-0.6708)
    assert lib.get("J201").param("nope") is None


def test_a_zener_is_a_diode_whose_record_checks_its_zener_voltage() -> None:
    """Z refs and the zener symbol follow the record: a `vz` check makes it a zener."""
    lib = load_models([LIBRARY])
    assert lib.get("1N4742A").zener
    assert not lib.get("1N4148").zener  # a `vf` check only
    assert not lib.get("TL072").zener


def test_ids_by_type() -> None:
    assert load_models([LIBRARY]).ids("jfet") == [
        "2N5457",
        "2N5458",
        "2N5485",
        "2SK184-GR",
        "2SK209-GR",
        "J113",
        "J201",
        "MPF102",
        "MPF4393",
        "PF5102",
    ]


def test_a_jfets_idss_and_vp_from_its_card() -> None:
    """J201: VTO -0.6708 V, BETA 0.9938 mA/V² → Idss = 0.9938m * 0.45 = 0.4472 mA."""
    lib = load_models([LIBRARY])
    spec = lib.get("J201").jfet_spec()
    assert spec is not None
    assert spec["vp"] == pytest.approx(-0.6708)
    assert spec["idss"] == pytest.approx(0.4472e-3, rel=1e-3)
    assert lib.get(lib.ids("diode")[0]).jfet_spec() is None


def test_a_transistors_gain_from_its_card() -> None:
    """D-130, D-153: its gain on the Geofex tester as recorded (`tester_hfe`), else its BF
    as written (`bf=1.434K`); none for a JFET or an op-amp."""
    lib = load_models([LIBRARY])
    assert lib.get("AC128").bjt_spec() == {
        "hfe": pytest.approx(91.47, abs=0.01), "leakage": pytest.approx(315.2e-6, rel=1e-3),
        "germanium": True,  # below Valvo's curve, which starts at 1 mA:
        "tester_ic": pytest.approx(91.47 * 9.0 / 2.2e6 + 315.2e-6, rel=1e-3), "sheet_low_ic": 1e-3,
    }  # fmt: skip
    card = ".model 2N5089 NPN(is=5.911f bf=1.434K ikf=15.4m)\n"  # the old LTspice card's style
    info = lib.get("2N5089").info.model_copy(update={"validation": []})
    assert Model(info, card).bjt_spec() == {
        "hfe": pytest.approx(1434.0), "leakage": 0.0, "germanium": False
    }  # fmt: skip
    assert lib.get("J201").bjt_spec() is None and lib.get("TL072").bjt_spec() is None


def test_an_estimated_card_says_so() -> None:
    """D-186: the OC81D has no sheet with curves; its card is the OC75's scaled to the
    cross-reference table, and its spec says so (the form's hint); a fitted card's doesn't."""
    lib = load_models([LIBRARY])
    assert (lib.get("OC81D").bjt_spec() or {})["estimated"] is True
    assert "estimated" not in (lib.get("OC75").bjt_spec() or {})


def test_a_tester_gain_below_the_sheets_curve_says_so() -> None:
    """9b: the tester feeds the base about 9 V / 2.2 MΩ = 4.09 µA. The MPSA06's 83.75 puts
    its collector near 0.343 mA, under the 0.52 mA where its sheet's gain curve starts, so
    the form says the figure is the card's extrapolation. The 2N3904's 0.96 mA is inside its
    curve (from 0.1 mA)."""
    lib = load_models([LIBRARY])
    spec = lib.get("MPSA06").bjt_spec()
    assert spec is not None
    assert spec["tester_ic"] == pytest.approx(83.75 * 9.0 / 2.2e6, rel=1e-3)
    assert spec["sheet_low_ic"] == pytest.approx(0.52e-3)
    assert "sheet_low_ic" not in (lib.get("2N3904").bjt_spec() or {})


def test_a_germaniums_tester_current_counts_its_leakage() -> None:
    """9c: Mullard's transfer curves give the whole collector current, leakage included,
    so the tester's is compared the same way: gain times 4.09 µA + leakage. The OC44 (94.6,
    32.7 µA: 0.42 mA) sits under its curve's 0.71 mA; the OC71 (60.1, 200 µA: 0.45 mA)
    and the OC75 (86.2, 370 µA: 0.72 mA) are inside theirs."""
    lib = load_models([LIBRARY])
    spec = lib.get("OC44").bjt_spec() or {}
    assert spec["tester_ic"] == pytest.approx(94.58 * 9.0 / 2.2e6 + 32.70e-6, rel=1e-3)
    assert spec["sheet_low_ic"] == pytest.approx(0.7082e-3)
    assert "sheet_low_ic" not in (lib.get("OC71").bjt_spec() or {})
    assert "sheet_low_ic" not in (lib.get("OC75").bjt_spec() or {})


def test_every_bjt_fit_lists_gain_against_collector_current() -> None:
    """9c: one shape for a BJT record's fit points, (IC in amps, DC gain), as
    `_below_sheet` reads them. A sheet's transfer curve (IB, IC) is kept whole under
    `curves["transfer"]`, and its points become (IC, IC / IB)."""
    lib = load_models([LIBRARY])
    for i in lib.ids("bjt"):
        fit = lib.get(i).info.fit
        if fit is None:
            continue
        for ic, gain in fit.points:
            assert 1e-7 < ic < 10.0, (i, ic)
            assert 1.0 < gain < 5000.0, (i, gain)
        for ib, ic in fit.curves.get("transfer", []):
            assert abs(ib) < 1e-2 and 0 < ic < 10.0, (i, ib, ic)
    oc71 = lib.get("OC71").info.fit
    assert oc71 is not None
    assert oc71.curves["transfer"][0] == pytest.approx((0.296e-6, 0.1858e-3), rel=1e-2)
    assert oc71.points[0] == pytest.approx((0.1858e-3, 0.1858e-3 / 0.296e-6), rel=1e-2)


def test_every_bjt_card_records_its_tester_gain() -> None:
    """D-153: where a measured transistor's form starts, and what the fit scales from."""
    lib = load_models([LIBRARY])
    missing = [
        i for i in lib.ids("bjt") if lib.get(i).bjt_spec() is not None
        and not any(v.quantity == "tester_hfe" for v in lib.get(i).info.validation)
    ]  # fmt: skip
    assert not missing


def test_every_germanium_model_records_its_leakage() -> None:
    """D-138: the form shows a germanium part's leakage, and the netlist makes up a measured
    one from the model's own, so a germanium card (EG 0.67 eV) must carry its simulated
    Iceo (`iceo`, re-measured by tests/sim/test_models.py). The library has some."""
    lib = load_models([LIBRARY])
    germanium = [i for i in lib.ids("bjt") if (lib.get(i).bjt_spec() or {}).get("germanium")]
    assert germanium
    missing = [
        i for i in germanium if not any(v.quantity == "iceo" for v in lib.get(i).info.validation)
    ]
    assert not missing, f"germanium models without a simulated leakage (iceo): {missing}"


def test_a_datasheet_range_is_the_first_record_with_both_limits() -> None:
    """2N3904's hFE: 100-300 at 10 mA (the 1 mA record has a minimum only); the AC128's
    at VCB = 0, as Valvo states it (D-170); none for a quantity with no record."""
    lib = load_models([LIBRARY])
    assert lib.get("2N3904").datasheet_range("hfe") == {
        "min": 100.0, "max": 300.0, "at": {"ic": 0.01, "vce": 1.0}
    }  # fmt: skip
    assert lib.get("AC128").datasheet_range("hfe") == {
        "min": 55.0, "max": 175.0, "at": {"ic": 0.05, "vcb": 0.0}
    }  # fmt: skip
    assert lib.get("2N3904").datasheet_range("idss") is None


def test_unknown_model_says_how_to_add_it() -> None:
    with pytest.raises(ModelError, match=r"no model called 'J999' in the library\. Add it with"):
        load_models([LIBRARY]).get("J999")


def test_user_models_override_core(tmp_path: Path) -> None:
    user = tmp_path / "models"
    (user / "jfet").mkdir(parents=True)
    shutil.copy(LIBRARY / "jfet" / "J201.lib", user / "jfet" / "J201.lib")
    info = json.loads((LIBRARY / "jfet" / "J201.json").read_text())
    info["description"] = "my own J201"
    (user / "jfet" / "J201.json").write_text(json.dumps(info))
    lib = load_models([user, LIBRARY])
    assert lib.get("J201").info.description == "my own J201"
    assert "TL072" in lib


def test_broken_model_file(tmp_path: Path) -> None:
    (tmp_path / "jfet").mkdir()
    (tmp_path / "jfet" / "X.json").write_text("{}")
    with pytest.raises(ModelError, match="can't be used"):
        load_models([tmp_path])


def test_model_cards_text_deduplicates() -> None:
    lib = load_models([LIBRARY])
    j = lib.get("J201")
    assert model_cards_text([j, j]).count(".model J201") == 1


def test_every_library_op_amp_records_its_swing_from_a_sheet_or_says_why() -> None:
    """Phase 9b (D-150): each op-amp's output swing comes from its datasheet; one without
    a figure yet is listed here with the reason (the rule of thumb covers it)."""
    pending: dict[str, str] = {}  # model → why it has no figure yet
    library = load_models([LIBRARY])
    for model_id in library.ids("opamp"):
        ratings = library.get(model_id).info.ratings
        has = "out_pos_headroom" in ratings and "out_neg_headroom" in ratings
        assert has != (model_id in pending), model_id


def test_an_op_amp_without_a_swing_figure_uses_the_rule_of_thumb() -> None:
    from solum.analysis.dc import OPAMP_SWING_MARGIN, opamp_output_limits

    library = load_models([LIBRARY])
    lm358 = library.get("LM358")
    bare = type(lm358)(lm358.info.model_copy(update={"ratings": {}}), lm358.card)  # a user's
    assert opamp_output_limits(bare, 9.0, 0.0) == (
        OPAMP_SWING_MARGIN, 9.0 - OPAMP_SWING_MARGIN, False)  # fmt: skip
    assert opamp_output_limits(library.get("LM358"), 9.0, 0.0) == pytest.approx((0.005, 7.0, True))


PACKAGE_PINS = {
    "bjt": {"C", "B", "E"}, "jfet": {"D", "G", "S"}, "diode": {"A", "K"}, "led": {"A", "K"}
}  # fmt: skip


def test_transistors_and_diodes_have_cited_pin_numbers() -> None:
    """For export (D-143, D-149): each pin numbered once, 1…n, from a cited sheet."""
    library = load_models([LIBRARY])
    for kind, pins in PACKAGE_PINS.items():
        for model_id in library.ids(kind):
            package = library.get(model_id).info.package
            assert package is not None and package.source, model_id
            assert set(package.pins) == pins, model_id
            assert sorted(package.pins.values()) == list(range(1, len(pins) + 1)), model_id


def test_every_model_links_its_datasheet() -> None:
    """9c, Tools → Parts and datasheets: every model's record names the sheet to open."""
    lib = load_models([LIBRARY])
    missing = [i for i in lib.ids() if not lib.get(i).info.datasheet.startswith("http")]
    assert not missing


def test_a_catalogue_entry_says_whose_card_and_its_caveats() -> None:
    """9c: the parts list reads each record, nothing new written: whose card it is, the
    sheet it was fitted to, its note, how many datasheet checks it passes, and the
    comparisons the sheet gives no limit for (a known miss, or a typical with no spread)."""
    lib = load_models([LIBRARY])
    ours = lib.get("2N404").catalogue_entry()
    assert ours["origin"] == "ours" and ours["origin_detail"].startswith("RCA 2N404")
    assert "held flat below 12 mA" in ours["note"]
    assert ours["datasheet"].startswith("https://bitsavers")
    assert ours["checks"] == 10  # its 12 sheet figures less the two VBE(sat) misses
    assert [u["quantity"] for u in ours["unchecked"]] == ["vbe_sat", "vbe_sat"]
    assert ours["unchecked"][0]["name"] == "VBE(sat)"
    pulled = lib.get("RC4558").catalogue_entry()
    assert pulled["origin"] == "library" and pulled["origin_detail"] == "rc4558.mod"
    assert pulled["maker"] == "Texas Instruments"
    assert "the 1989 model reflects the original" in pulled["unchecked"][0]["note"]
    assert pulled["note"].startswith("The card clips 2.0 V from each rail")
    assert lib.get("OC81D").catalogue_entry()["origin"] == "estimate"
    assert lib.get("TC1044S").catalogue_entry()["origin"] == "maker"
    assert lib.get("TL072").catalogue_entry()["package"] == "8-pin DIP"
