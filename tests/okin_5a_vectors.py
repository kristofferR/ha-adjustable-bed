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
