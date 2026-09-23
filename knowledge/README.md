# Konvence znalostní báze

Každý znalostní soubor začíná hlavičkou:

```yaml
---
tema: <název>
naposledy_overeno: YYYY-MM-DD
zralost: experimental | preview | stable | legacy
primarni_zdroje:
  - <URL oficiální specifikace / dokumentace>
---
```

Doporučená struktura těla:

1. **Účel** – jaký problém řeší, jednou dvěma větami.
2. **Aktuální stav** – verze, datum, kdo řídí vývoj.
3. **Klíčové koncepty** – hlavní pojmy a mechanismy.
4. **Místo v architektuře** – vrstva, vazby na ostatní technologie.
5. **Zralost a rizika** – co je stabilní, co se mění, na co si dát pozor.
6. **Architektonické důsledky** – co z toho plyne pro návrh.
7. **Otevřené otázky** – co je potřeba ještě zjistit.
8. **Changelog** – co a kdy se v souboru měnilo.

Pravidla:
- Fakta o verzích a datech vždy se zdrojem.
- Vlastní názory a doporučení označuj jako **Pozn. Adam:**.
- Pokud je údaj starší než ~3 měsíce a jde o rychle se měnící oblast, před použitím ho ověř.
