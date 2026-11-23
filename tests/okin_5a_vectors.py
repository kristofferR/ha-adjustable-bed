"""Frozen Okin 5A frames per profile, the vectors the codec must reproduce.

No accepted APK Protocol Audit report covers these routes' key frames, so each
profile's vectors are every frame its pre-v5 controller sent, captured from the
controller methods before the move:

- The accepted MFirm 900 1.1.2 report (``com.okin.bedding.rizemf900``) and the
  Nectar Move report reach only the Okin CST ``0C 02`` frame.
- The Sealy 1.1.3 reports (``com.okin.sealy``) are PARTIAL.
- #447 lists the AdjustableM5X5 1.2.3 and M1X12 1.1.3 reports as historically
  accepted and unavailable for new reuse. Every ``star_elevate`` frame below also
  appears in the local M1X12 1.1.3 COMPLETE report (run ``39bdcafa``), as a
  cross-check only.
"""

FROZEN_FRAMES: dict[str, frozenset[str]] = {
    # pre-v5 Okin7ByteController (MaximumWorf's Nectar reverse engineering); also `nectar`
    "okin_7byte": frozenset(
        {
            "5a0103103000a5",
            "5a0103103001a5",
            "5a0103103002a5",
            "5a0103103003a5",
            "5a0103103004a5",
            "5a0103103007a5",
            "5a010310300fa5",
            "5a0103103010a5",
            "5a0103103011a5",
            "5a0103103013a5",
            "5a0103103016a5",
            "5a010310301aa5",
            "5a010310301ba5",
            "5a0103103058a5",
            "5a0103103059a5",
            "5a010310305aa5",
            "5a0103103071a5",
            "5a0103103073a5",
            "5a0103103074a5",
        }
    ),
    # pre-v5 OkinNordicController (#50, Mattress Firm 900 / iFlex); also `mattressfirm`
    "okin_nordic": frozenset(
        {
            "09050a23050000",
            "5a0103103000a5",
            "5a0103103001a5",
            "5a0103103002a5",
            "5a0103103003a5",
            "5a0103103006a5",
            "5a0103103007a5",
            "5a010310300fa5",
            "5a0103103010a5",
            "5a0103103013a5",
            "5a0103103016a5",
            "5a0103103017a5",
            "5a0103103018a5",
            "5a0103103052a5",
            "5a0103103059a5",
            "5a010310305aa5",
            "5a010310306fa5",
            "5a0103103071a5",
            "5a0103103073a5",
            "5a0103103074a5",
            "5a0103104060a5",
            "5a0103104063a5",
            "5a0b00a5",
        }
    ),
    # pre-v5 OkinCB35Controller (Sealy Posturematic, #310)
    "okin_cb35": frozenset(
        {
            "5a0103103000a5",
            "5a0103103001a5",
            "5a0103103002a5",
            "5a0103103003a5",
            "5a0103103006a5",
            "5a0103103007a5",
            "5a0103103008a5",
            "5a0103103009a5",
            "5a010310300aa5",
            "5a010310300ba5",
            "5a010310300fa5",
            "5a0103103010a5",
            "5a0103103011a5",
            "5a0103103013a5",
            "5a0103103016a5",
            "5a0103103017a5",
            "5a0103103018a5",
            "5a010310301aa5",
            "5a010310301ba5",
            "5a0103103052a5",
            "5a0103103059a5",
            "5a010310305aa5",
            "5a0103103060a5",
            "5a0103103061a5",
            "5a0103103062a5",
            "5a0103103063a5",
            "5a010310306fa5",
            "5a0103103070a5",
            "5a0103103071a5",
            "5a0103103073a5",
            "5a0103103074a5",
            "5a0103103080a5",
            "5a0103103081a5",
            "5a0b00a5",
        }
    ),
    # pre-v5 StarElevateController and its M1X12 route (StarElevateM1X12Controller)
    "star_elevate": frozenset(
        {
            "5a010310300fa5",
            "5a0103103040a5",
            "5a0103103041a5",
            "5a0103103042a5",
            "5a0103103043a5",
            "5a0103103044a5",
            "5a0103103045a5",
            "5a0103103046a5",
            "5a010310304fa5",
            "5a0b00a5",
        }
    ),
}

