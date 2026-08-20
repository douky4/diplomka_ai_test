# Rozpoznávání AI obrázků

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

Seznam testovacích obrázků se načítá z `metadata.csv`. Do testu se zařadí řádky, které mají `is_active=true` a `split` nastavený na `pilot` nebo `test`. Veřejný endpoint `/api/images` posílá pouze ID a cestu obrázku; správná odpověď, technika a ostatní výzkumná metadata zůstávají na serveru.

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
