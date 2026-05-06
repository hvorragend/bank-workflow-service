"""DB-gestuetzte Konfiguration. Jeder Subsystem-Bereich hat ein Modul mit
typisierten get_*/set_*-Funktionen. Bewusst kein Caching — Reads sind klein
und selten, und so vermeiden wir die Klasse 'aenderung greift erst nach
Restart'-Bugs.
"""
