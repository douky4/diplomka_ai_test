# Rozpoznávání AI obrázků

## Produkce: GitHub Pages + Supabase

- Kvíz: https://douky4.github.io/diplomka_ai_test/
- Administrace a CSV: https://douky4.github.io/diplomka_ai_test/admin.html
- Přihlášení do administrace používá heslo `ADMIN_PASSWORD` z lokálního `.env`.
- Data zůstávají v Supabase. `public.participants` obsahuje respondenty, `public.answers` jednotlivé odpovědi, jistotu, zdůvodnění a identifikaci obrázku/dvojice. `public.quiz_assignments` eviduje přidělené otázky.
- Pro analýzu použijte **Export CSV** v administraci; jeden řádek je jedna odpověď včetně údajů respondenta. Výsledky lze také prohlížet přes Supabase Table Editor.

GitHub Actions při pushi do `main` sestaví a publikuje pouze `_site`. Nastavení repozitáře obsahuje veřejné proměnné `SUPABASE_URL` a `SUPABASE_PUBLISHABLE_KEY`. Heslo administrace ani připojení k databázi do GitHubu nepatří.

Losování a zápis odpovědí provádějí SQL funkce v Supabase. Přímé čtení tabulek návštěvníky je zakázané; správné odpovědi jsou dostupné až v administraci. Každý respondent dostane 15 různých dvojic, vždy jen originál nebo AI verzi, s poměrem 7:8. Dva po sobě založení respondenti dostanou vzájemně doplňkové varianty.

Příprava nebo aktualizace databázových funkcí z lokálního `.env`:

```powershell
.venv\Scripts\python.exe scripts/deploy_supabase.py
.venv\Scripts\python.exe scripts/verify_supabase.py
.venv\Scripts\python.exe scripts/build_pages.py
```

Nasazení databáze uchovává záznamy a před změnou vytváří soukromou zálohu v `.local/backups/`. Ověřovací skript vrací všechny své testovací zápisy zpět transakcí. Administrace neodesílá heslo v URL; přihlášení platí čtyři hodiny.

Původní Flask/Render zůstává funkční jako záloha. Rozpracovaný kvíz se mezi doménami automaticky nepřenáší, protože prohlížeč ukládá identifikátor podle domény. Novým respondentům posílejte adresu GitHub Pages. Níže uvedené postupy pro Flask platí pro původní server.

Webová výzkumná aplikace, ve které respondent rozlišuje skutečné fotografie od obrázků vytvořených pomocí AI a u každé odpovědi uvádí míru jistoty.

## Technologie

- Flask + Gunicorn
- SQLite
- PostgreSQL / Supabase pro trvalé produkční uložení
- HTML, CSS a JavaScript
- nasazení na Renderu pomocí `render.yaml`

## Spuštění lokálně

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Aplikace poběží na `http://localhost:5000`. Administrace je dostupná na `/admin`.

## Struktura projektu

- `app.py` – Flask backend, databáze, API a administrace
- `index.html` – rozhraní testu
- `script.js` – ovládání testu a komunikace s API
- `style.css` – vzhled testu
- `images/` – testované obrázky
- `metadata.csv` – popis obrázků, správné odpovědi a parametry jejich vzniku
- `scripts/validate_dataset.py` – kontrola metadat a obrazových souborů
- `render.yaml` – konfigurace nasazení na Render
- `database.db` – lokální SQLite databáze, vytvoří se automaticky a není verzovaná

## Vyhodnocení

Aplikace zobrazuje tři odlišné metriky:

- **Úspěšnost** – podíl správných odpovědí bez ohledu na jistotu.
- **Průměrná jistota** – průměr z hodnot 1 až 5.
- **Jistotou vážené skóre** – číslo od 0 do 100, které kombinuje správnost a jistotu.

Vážené skóre jedné odpovědi se počítá takto:

| Odpověď | Jistota 1 | Jistota 2 | Jistota 3 | Jistota 4 | Jistota 5 |
|---|---:|---:|---:|---:|---:|
| Správná | 60 | 70 | 80 | 90 | 100 |
| Špatná | 40 | 30 | 20 | 10 | 0 |

Celkové vážené skóre respondenta je průměr bodů ze všech jeho odpovědí. Hodnota 50 představuje neutrální střed; vysoká jistota zesiluje správnou i špatnou odpověď odpovídajícím směrem.

Výsledky jsou dostupné v administraci, detailu respondenta, výsledkovém API a CSV exportu.

