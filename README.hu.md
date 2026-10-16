# n8n-backup

[![CI](https://github.com/radaimate/n8n-backup/actions/workflows/ci.yml/badge.svg)](https://github.com/radaimate/n8n-backup/actions/workflows/ci.yml)

*[English version](README.md)*

Automatikus mentés egy Dockerben futó [n8n](https://n8n.io) SQLite-adatbázisáról, Windowson.

A script szabályosan leállítja az n8n-konténert, kimásolja belőle az adatbázist, dátumozott ZIP-fájlba csomagolja, megtartja a legutóbbi mentéseket, újraindítja a konténert, és az eredményről Telegramon értesítést küld. A Windows Feladatütemezőből (Task Scheduler) futtatható.

A projekt egy korábbi PowerShell-script Python-átirata, modulokra bontva, típusjelzésekkel és tesztekkel.

## Funkciók

- **Konzisztens mentés:** a konténert `docker stop -t 30` állítja le, így az n8n szabályosan lezárja az adatbázist, és a másolás alatt nem ír bele.
- **Dátumozott ZIP:** `n8n_backup_2026-10-15_03.00.00.zip` formátumú fájlnév, a fájlok a ZIP gyökerében.
- **Méretellenőrzés:** a gyanúsan kicsi (100 KB alatti) ZIP hibának számít, és törlődik.
- **Retenció:** csak a legutóbbi 15 mentés marad meg, a régebbiek törlődnek.
- **A konténer mindig újraindul,** akkor is, ha a mentés közben hiba történt.
- **Telegram-értesítés** egyértelmű állapotokkal (OK / FIGYELMEZTETÉS / HIBA / KRITIKUS HIBA / KONFIGURÁCIÓS HIBA).
- **A titkosítási kulcs nem hagyja el a konténert:** csak a `database.sqlite*` fájlok kerülnek ki, a `config` fájl nem.
- **Exit kód:** hiba esetén `1`, így a Feladatütemező is látja, ha valami nem sikerült.
- **Forgó naplófájl:** legfeljebb 1 MB, 3 korábbi példánnyal.
- **Takarítás:** az ideiglenes másolatok a futás végén törlődnek a `%TEMP%` mappából.

## Követelmények

- Windows
- Python 3.13
- Docker Desktop, benne egy futó, `n8n` nevű konténer (a hivatalos `n8nio/n8n` image alapértelmezett adatmappájával: `/home/node/.n8n`)
- Telegram-bot (opcionális, csak az értesítésekhez)

## Telepítés

```powershell
git clone https://github.com/radaimate/n8n-backup.git
cd n8n-backup
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Beállítás

Másold le a `.env.example` fájlt `.env` néven, és töltsd ki:

```powershell
Copy-Item .env.example .env
```

| Változó | Kötelező | Leírás |
|---|---|---|
| `BACKUP_DIR` | igen | Ebbe a mappába kerülnek a ZIP-fájlok és a napló. Ha nem létezik, a script létrehozza. Egy OneDrive-mappa megadásával a mentések a felhőbe is felkerülnek. |
| `TELEGRAM_TOKEN` | nem | A Telegram-bot tokenje (a [@BotFather](https://t.me/BotFather) adja). |
| `TELEGRAM_CHAT_ID` | nem | A chat azonosítója, ahová az értesítések mennek. |

Ha a `TELEGRAM_TOKEN` vagy a `TELEGRAM_CHAT_ID` üres, a script nem küld értesítést, de a mentés ettől még lefut.

A `.env` fájl titkos adatokat tartalmaz, ezért szerepel a `.gitignore`-ban, és nem kerül fel a repóba.

További beállítások az [n8n_backup/config.py](n8n_backup/config.py) fájlban:

| Konstans | Alapérték | Jelentés |
|---|---|---|
| `CONTAINER_NAME` | `"n8n"` | A mentendő konténer neve |
| `KEEP_COUNT` | `15` | Ennyi mentés marad meg |
| `MIN_ZIP_SIZE` | `100 * 1024` | Ennél kisebb ZIP-fájl (bájtban) hibának számít |
| `LOG_MAX_BYTES` | `1024 * 1024` | A naplófájl maximális mérete |
| `LOG_BACKUP_COUNT` | `3` | Ennyi régi naplófájl marad meg |

## Futtatás

A projekt gyökeréből:

```powershell
python -m n8n_backup
```

| Exit kód | Jelentés |
|---|---|
| `0` | A mentés sikeres, és a konténer fut |
| `1` | Valamelyik lépés nem sikerült (a részletek a naplóban és a Telegram-üzenetben) |

## A mentés menete

1. A `BACKUP_DIR` ellenőrzése és a naplózás beállítása
2. A konténer leállítása (`docker stop -t 30 n8n`)
3. A `database.sqlite*` fájlok kimásolása egy ideiglenes mappába (`docker cp`)
4. A fájlok ZIP-be csomagolása
5. A ZIP méretének ellenőrzése
6. A régi mentések törlése
7. A konténer újraindítása (`docker start n8n`), **hiba esetén is**
8. Az ideiglenes mappa törlése
9. Jelentés: napló + Telegram + exit kód

## Ütemezés a Feladatütemezővel

A Feladatütemezőben (Task Scheduler) hozz létre egy új feladatot (*Create Task*), és a *Műveletek* (*Actions*) fülön állítsd be:

| Mező | Érték |
|---|---|
| Program/script | A venv Pythonjának **teljes** útvonala, pl. `C:\...\n8n-backup\.venv\Scripts\python.exe` |
| Argumentumok | `-m n8n_backup` |
| Kezdés helye (*Start in*) | A projekt gyökérmappája, pl. `C:\...\n8n-backup` |

- A **Program** mezőbe a venv Pythonja kell, ne a globális `python`, mert csak abban vannak telepítve a függőségek.
- A **Kezdés helye** mező kötelező: a `python -m n8n_backup` az aktuális mappában keresi az `n8n_backup` csomagot.
- A Docker Desktop általában csak bejelentkezett felhasználónál fut, ezért a feladatot is a *Csak akkor fusson, ha a felhasználó be van jelentkezve* beállítással érdemes futtatni.

## Kimenet

**Mentések:** `BACKUP_DIR\n8n_backup_ÉÉÉÉ-HH-NN_óó.pp.mm.zip`, benne a `database.sqlite` (és ha vannak, a `-wal` és `-shm` fájlok).

**Napló:** `BACKUP_DIR\backup-log.txt`. 1 MB fölött új fájl kezdődik, a régiek `backup-log.txt.1` … `.3` néven maradnak meg.

**Telegram-értesítések:**

| Állapot | Mentés | Konténer | Teendő |
|---|---|---|---|
| OK | sikeres | fut | — |
| FIGYELMEZTETÉS | sikertelen | fut | Megnézni a naplót, a következő futás újrapróbálja |
| HIBA | sikeres | **áll** | A konténert kézzel kell elindítani |
| KRITIKUS HIBA | sikertelen | **áll** | Azonnali beavatkozás szükséges |
| KONFIGURÁCIÓS HIBA | el sem indult | fut (nem állt le) | A `.env` javítása: a következő futás magától sem fog sikerülni |

A KONFIGURÁCIÓS HIBA akkor jön, ha a `BACKUP_DIR` hiányzik, üres vagy nem hozható létre. Ilyenkor a script a konténerhez hozzá sem nyúl.

## Visszaállítás

> **Fontos: a titkosítási kulcs.** Az n8n a credentialöket (API-kulcsok, jelszavak) titkosítva tárolja az adatbázisban. A kulcs **nincs** benne a mentésben: a konténer `/home/node/.n8n/config` fájljában van, vagy az `N8N_ENCRYPTION_KEY` környezeti változóban. A kulcs nélkül a visszaállított credentialök nem használhatók, ezért mentsd el külön, például egy jelszókezelőbe:
>
> ```powershell
> docker exec n8n cat /home/node/.n8n/config
> ```

A visszaállítás lépései:

```powershell
# 1. A konténer leállítása
docker stop -t 30 n8n

# 2. A kiválasztott mentés kicsomagolása
Expand-Archive .\n8n_backup_2026-10-15_03.00.00.zip -DestinationPath .\restore

# 3. A konténerben maradt régi WAL- és SHM-fájl törlése.
#    Ha ott maradnának, az SQLite egy másik adatbázis naplóját játszaná rá
#    a visszaállított fájlra, ami az adatbázis sérülését okozhatja.
docker run --rm --volumes-from n8n alpine rm -f /home/node/.n8n/database.sqlite-wal /home/node/.n8n/database.sqlite-shm

# 4. A ZIP összes fájljának visszamásolása a konténerbe
docker cp .\restore\. n8n:/home/node/.n8n/

# 5. A tulajdonos beállítása még az indítás előtt. A docker cp root tulajdonba
#    másol, az n8n viszont a node felhasználóval (UID 1000) fut.
docker run --rm --volumes-from n8n alpine sh -c "chown 1000:1000 /home/node/.n8n/database.sqlite*"

# 6. Indítás
docker start n8n
```

A `--volumes-from` akkor működik, ha az adatmappa Docker volume-on van (a hivatalos n8n-telepítésnél igen). Az `alpine` image-et a Docker az első használatkor letölti.

Az eljárás tesztelve van: egy mentést egy külön, ugyanazzal az n8n image-dzsel futó konténerbe állítottam vissza. A felhasználók, a workflow-k és a credentialök is visszaálltak, és egy HTTP-kérés igazolta, hogy a visszaállított credentialök a külön tárolt kulccsal visszafejthetők.

## Tervezési döntések

**Miért kell leállítani a konténert?**

Ha futó konténerből másolnánk, fennállna annak a veszélye, hogy éppen akkor másolnánk, amikor az n8n ír az adatbázisba, így inkonzisztens adatok kerülhetnek a ZIP-be.

**Miért `urllib` és nem `requests`?**

Mivel napi egy db POST kéréssel történő üzenetküldés van, ezért nem éri meg a `requests`, még akkor sem, ha a szintaxisa egyszerűbb, hisz az nem része a standard library-nak (kevesebb függőség = kevesebb karbantartás). Ha több API-hívás vagy JSON-kezelés lenne, a `requests`-et választanám.

**Miért van két külön `try` a `finally`-ben?**

A `finally`-ben két takarítási lépés van, mindkettő külön `try`-ban, hogy az egyik hibája ne akadályozza a másikat. Például ha `try` nélkül lenne az első, és a `docker start` nem jó valamiért, akkor a `STAGING` (ideiglenes mappa) nem törlődne, ott maradna, ami viszont már biztonsági kockázat. Emellett a jelentés sem menne ki, mert a hiba kimenne a `main()`-ből. A script Telegram-üzenet nélkül omlana össze.

**Miért nincs kulcs a mentésben? (n8n encryption key)**

Az n8n-ben a workflow-k külső szolgáltatásokhoz kapcsolódnak: Gmail, Google Sheets, API-kulcsok, adatbázis-jelszavak. Ezeket az n8n a `database.sqlite`-ban titkosítva tárolja, és a titkosítás kulcsa a `config` fájlban van. A titkosított adatot és a kulcsát szándékosan külön kell tárolni. Ha egy felhőbe szinkronizált mentés kiszivárog, a credentialök a kulcs nélkül használhatatlanok. Ezért a script a config fájlt ideiglenesen sem másolja ki a konténerből, csak az adatbázis-fájlokat.

**Miért Telegram?**

Független az n8n-től: ha az n8n áll, a riasztás akkor is megjön, mert a megfigyelt rendszer nem saját magáról riaszt. Emellett ingyenes, és viszonylag egyszerűen valósítottam meg vele, amit akartam, mert nem kell hozzá e-mail-szerver, plusz gyors, push-alapú a riasztás. Valamint egyes cégek (Meta) az üzenetküldőik esetén komolyan korlátozzák vagy büntetik az automatizációt.

**Miért Pythonban?**

Egészen egyszerűen azért, mert a C/C++ mellett Pythonban van a legnagyobb tapasztalatom, és szerencsémre a 3 közül az automatizálásra az utolsó kitűnően használható. A gazdag standard könyvtára pedig segítette a munkámat.

**Miért kell CI workflow?**

Ez egy egyszerűen megvalósítható, de annál hasznosabb funkció, minden push és pull request esetén lefuttatja a teszteket és ellenőrzi a formázást, így ha valami hibás, látjuk a GitHubon és már előre tudjuk, hogy a rossz kódra nem építünk. Ezen kívül, mivel tiszta gépen, Ubuntun és Windowson is fut az is kiderül ha valami csak a saját gépemen működik.

## Fejlesztés

```powershell
pip install -r requirements-dev.txt

pytest              # tesztek
ruff check .        # lint
ruff format .       # formázás
```

A tesztek nem igényelnek Dockert vagy hálózatot: a `subprocess.run` és az `urllib` hívásokat a pytest `monkeypatch` fixture-je helyettesíti.

### Folyamatos integráció (CI)

Minden pushnál és pull requestnél a GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)) Ubuntun és Windowson is lefuttatja ugyanezt a három ellenőrzést: `ruff check`, `ruff format --check` és `pytest`. Az eredményt a README tetején lévő jelvény mutatja.

### A projekt szerkezete

```
n8n_backup/
  __main__.py     # belépési pont: a mentés folyamata és a jelentés
  config.py       # konstansok, a .env betöltése, a BACKUP_DIR ellenőrzése
  backup.py       # DB-fájlok kimásolása, ZIP készítése és ellenőrzése, retenció
  docker_ops.py   # Docker-parancsok futtatása
  notify.py       # Telegram-értesítés
  errors.py       # BackupError kivételosztály
tests/            # pytest-tesztek
.github/workflows/
  ci.yml          # GitHub Actions: lint + tesztek Ubuntun és Windowson
```

## Licenc

[MIT](LICENSE)
