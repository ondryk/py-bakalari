py_bakalari - small helper for Bakaláři API

Usage
- Install dependencies: pip install -r requirements.txt
- Edit `examples/login_example.py` and set `base_url` to your school's Bakaláři host (e.g. https://skola.bakalari.cz)
- Run example to perform login and save tokens:
  python examples/login_example.py

Token storage
- Default token file: `~/.py_bakalari_tokens.json`
- Contains access_token, refresh_token, id_token (when present), token_type, expires_in and obtained_at (unix timestamp)
