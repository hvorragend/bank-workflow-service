"""Reporting-Modul: lese-only Endpunkte fuer Aufsicht/Revision.

Authentifizierung via API-Token im Header `X-Reporting-Token` — getrennt vom
Login-/JWT-Pfad. Das verhindert, dass eine kompromittierte User-Session
automatisch Reporting-Daten freigibt.
"""
