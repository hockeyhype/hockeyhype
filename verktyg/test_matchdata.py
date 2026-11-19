"""Test av tolkningen av swehockeys matchsidor (matchdata.py). Kör: python verktyg/test_matchdata.py

Testfilerna i test_fixtures/ är riktiga sidor (U14-match 2026-11-18) där alla namn bytts ut.
"""
import os, sys

MAPP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(MAPP))
import matchdata

las = lambda n: open(os.path.join(MAPP, "test_fixtures", n), encoding="utf8").read()
m = matchdata.tolka_match(las("events-1130378.html"), las("lineup-1130378.html"), "1130378", "21869")

assert (m["hemma"], m["borta"], m["h"], m["b"]) == ("Nyköpings SK", "Södertälje SK", 3, 4), m["hemma"]
assert m["perioder"] == [[0, 2], [3, 2]]
assert m["klar"] and m["status"] == "Final Score" and m["publik"] == 39
assert (m["datum"], m["tid"], m["arena"]) == ("2026-11-18", "19:15", "Stora Hallen")

H, B = m["lag"]["h"], m["lag"]["b"]
assert (H["kort"], B["kort"]) == ("NSK", "SSK")
assert H["skott"] == [11, 12] and B["skott"] == [9, 10]
assert H["raddningar"] == [7, 8] and B["raddningar"] == [11, 9]
assert (H["pim"], B["pim"], H["pp"], B["pp"]) == (8, 4, "N/A", "33,33%")
assert [(g["nr"], g["rdd"], g["skott"]) for g in H["malvakter"]] == [(1, 8, 10), (30, 7, 9)]
assert [(g["nr"], g["rdd"], g["skott"]) for g in B["malvakter"]] == [(1, 20, 23)]

# Händelserna i matchordning, med rätt lag
h = m["handelser"]
mal = [e for e in h if e["typ"] == "mal"]
assert [e["stallning"] for e in mal] == ["0-1", "0-2", "1-2", "2-2", "3-2", "3-3", "3-4"]
assert [e["lag"] for e in mal] == ["b", "b", "h", "h", "h", "b", "b"]
assert mal[2]["lage"] == "SH1" and mal[6]["lage"] == "PP1"
assert mal[0]["spelare"] == {"nr": 68, "namn": "Efternamn68, Förnamn"} and mal[0]["malnr"] == 3
assert [a["nr"] for a in mal[0]["assist"]] == [93]
utv = [e for e in h if e["typ"] == "utv"]
assert len(utv) == 6 and utv[0] == {"period": "2nd period", "tid": "24:21", "typ": "utv", "min": 2,
                                     "spelare": {"nr": 28, "namn": "Efternamn28, Förnamn"}, "orsak": "Boarding", "lag": "h"}
assert [e["typ"] for e in h if e["tid"] == "20:00"] == ["mv_ut", "mv_in"]
assert sum(e["typ"] == "timeout" for e in h) == 1

# Laguppställningen: målvakter och femmor med positioner (swehockeys ordning, vänster kolumn = vänster)
U = H["uppstallning"]
assert [p["nr"] for p in U["malvakter"]] == [30, 1]
assert [k["namn"] for k in U["kedjor"]] == ["1st Line", "2nd Line", "3rd Line"]
assert [(p["pos"], p["nr"]) for p in U["kedjor"][0]["spelare"]] == [("LD", 32), ("RD", 19), ("LW", 11), ("C", 40), ("RW", 6)]
assert [(p["pos"], p["nr"]) for p in U["kedjor"][2]["spelare"]] == [("RD", 7), ("LW", 41), ("C", 17), ("RW", 29)]
UB = B["uppstallning"]
assert [k["namn"] for k in UB["kedjor"]] == ["1st Line", "2nd Line", "3rd Line"]
assert [(p["pos"], p["nr"]) for p in UB["kedjor"][0]["spelare"]] == [("LD", 41), ("RD", 17), ("LW", 77), ("C", 29), ("RW", 18)]
assert H["farg"] == "Black" and B["farg"] == "Blue"
assert m["domare"] == ["Domare Ett"] and m["linjemän"] == ["Linje Ett", "Linje Två"]
# Mål utan målantal efter skytten (vissa matcher): assisten får inte hamna i skyttens namn
rad = ('<h2>A - B</h2><h2>Actions</h2><table><tr><th><h3>1st period</h3></th></tr><tr><td>01:57</td><td>0-1 (EQ)</td>'
       '<td>BBB</td><td>21. Efternamn21, Förnamn<div style="padding-left: 10px;">14. Efternamn14, Förnamn</div>'
       '<td class="tdOdd" /></td></tr></table>')
e = matchdata.tolka_handelser(rad)["handelser"][0]
assert e["spelare"] == {"nr": 21, "namn": "Efternamn21, Förnamn"} and [a["nr"] for a in e["assist"]] == [14], e
print("alla tester ok")
