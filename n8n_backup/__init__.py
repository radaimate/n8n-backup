"""
n8n_backup – az n8n Docker-konténer SQLite-adatbázisának mentése.

Leállítja a konténert, kimásolja a database.sqlite fájlokat, dátumozott
ZIP-be csomagolja őket, csak a legutóbbi mentéseket tartja meg,
újraindítja a konténert, és az eredményről Telegramon értesítést küld.

Futtatás a projekt gyökeréből:
    python -m n8n_backup
"""
