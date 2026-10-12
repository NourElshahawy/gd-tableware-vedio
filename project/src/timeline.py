"""Shared timeline for picture and sound. 120 BPM -> one beat every 0.5 s.

Every major cut sits on a beat so the edit and the soundtrack stay locked.
"""
FPS = 30
DURATION = 20.0
BPM = 120
BEAT = 60.0 / BPM

# scene boundaries (seconds)
S1 = (0.0, 3.0)    # emerging from darkness - black serving pot
S2 = (3.0, 6.0)    # material beauty - marble macros (cuts at 3, 4, 5)
S3 = (6.0, 9.0)    # black collection - bowl, match cut to pot at 7.5
S4 = (9.0, 12.0)   # contrast - white dish, two-tone bowl at 10.5
S5 = (12.0, 17.0)  # grand collection reveal (staggered on beats)
S6 = (17.0, 20.0)  # brand finale

MACRO_CUTS = (3.0, 4.0, 5.0)
MATCH_CUT = 7.5
TWO_TONE_CUT = 10.5
REVEAL_BEATS = (12.0, 12.5, 13.0, 13.5, 14.0)  # collection pieces light up
LOGO_HIT = 18.0                                 # final musical impact

# accents the soundtrack hits (metallic / impact)
IMPACTS = (0.0, 6.0, 12.0, 17.0, 18.0)
ACCENTS = (3.0, 4.0, 5.0, 7.5, 9.0, 10.5, 12.5, 13.0, 13.5, 14.0)
