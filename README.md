# Canteen Counter (Python / Flask)

Same five tables and seed data as the original `schema.sql` (users, admin, moderators, customers, menu_items), now served by Flask with a SQLite file that is created on first run.

    pip install -r requirements.txt
    python app.py          # http://localhost:5000

Delete `canteen.db` to reset the data.

Demo logins: rahul_admin/admin123, priya_mod/mod123, aman_mod/mod456, sara_cust/cust123, vikram_cust/cust456, neha_cust/cust789.

Passwords are stored hashed. Orders run in a transaction and roll back if any item is unavailable or the wallet is short.
