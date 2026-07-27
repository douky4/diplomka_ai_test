# diploma_ai_test Streamlit

Tento projekt byl přepsán na Streamlit aplikaci s SQLite databází pro nasazení na Replit.

## Co je v projektu

- `app.py` — Streamlit aplikace
- `requirements.txt` — závislosti (`streamlit`, `pillow`)
- `.replit` — konfigurace pro běh na Replit
- `images/` — dvě testovací fotografie
- `database.db` — bude vytvořena automaticky při prvním spuštění

## Jak spustit lokálně

1. Otevři složku projektu v terminálu.
2. Vytvoř a aktivuj virtuální prostředí (doporučeno):
   - `python -m venv venv`
   - `venv\Scripts\activate` (Windows)
3. Nainstaluj závislosti:
   - `pip install -r requirements.txt`
4. Spusť aplikaci:
   - `streamlit run app.py`
5. Otevři prohlížeč na adrese, kterou ti Streamlit ukáže.

## Jak nasadit na Replit

1. Vytvoř nový Replit projekt typu **Python**.
2. Nahraj do něj všechny soubory z tohoto adresáře.
3. Replit automaticky použije `requirements.txt` k instalaci závislostí.
4. V souboru `.replit` je nastaven příkaz pro spuštění:
   - `streamlit run app.py --server.address 0.0.0.0 --server.port 3000`
5. Spusť repl, aplikace se spustí a zobrazí se URL.

## Jak připravit ZIP ke stažení

1. Zkontroluj, že projekt obsahuje tyto soubory:
   - `app.py`
   - `requirements.txt`
   - `.replit`
   - `images/real_001.jpg`
   - `images/fake_001.png`
   - `style.css`, `index.html`, `script.js` (původní web zůstává v projektu)
2. Sbal složku do ZIP archivu.
3. ZIP pak můžeš nahrát do Replit nebo sdílet.

## Poznámka

Tento projekt již nepoužívá `index.html`, `script.js` a `style.css` pro běh Streamlit aplikace. Jsou v repozitáři zachovány jako původní verze projektu.