Administrace navíc porovnává výsledky ve věkových skupinách do 20, 21–30, 31–40, 41–50 a 51 a více let. U každé skupiny uvádí počet respondentů a odpovědí, úspěšnost, průměrnou jistotu a vážené skóre. Stejná agregovaná data poskytuje endpoint `/api/results/age-analysis`.

## Správa datasetu

Seznam testovacích obrázků se načítá z `metadata.csv`. Do testu se zařadí řádky, které mají `is_active=true` a `split` nastavený na `pilot` nebo `test`. Aktivních je 30 obrázků (15 fotografií a 15 AI variant), propojených společným `subject_id` do 15 dvojic. Dvě původní prototypové položky zůstávají neaktivní pro dohledání historie.

Při založení respondenta server v jedné transakci uloží 15 otázek do `quiz_assignments`: jednu verzi z každé dvojice, 7 nebo 8 AI obrázků a náhodné pořadí. Následující respondent dostane opačné verze, opět náhodně seřazené. `allocation_state` uchovává stav vyvažování i po restartu; databázový zámek brání souběžnému přidělení stejného bloku. Vyvažuje se počet přidělení, nikoli dokončených odpovědí.

`/api/images?participant_id=...` vrací pouze náhodné veřejné identifikátory a neutrální odkazy `/api/media/...`. Odpověď musí obsahovat přidělený veřejný `image_id` i `question_index`; server ověří shodu a uloží skutečný výzkumný identifikátor, správnou odpověď, jistotu 1–5, zdůvodnění a neměnný snímek metadat (`metadata_snapshot`). Správná odpověď ani názvy zdrojových souborů se seznamem otázek neposílají. Soubory projektu nejsou veřejně servírovány.

Prohlížeč uchovává identifikátor testu v `localStorage`. Po obnovení načte stejné přidělení a pokračuje první nezodpovězenou otázkou; dokončený test zůstane dokončený. Toto chrání pokračování v jednom prohlížeči, nikoli opakovanou účast stejného člověka z jiného zařízení nebo po vymazání úložiště.

Administrace `/admin/images` a chráněné API `/api/results/image-analysis` ukazují náhledy, počty přidělení a odpovědí, volby AI/fotografie, rozložení jistoty pro správné i chybné odpovědi, chyby s jistotou 4–5 a úplná zdůvodnění. Odkaz je v hlavní administraci. CSV export obsahuje i zamýšlenou obtížnost a záměrně požadovaná vodítka; skutečná obtížnost zůstává `unknown` do vyhodnocení pilotu.

Při prvním databázovém požadavku nové verze se automaticky doplní tabulky a sloupec `metadata_snapshot` ve stávajícím SQLite i PostgreSQL/Supabase. Dosavadní odpovědi se nemažou. Obrázky jsou soubory v GitHubu/Renderu, odpovědi a přidělení jsou v databázi Supabase.

Kontroly implementace:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
node -e "import('./tests/test_quiz_frontend.mjs').then(async m => console.log(await m.run()))"
```

Před spuštěním nebo nasazením nového datasetu spusťte:

```powershell
.venv\Scripts\python.exe scripts\validate_dataset.py
```

Validátor kontroluje povinné sloupce, unikátní ID a soubory, platnost obrázků, rozměry, přesné duplicity a vyvážení tříd. Nový obrázek je potřeba uložit do `images/`, přidat jako nový řádek do `metadata.csv` a následně validaci zopakovat.

## Nasazení na Render

Render podle `render.yaml` provede:

```text
pip install -r requirements.txt
gunicorn app:app
```

Po pushnutí změn do větve propojené s Renderem se služba znovu sestaví a nasadí.

### Trvalá databáze Supabase

Bez `DATABASE_URL` aplikace používá lokální `database.db`, což je vhodné jen pro vývoj.
V produkci nastavte v Renderu v **Environment**:

- `DATABASE_URL` – Supabase PostgreSQL connection string pro **Session pooler** (IPv4, port 5432), včetně `sslmode=require`;
- `ADMIN_PASSWORD` – vlastní dlouhé náhodné heslo.

Po restartu aplikace se tabulky a indexy vytvoří automaticky. Každá odpověď ukládá
volbu a jistotu respondenta, textové zdůvodnění, stabilní ID obrázku, správnou odpověď
a výzkumná metadata platná v okamžiku odpovědi.

Existující lokální data lze po nastavení `DATABASE_URL` jednorázově přenést:

```text
python scripts/migrate_sqlite_to_postgres.py
```

Hodnoty podle `.env.example` jsou pouze ukázky. Skutečné přihlašovací údaje se nesmí commitovat.
