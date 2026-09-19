# Pilotní sada fotografií a AI variant

Složka `real/` obsahuje 15 původních fotografií, `ai/` obsahuje 15 syntetických variant. V této dávce byly doplněny soubory `pilot_ai_003.png` až `pilot_ai_015.png`; první dvě varianty vznikly dříve.

Párování originálů a variant je v `pairs.csv`. Přesná zadání, použitý nástroj, způsob vzniku, kontrolní součty a rozměry jsou v `generation_log.json`. Zadání nové dávky jsou také v `generation_plan_2026-09-19.json`.

Varianty vznikly vestavěným nástrojem image_gen z textových popisů napsaných po prohlédnutí originálů. Obrazové soubory nebyly předány generátoru. Jde o nové syntetické scény se stejným námětem, nikoli přesné kopie nebo editace originálů. Následné obrazové úpravy nebyly provedeny.

## Obtížnost

`difficulty_intended` vyjadřuje pouze záměr zadání, nikoli změřenou obtížnost. `deliberate_cues` zaznamenává požadované záměrné nedostatky, které se nemusely ve výsledku projevit. `visual_review` uvádí vybraná pozorování výsledků.

- AI008 (skleník): viditelně deformované a slité prvky bílého zábradlí.
- AI013 (stádo): nejbližší kráva má pět viditelných končetin.
- AI007 (kočka) a AI010 (bar): požadovaná snazší rozpoznatelnost se projevila slaběji; nelze je bez pilotního měření označit za snadné.

U záměrných chyb je při vyhodnocení potřeba uvést, že byly požadovány promptem. Nejsou dokladem spontánní chybovosti modelu. Skutečnou obtížnost stanoví odpovědi respondentů.

Sada je aktivní v kořenovém `metadata.csv`. Každý respondent dostane 15 obrázků, po jedné verzi z každé dvojice. Dvě původní prototypové položky zůstaly v metadatech neaktivní pro dohledání starších výsledků.