STARCODE_FRAMES: dict[str, frozenset[str]] = {
    "normal": frozenset(
        {
            "5a0100000400a5",
            "5a0100000800a5",
            "5a0100000c00a5",
            "5a0100800000a5",
            "5a0101000000a5",
            "5a0101800000a5",
            "5a0103103000a5",
            "5a0103103001a5",
            "5a0103103002a5",
            "5a0103103003a5",
            "5a0103103004a5",
            "5a0103103005a5",
            "5a0103103006a5",
            "5a0103103007a5",
            "5a0103103008a5",
            "5a0103103009a5",
            "5a010310300aa5",
            "5a010310300ba5",
            "5a010310300ca5",
            "5a010310300da5",
            "5a010310300fa5",
            "5a0103103010a5",
            "5a0103103011a5",
            "5a0103103013a5",
            "5a0103103016a5",
            "5a0103103017a5",
            "5a0103103018a5",
            "5a010310301aa5",
            "5a010310301ba5",
            "5a010310301fa5",
            "5a0103103040a5",
            "5a0103103041a5",
            "5a0103103042a5",
            "5a0103103043a5",
            "5a0103103044a5",
            "5a0103103045a5",
            "5a0103103046a5",
            "5a010310304fa5",
            "5a0103103052a5",
            "5a0103103053a5",
            "5a0103103054a5",
            "5a0103103058a5",
            "5a0103103059a5",
            "5a010310305aa5",
            "5a0103103060a5",
            "5a0103103061a5",
            "5a0103103062a5",
            "5a0103103063a5",
            "5a0103103066a5",
            "5a0103103067a5",
            "5a0103103068a5",
            "5a0103103069a5",
            "5a010310306fa5",
            "5a0103103070a5",
            "5a0103103071a5",
            "5a0103103073a5",
            "5a0103103074a5",
            "5a0103103079a5",
            "5a010310307aa5",
            "5a0103103089a5",
            "5a010310308aa5",
            "5a0103103090a5",
            "5a0103103091a5",
            "5a0103103092a5",
            "5a0103103094a5",
            "5a0103103095a5",
            "5a0103103096a5",
            "5a0103104060a5",
            "5a0103104061a5",
        }
    ),
    "extended": frozenset(
        {
            "5ae00400000000a5",
            "5ae00400060000a5",
            "5ae00400250000a5",
            "5ae00401010000a5",
            "5ae00401250000a5",
            "5ae00406000000a5",
            "5ae00406030300a5",
            "5ae00407010000a5",
            "5ae00407020000a5",
            "5ae00407030000a5",
            "5ae00407070000a5",
            "5ae0040d090100a5",
        }
    ),
    "position_target": frozenset(
        {"5af003006400a5", "5af003023200a5", "5af003023700a5", "5af003070000a5"}
    ),
    "request": frozenset({"5a0b00a5", "5ab000a5", "5ad000a5"}),
    "clock": frozenset(
        {"5a14071a07100d2d1e04a5", "5a14071a0a1a010e191ea5", "5a14074a0a1a010e191ea5"}
    ),
}
"""StarCode frames of the standalone StarCode controllers, by codec encoder.

Every literal of these encoders in the controllers' frozen artifact vectors:
``fixtures/starcode_m1x12_vectors.json`` (M1X12 1.1.3),
``fixtures/starcode_m5x5_commands.json`` and ``starcode_m5x5_existing_leaves.json``
(AdjustableM5X5 1.2.3), ``fixtures/sleepys_elite_routes_v2.tsv`` and
``sleepys_elite_dynamic_v2.tsv`` (Sleepy's Elite 1.1.5) and the SleepSpa 1.3.7
oracles in ``test_sleepstar.py``.
"""
