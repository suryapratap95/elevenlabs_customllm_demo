"""Reset the demo database to the seed data: python reset_db.py"""
import store

store.reset()
print(f"Reset {store.DB_PATH}")
